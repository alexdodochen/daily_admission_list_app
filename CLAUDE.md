# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository identity

This is **`public_daily_admission_app`** — the public, sanitised fork that ships as a double-clickable `.exe` to each year's incoming 行政總醫師. It is the place where all UI/feature implementation lands.

Two read-only sibling repos are referenced by the integration plan and **must not be modified from here**:

- `https://github.com/alexdodochen/CV-Schedulling-APP` — reference for the planned 排班 + key 班 cards. Port code by copying in, not by editing there.
- `https://github.com/alexdodochen/daily-admission-list` (private, mirrors `D:\心臟內科 總醫師\行政總醫師\每日入院名單`) — source of workflow rules and reference impls (`cathlab_keyin.py`, `process_emr.py`, `verify_cathlab.py`, `webcvis_*.py`).

`app/VERSION` records the sha this repo was last synced from. Code under `app/` is downstream of the private workflow source — when post-sync rule changes need to flow in, **read the private repo, re-implement here**, do not push changes upstream.

**PHI safety**: this repo is public. Never commit real chart numbers, patient names, DOBs, or raw EMR text. The bundled `defaults.json` Sheet ID points at the sanitised public mirror.

## Common commands

```bash
# Dev run (auto-opens http://127.0.0.1:8766)
python -m app.run

# Tests (pytest config in pytest.ini — testpaths=tests)
python -m pytest tests/ -v
python -m pytest tests/test_cathlab_service.py -v          # single file
python -m pytest tests/test_cathlab_service.py::test_x     # single test

# Playwright browsers (needed for Step 3 EMR + Step 5 cathlab)
playwright install chromium

# Build the .exe (see BUILD.md for full handoff procedure)
# 1. cp <real-SA>.json app/bundled/service_account.json   (.gitignored)
# 2. verify app/bundled/defaults.json sheet_id
# 3. bump app/VERSION if shipping
pyinstaller packaging.spec --noconfirm
# Output: dist/admission-app/admission-app.exe (onedir)
```

There is no `.github/workflows/` directory in this clone — README mentions a `pytest.yml` CI but it is not present here; verify before referencing CI in commits.

## Architecture

### Runtime shape

FastAPI (`app/main.py`) + uvicorn launched by `app/run.py`, which opens the browser after a 1s delay. Jinja2 templates (`app/templates/`), no JS framework — inline `app/static/app.js` only. Single-user, no concurrency locks.

### 3-card home

`/` renders `home.html` (a card grid). The three cards:

