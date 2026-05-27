# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository identity

This is **`daily_admission_list_app`** (public on GitHub) — ships as a double-clickable `.exe` to each year's incoming 行政總醫師. All UI/feature work happens here.

`app/VERSION` records the sha. The sibling private repos (`daily-admission-list`, `Key-Schedule-APP`, `CV-Schedulling-APP`) are reference only — port code by copying in, never edit upstream.

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
# Output: dist/行政總醫師.排班.Key班.入院/行政總醫師.排班.Key班.入院.exe (onedir)
# Release asset is ASCII admission-app.zip (non-ASCII → action-gh-release "default.zip")
```

There is no `.github/workflows/` directory in this clone — README mentions a `pytest.yml` CI but it is not present here; verify before referencing CI in commits.

## Architecture

### Runtime shape

FastAPI (`app/main.py`) + uvicorn launched by `app/run.py`, which opens the browser after a 1s delay. Jinja2 templates (`app/templates/`), no JS framework — inline `app/static/app.js` only. Single-user, no concurrency locks.

### 3-card home

`/` renders `home.html` (a card grid). The three cards:

- **`/sched`** — Card 1, 排班. Renders `schedule_gen.html` (self-contained Tailwind page, doesn't extend `base.html`). Drives a 5-step UI against `/api/sched/{init,compute,solve,write}`.
- **`/keyin`** — Card 2, Key 班. Ported from `Key-Schedule-APP` (2026-05-15). APIRouter at `/keyin/api/*` for Excel upload / preview / start / continue / cancel / status / ws. Drives Playwright against `web.hosp.ncku.edu.tw/edr/login` to auto-fill the EDR shift grid.
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

1. **OCR** (`ocr_service.py`) — LLM vision parses admission-list screenshot → A-L preview → diff-update write (never overwrite filled rows blindly; preserves EMR / F / G already populated). On overwrite, `_apply_diff_to_subtables` also reconciles existing per-doctor sub-tables: removed rows dropped, doctor-changed rows moved (E cleared on move), added rows appended to their A-L doctor's sub-table. Patients whose doctor has no existing sub-table are reported as `unattached_added` / `unattached_changed`, never silently dropped.
2. **Build sub-tables** (`subtable_service.py`) — `POST /api/step2/build_subtables` reads main A-L, groups patients by 主治醫師 in first-appearance order, writes per-doctor sub-table blocks (title `醫師（N人）` + sub-header + patient rows, ≥2-row gap between blocks). Refuses to overwrite if sub-tables already exist (preserves any user-filled F/G/E/H/I). `POST /api/step2/rebuild_subtables` (`smart_rebuild`) is the rescue path that rewrites all blocks deduped by 病歷號. **No lottery in this step** — that's Step 4.
3. **EMR** (`emr_service.py`) — Playwright drives the user's already-logged-in browser session (user pastes session URL); extracts SOAP + `divUserSpec`. NCKUH-specific frame walk: `#txtChartNo` + `#BTQuery` in topFrame, clinic visit anchors in leftFrame, `div.small` SOAP in mainFrame. Falls back to `FALLBACK_DOCTORS = ['劉秉彥','趙庭興','蔡惟全','許志新','陳柏升','李貽恒']` when the assigned 主治醫師 has no 一年內門診紀錄. **Endpoint MUST call `write_results_to_subtables(date, results)` to persist C/F/G back to the sheet** — returning to the UI alone is a bug.
4. **Lottery + Ordering** (`lottery_service.py` + `ordering_service.py`) — three independent pin layers (see [[pin-layers-separated]]):
   - **`POST /api/step4/lottery`** runs `lottery_with_pins(date, weekday, patient_pins, doctor_pins)`:
     - L1: sub-table E col → within-doctor sort (`sort_by_manual_e`).
     - L2: `patient_pins` `{chart_no: seq}` → forces a patient to global 序號 N.
     - L3: `doctor_pins` `{doctor: rank}` → forces a doctor to be N-th in RR draw order.
     - Returns 400 on duplicate / out-of-range pin values.
   - **`POST /api/step4/integrate`** re-runs `ordering_service.integrate_ordering(date)` — preserves existing N-V (Q 住服 / V 改期) while patching T/U from current sub-table F/G + re-applying L1 sort.
   - **`POST /api/step4/cell`** is the inline-edit endpoint for any sub-table cell (used by both the editable-pin E col and the F/G datalist inputs).
5. **Cathlab** (`cathlab_service.py`) — `plan` (dry-run) / `verify` (cross-check WEBCVIS) / `keyin` (Phase 1 ADD + Phase 2 UPT). Static lookup tables in `app/data/static/` (`cathlab_id_maps.json`, `doctor_codes.json`, `cathlab_schedule.json`) — **never hardcode IDs in `.py`**. `resolve_diag` falls back to `OTHERS_PDI = "PDI20090908120008"` for any unresolved text so user-typed F values still key into WEBCVIS (under "OTHERS" with the label as free text). `resolve_proc` returns `("","")` for unresolved G → existing logic appends the cath text to `note_out` (WEBCVIS 備註).
6. **LINE push** (`line_service.py`) — read N-Q → preview → push to user-configured group.

Two cross-cutting services gate Steps 5–6:

- `format_check_service.py` — read-back verification + auto-fix for layout drift (headers, subtable counts, ≥2-row gap, 病歷號 TEXT format).
- `finalize_service.py` — read-only 定案 readiness checklist (D/F/I non-empty, subtable F/G complete, N-row count matches main, 改期 column shape).

### Read-only sheet viewer (global)

Two endpoints, one modal:
- `GET /api/sheet/read?date=YYYYMMDD` — date sheet view (structured: main A-L + ordering N-W + per-doctor sub-tables via `format_check_service.parse_structure`).
- `GET /api/sheet/raw?name=<tab>` — generic A:Z read for any non-date tab (主治醫師抽籤表 / 值班總數統計 / 改期清單…).

The `📋 查閱` topbar link opens the viewer modal; the dropdown groups options into "日期分頁 (YYYYMMDD)" + "其他工作表" via JS (`isYmd()` check). Topbar also has `🔗 入院 Sheet` / `🔗 排班 Sheet` links that open the live Google Sheet in a new tab (only render if respective `cfg.*_sheet_id` is set).

### Step 4 pin storage (browser-local)

The patient and doctor pin panels persist to `localStorage[pin_YYYYMMDD]` so reloading the page keeps the user's input. Pin state is NOT synced to the sheet — it's a per-browser, per-day, transient layer that the lottery endpoint consumes once per run. Sub-table E col is the only pin layer that touches the sheet.

### Cache-buster for static assets

`_STATIC_VERSION = str(int(time.time()))` is set once per server startup and injected into every template context as `static_version`. `base.html` references `/static/app.css?v={{ static_version }}` and `/static/app.js?v={{ static_version }}` so browsers reload the bundle on every restart — no need for `Ctrl+F5`.

### Button loading states

Every async click handler in `app.js` wraps its body with `await withBusy(btn, busyText, async () => {...})`. The helper disables the button, swaps its text to `busyText`, adds `class="busy"` (orange background + spinning border via CSS), then restores on `finally`. Apply to any new async button.

### F/G combobox container invariant

`fgInput()` emits a `<ul class="fg-popup">` inside its `<span class="fg-cell">`. **Never wrap an `fgInput()` in a `<p>`** — the HTML parser auto-closes `<p>` at the first `<ul>`, hoisting the popup out of its `.fg-cell` so `wireFgInputsIn` bails (`if (!popup) return`) and that combobox's ▼ goes dead (regressed F in Step 3 EMR cards, fixed 2026-05-17 `a7fa372`). Use `<div>`/`<td>` as the container. Step 4 sub-table uses `<td>` (valid); Step 3 EMR cards use `<div class="emr-fg-row">`.

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

Headers are the source of truth — `format_check_service.EXPECTED_MAIN_HEADER` / `EXPECTED_ORDER_HEADER` / `EXPECTED_SUB_HEADER` must stay in sync with `sheet_service.ensure_date_sheet` + `subtable_service.SUB_HEADER` + `ocr_service.SUB_HEADER` + `app.js SUB_HEADER`. Canonical SUB_HEADER (9 cols): `["姓名","病歷號","EMR","EMR摘要","手動設定入院序","術前診斷","預計心導管","註記","備註(住服)"]`.

**Sub-table mirror to N-V (`ordering_service`)** — H 註記 → R 備註; I 備註(住服) → Q; F 術前診斷 → T; G 預計心導管 → U. Empty sub-table cells preserve existing N-V. V (改期) is preserved verbatim. `propagate_field_edit` keeps both sides in sync on every single-cell edit.

### Auto-update

`updater.py` polls `https://api.github.com/repos/alexdodochen/daily_admission_list_app` (constants `REPO_OWNER` / `REPO_NAME` at top of file) and `git pull --ff-only` on `apply`. Version source order: `git rev-parse HEAD` → `app/VERSION` file → "unknown".

## Status

Current state lives in git log + `memory/MEMORY.md`; this section keeps only
the load-bearing invariants the codebase relies on.

**Sub-table 9-col layout**: `["姓名","病歷號","EMR","EMR摘要","手動設定入院序","術前診斷","預計心導管","註記","備註(住服)"]`. Cols F/G/H/I mirror N-V T/U/R/Q via `ordering_service` (`integrate_ordering`, `sync_ordering_after_diff`, `propagate_field_edit`). Q (住服) / R (備註) preserved when sub I/H empty; V (改期) preserved verbatim.

**Main A-L boundary**: `_apply_diff_to_subtables` walks `A2:L500` and stops at first blank OR sub-table title `xxx（N人）`. Never read `A2:Lnnn` unbounded — sub-table rows would be misread as main.

**Smart rebuild rescue**: `subtable_service.smart_rebuild(date)` + `POST /api/step2/rebuild_subtables` rewrites blocks deduped by 病歷號, drops orphans + ghost blocks (doctor name = column-header label, filtered via `_HEADER_LABEL_FRAGMENTS`). Preserves EMR/F/G/H/I; re-syncs N-V.

**Lottery rule 16** (詹世鴻): on Friday **admission** day (not op day) he's dropped from 時段組 to 非時段組. `_admission_is_friday(date)` gates the rule.

**Lottery sheet axis**: `主治醫師抽籤表` is column-major — row 1 = 星期X header, doctors run DOWN each column, same-column repeats accumulate. `read_lottery_tickets` matches via `_normalize_weekday_label` (whitespace/punct-insensitive, folds 星期X↔週X).

**OCR re-upload is membership-only**: chart_no determines diff. Doctor changes never propagate; only A-L overlay carries user-typed cell edits (`_compute_manual_edit_overlay`).

**FALLBACK_DOCTORS** for EMR: when the assigned 主治醫師 has no 一年內門診紀錄, fall through `_load_cv_doctor_pool()` (unions `doctor_codes.json` + hardcoded floor).

## Test conventions

23 test files under `tests/` (445 tests), all pure-logic (no network) — service modules are tested by monkeypatching `sheet_service` / `get_llm()`. The `test_main_endpoints.py` suite uses FastAPI `TestClient` for endpoint shape checks. When adding a new service function, add coverage there in the same pattern (mock `sheet_service.get_worksheet` to return a fake with `.get()` / `.update()` / `.update_cell()`).

`test_cv_solver.py` covers the pure scheduling surface (holiday classification, `month_h_w`, `compute_initial_targets` shape, `_qod_count` / `_scan_qod`). The full backtracking solver path is **not** unit-tested — its runtime varies wildly with baseline and can take minutes on a uniform-zero baseline. Verify solver changes through the `/sched` UI on a real month, not pytest.