- **`/sched`** — Card 1, 排班. Renders `schedule_gen.html` (self-contained Tailwind page, doesn't extend `base.html`). Drives a 5-step UI against `/api/sched/{init,compute,solve,write}`.
- **`/` (disabled card)** — Card 2, Key 班. Placeholder; the keyin port from CV-Schedulling-APP is Phase 2.
- **`/admission`** — Card 3, 入院清單. Renders `admission.html` (formerly `index.html`) — the original 6-step admission workflow, unchanged.

`base.html` provides the topbar nav (主畫面 / 排班 / 入院清單 / 設定). When `cfg.is_ready()` is false, every page route redirects to `/settings`.

### Card 1 — 排班 architecture

Two new modules:

- `app/services/cv_solver.py` — pure scheduling logic ported from `CV-Schedulling-APP/cv_solver.py`. Owns `TAIWAN_HOLIDAYS`, `is_taiwan_holiday`, `make_stat_type_fn`, doctor pools (`CRS` / `VS_LIST` / `INTER_MID`), and the backtracking solver. No I/O — caller supplies `baseline` dict, gets `schedule` dict back. Solver tries strict QOD first, relaxes if infeasible.
- `app/services/scheduling_service.py` — Google Sheets I/O for the duty schedule. Talks to a **different spreadsheet** than `sheet_service` (uses `cfg.schedule_sheet_id`, not `cfg.sheet_id`) with the same service-account credentials. Provides `get_sheet()` / `connection_check()` / `write_calendar_sheet()` / `write_monthly_stats()` / `load_cumulative_stats()` / `update_cumulative_stats()`. Has its own client+spreadsheet memoisation with `reset_cache()` (called alongside `sheet_service.reset_cache()` on settings save).

`/api/sched/solve` caches its result in module-global `_solve_cache` (key: `"YYYYMM"`) so `/api/sched/write` can use the preview without re-solving. Single-user app, so a plain dict is fine.

The 6 cumulative stat keys read from `值班總數統計` (平日/週五/週六/週日/假日) feed `cv_solver.compute_initial_targets()` to balance category counts across doctors.

### The 6-step workflow (card 3)

Each step is a `/api/step{N}/...` endpoint group in `main.py` delegating to one service module under `app/services/`. The Step → service map is the entire backend:

1. **OCR** (`ocr_service.py`) — LLM vision parses admission-list screenshot → A-L preview → diff-update write (never overwrite filled rows blindly; preserves EMR / F / G already populated).
2. **Lottery** (`lottery_service.py`) — read 主治醫師抽籤表, draw N tickets, round-robin into N-S.
3. **EMR** (`emr_service.py`) — Playwright drives the user's already-logged-in browser session (user pastes session URL); LLM summarises SOAP HTML into 4 sections. Hospital-specific selectors in `fetch_raw_html()` — default is NCKUH pattern.
4. **Ordering** (`ordering_service.py`) — read per-doctor subtables → integrate back into N-W on main sheet. `POST /api/step4/cell` is the inline-edit endpoint that backs F/G contenteditable cells.
5. **Cathlab** (`cathlab_service.py`) — `plan` (dry-run) / `verify` (cross-check WEBCVIS) / `keyin` (Phase 1 ADD + Phase 2 UPT). Static lookup tables in `app/data/static/` (`cathlab_id_maps.json`, `doctor_codes.json`, `cathlab_schedule.json`) — **never hardcode IDs in `.py`**.
6. **LINE push** (`line_service.py`) — read N-Q → preview → push to user-configured group.

Two cross-cutting services gate Steps 5–6:

- `format_check_service.py` — read-back verification + auto-fix for layout drift (headers, subtable counts, ≥2-row gap, 病歷號 TEXT format).
- `finalize_service.py` — read-only 定案 readiness checklist (D/F/I non-empty, subtable F/G complete, N-row count matches main, 改期 column shape).

### Config & bundling

`app/config.py` resolves settings in this layer order (later wins):

1. `AppConfig` dataclass defaults
2. `app/bundled/defaults.json` (Sheet IDs, base URLs — shipped in the `.exe`)
3. `app/bundled/service_account.json` (real Google SA key — `.gitignored`, copied in before `pyinstaller` runs)
4. `app/data/config.json` (per-user, written by the settings page; placed at `<exe>/user_data/` when frozen so re-builds don't wipe it)

A *user-set* field is one with a non-blank value in `config.json`; user values always beat bundled defaults. Adding a new bundle-supplied field requires updating `_BUNDLE_KEYS` and `bundled_flags()`.

Two Sheet IDs live in config:
- `cfg.sheet_id` — admission/cathlab Sheet (card 3), date tabs `YYYYMMDD`
- `cfg.schedule_sheet_id` — duty-schedule Sheet (card 1), month tabs `YYYYMM` + cumulative `值班總數統計`

Both use the same `google_creds_path`; the service account must be an editor on both sheets.

### LLM abstraction

`app/llm/__init__.py` exposes `get_llm()` (factory keyed on `cfg.llm_provider`) and `PROVIDERS` metadata. Each provider implements `LLMClient.vision()` + `LLMClient.text()` from `base.py`. `extract_json()` in `base.py` strips ```` ```json ```` fences and balances brackets — use it for every LLM JSON response, providers themselves don't parse.

### Google Sheets layer

`sheet_service.py` (admission) and `scheduling_service.py` (duty roster) are the two modules that talk to gspread. Each memoises the client + spreadsheet objects keyed on its respective Sheet ID; the `/api/settings` POST calls **both** `reset_cache()`s after any config change.

Date sheets are titled `YYYYMMDD`. Canonical layout:

- **A–L** (main data, 12 cols): 實際住院日 / 開刀日 / 科別 / 主治醫師 / 主診斷(ICD) / 姓名 / 性別 / 年齡 / 病歷號碼 / 病床號 / 入院提示 / 住急
- **N–W** (ordering, 10 cols): 序號 / 主治醫師 / 病人姓名 / 備註(住服) / 備註 / 病歷號 / 術前診斷 / 預計心導管 / 每日續等清單 / 改期
- Sub-tables below, one per doctor, title row `<doctor>（N人）`, ≥2 blank rows between sections.

Headers are the source of truth — `format_check_service.EXPECTED_MAIN_HEADER` / `EXPECTED_ORDER_HEADER` must stay in sync with `sheet_service.ensure_date_sheet`.

### Auto-update

`updater.py` polls `https://api.github.com/repos/alexdodochen/public_daily_admission_app` and `git pull --ff-only` on `apply`. Version source order: `git rev-parse HEAD` → `app/VERSION` file → "unknown". The repo constants `REPO_OWNER` / `REPO_NAME` in `updater.py` must match wherever this fork actually lives.

## Status & pending direction

**Done (2026-05-11):** 3-card home delivered. Card 1 (排班) ported from `CV-Schedulling-APP` — `cv_solver.py` + `scheduling_service.py` (renamed gsheet_io) + `schedule_gen.html` + 4 routes under `/api/sched/`. Card 3 (入院清單) moved to `/admission` route, otherwise unchanged. Card 2 (Key 班) is a disabled placeholder card.

**Still pending:**

- **Card 2 (Key 班)** — port `keyin_routes.py + keyin_scheduler.py + keyin_excel_parser.py + keyin_index.html` from `CV-Schedulling-APP` once they exist there (CV-Schedulling-APP's own home calls it "即將推出").
- **Admission rule sync** — existing `app/services/*.py` was last synced 2026-04-19. Known post-sync rule deltas not yet merged in: cathlab third doctor (recommendationDoctor), Mon EP forces 洪晨惠 as 2nd, 25 房 ROOM_CODES, EMR age from DOB (not screenshot), WEBCVIS DEL via chk-checkbox, week-scan Mon–Fri before any ADD, `_normalize_diag` angina→CAD, reschedule full-move (V mark + main copy + subtable rebuild), 詹世鴻 Friday → non-schedule, 陳則瑋+劉秉彥 OPD → attendingdoctor2=劉秉彥, 張獻元 Wed → same-day PM C2.
- **Dropped:** the 5/4 LLM-EMR-summary feature — D column stays a header placeholder, not autofilled.
- **Auth:** intentionally stripped from the 排班 port (single-user local app). Don't reintroduce login/users/audit — those belong to the server-deployed `CV-Schedulling-APP`, not this local-only app.
- **Missing static data:** `app/data/` is `.gitignored` and an empty clone has no `app/data/static/cathlab_id_maps.json` / `doctor_codes.json` / `cathlab_schedule.json`. Card 3 Step 5 will 500 until these are copied in from the private workflow repo. 26 cathlab tests fail for the same reason — pre-existing, not a regression.

## Test conventions

14 test files under `tests/`, all pure-logic (no network) — service modules are tested by monkeypatching `sheet_service` / `get_llm()`. The `test_main_endpoints.py` suite uses FastAPI `TestClient` for endpoint shape checks. When adding a new service function, add coverage there in the same pattern (mock `sheet_service.get_worksheet` to return a fake with `.get()` / `.update()` / `.update_cell()`).

`test_cv_solver.py` covers the pure scheduling surface (holiday classification, `month_h_w`, `compute_initial_targets` shape, `_qod_count` / `_scan_qod`). The full backtracking solver path is **not** unit-tested — its runtime varies wildly with baseline and can take minutes on a uniform-zero baseline. Verify solver changes through the `/sched` UI on a real month, not pytest.
