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
2. **Build sub-tables** (`subtable_service.py`) — `POST /api/step2/build_subtables` reads main A-L, groups patients by 主治醫師 in first-appearance order, writes per-doctor sub-table blocks (title `醫師（N人）` + sub-header + patient rows, ≥2-row gap between blocks). Refuses to overwrite if sub-tables already exist (preserves any user-filled F/G/E/H). **No lottery in this step** — that's Step 4. The legacy `/api/step2/run`, `/api/step2/write` lottery routes remain in `main.py` but are no longer wired to the UI.
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

Headers are the source of truth — `format_check_service.EXPECTED_MAIN_HEADER` / `EXPECTED_ORDER_HEADER` / `EXPECTED_SUB_HEADER` must stay in sync with `sheet_service.ensure_date_sheet` + `subtable_service.SUB_HEADER` + `ocr_service.SUB_HEADER` + `app.js SUB_HEADER`. The canonical SUB_HEADER labels (per `daily-admission-list-public`) are `["姓名","病歷號","EMR","EMR摘要","手動設定入院序","術前診斷","預計心導管","註記"]` — never use `summary` / `入院序` (legacy, Phase 16 cleanup).

**Sub-table H → N-V R sync (Phase 18, 2026-05-20)**: `ordering_service.integrate_ordering` + `sync_ordering_after_diff` copy sub-table H (註記) into N-V R (備註) when H is non-empty; preserve existing R when H is empty. Mirrors `daily-admission-list-public`'s canonical mapping. Q (備註住服) and V (改期) remain preserved verbatim — different workflow.

### Auto-update

`updater.py` polls `https://api.github.com/repos/alexdodochen/public_daily_admission_app` and `git pull --ff-only` on `apply`. Version source order: `git rev-parse HEAD` → `app/VERSION` file → "unknown". The repo constants `REPO_OWNER` / `REPO_NAME` in `updater.py` must match wherever this fork actually lives.

## Status & pending direction

**Delivered (Phase 22 — 2026-05-25 — sub-table I col + main-boundary + smart_rebuild + lottery rule, 448 tests):**
- **Sub-table I col 「備註(住服)」** — 8→9 cols across writers/readers; I↔Q
  mirror joins H↔R / F↔T / G↔U. Inline-editable in Step 3 EMR cards + Step 4
  sub-tables + 查閱 viewer. `_MIRROR_*` maps in ordering_service expanded;
  `lottery_with_pins` sources Q from sub I; `integrate_ordering` and
  `sync_ordering_after_diff` copy non-empty sub I over N-V Q. See updated
  [[corresponding-fields-must-mirror]].
- **Main A-L boundary detection** — `write_to_sheet` used to `read_range("A2:L200")`
  unbounded, which read sub-table rows as "existing main" → on every re-upload
  the merged main extended INTO the sub-table area, stray main-shaped rows
  interleaved with sub-tables, duplicate sub-table blocks accumulated. Now
  walks `A2:L500` and stops at first blank OR sub-table title `xxx（N人）`.
  Field bug 5/26: sheet had 2 full copies of every sub-table block + stray
  r45-46 main rows. See [[main-boundary-must-stop-at-subtable]].
- **`smart_rebuild` rescue button** — `subtable_service.smart_rebuild(date)` +
  `POST /api/step2/rebuild_subtables` + 「🔧 重建子表格」 collapsible UI on
  admission page. Reads ALL existing sub-table blocks, dedupes by 病歷號
  (longest C col wins), drops orphans + ghost blocks (doctor name = column
  header label), writes ONE block per doctor in main A-L order. Preserves
  EMR/F/G/H/I across the rewrite. Re-syncs N-V. See [[smart-rebuild-rescue-path]].
- **OCR header-row filter** — `_HEADER_LABEL_FRAGMENTS` rejects rows where
  doctor/name = column header labels (主治醫師, 姓名, 病歷號 …). LLM was
  occasionally returning the column header row as a patient → `_apply_diff_to_subtables`
  created ghost "主治醫師（0人）" blocks. Same set also filters real_subs
  in `_apply_diff_to_subtables` and the title walker in `smart_rebuild`.
- **Viewer rendering** — `/api/sheet/read` `sub.rows` now returns patient rows
  ONLY (server-side strip of title + subheader). Pre-fix the viewer rendered
  title and subheader as the first two rows of each block's table → looked
  like duplicate subheader. Added `first_patient_row` to the response;
  `subsToEmrResults` + `renderSub` use it for row arithmetic.
- **Rule 16 clarification** — `lottery_service` Rule 16 (詹世鴻 dropped from
  時段組 on Fridays) now gates on **admission day** weekday, not the
  op-day `weekday` parameter. Pre-fix the rule fired on every Thursday
  admission (op=Friday) and wrongly dropped 詹's 3 patients to 非時段 in
  5/28 lottery. New `_admission_is_friday(date)` helper. See
  [[zhan-friday-drop-is-admission-day]].
- **OCR misread map +1**: 劉獻文 → 劉嚴文 (嚴/獻 glyph collision).
- **Step 1 button text** → 「比對 → 更新主表與子表格」 + busy 「比對中…」.
- **Step 1 manual edit overlay** — `_compute_manual_edit_overlay` writes the
  cells the user fixed in the OCR table to the sheet on re-upload (was
  silently dropped by the membership-only verbatim rule). See updated
  [[ocr-reupload-membership-only]].
- **Format check +5 new issue types** — `duplicate_doctor_block`,
  `subtable_orphan_chart`, `main_chart_missing_from_subtable`,
  `subtable_doctor_not_in_main`, `subtable_doctor_mismatch`. All fixable
  via `smart_rebuild` chain in `fix()`.
- **`step2Ordered` refresh post-write** — Step 3 EMR was using stale cached
  patient list when user fixed chart_no in Step 1; now always re-reads
  `/api/step4/subtables` after a successful write.
- **Lottery axis fix** — `read_lottery_tickets` rewritten to column-major
  (sheet has 星期X header in row 1, doctors down each column with same-column
  repeats accumulating). Old row-major reader returned {} for every weekday.
  See [[reference-lottery-sheet-column-major]].
- **Tests:** 430 → 448 (+18). Repaired 5/25, 5/26, 5/28 sheets in-place via
  smart_rebuild / one-shot scripts.

**Delivered (Phase 21 — 2026-05-24 — 5/24-5/25 field-bug batch, 434 tests):**
- **Lottery sheet axis fix** — `lottery_service.read_lottery_tickets` was reading
  the sheet as row-major (A col = weekday) but the user's `主治醫師抽籤表`
  is column-major: row 1 carries `星期一/星期二/…` headers, doctors run down
  each column, repeats in same column accumulate (sheet legend). Old reader
  always returned `{}` → all doctors routed to 非時段組 → random shuffle.
  Reader rewritten to column-major; warning copy updated; tests cover both
  the real-sheet column-major fixture and the same-column repeat rule. See
  [[reference-lottery-sheet-column-major]].
- **Manual edits in Step 1 OCR table now land on sheet** — the 2026-05-19
  membership-only rule was overriding user fixes typed into the OCR table.
  JS now captures the OCR baseline as `original_rows` and sends it with
  `/api/step1/write`; `ocr_service.write_to_sheet` accepts `original_patients=`
  and runs `_compute_manual_edit_overlay` to extract cell-level edits
  (final ≠ snapshot) and overlay them on the verbatim-kept rows. Pure
  re-pastes still return `unchanged: True`. See updated
  [[ocr-reupload-membership-only]].
- **Sub-table duplicate-block dedupe** — `_apply_diff_to_subtables` rebuilt
  the doctor list from `real_subs` with `subs_by_doctor[doc] = rows` and
  `doctor_order.append(doc)` per block. When a doctor appeared in multiple
  existing blocks (sheet got duplicated by a prior bug), the dict overwrote
  earlier-block patients AND `doctor_order` carried N copies of the same
  name → rewrite emitted N duplicate titles. Fixed: merge per-doctor across
  blocks, dedupe by 病歷號, keep only the first appearance in `doctor_order`.
  Self-heals on next add/remove reconcile. 5/25 was repaired in-place via
  a one-shot script (now deleted): 4-row main → 7-row main, 8 duplicate
  陳昭佑 blocks → 1 block per doctor, all EMR/F/G/註記 preserved, N-V re-synced.
- **OCR doctor name correction** — `OCR_NAME_CORRECTIONS = {"柯星諭": "柯呈諭"}`
  applied in `ocr_image()` to `doctor` + `name` fields, strips trailing `?`/`？`
  before lookup. Extend the map when new mis-reads surface. See
  [[reference-ocr-doctor-misreads]].
- **Step 1 button text** — `寫入 Sheet A-L` → `比對 → 更新主表與子表格`,
  busy `寫入中…` → `比對中…` (reflects what the endpoint actually does).
- **Tests:** 430 → 434 (+2 lottery column-major + same-column repeats,
  +2 OCR overlay apply/noop, +1 sub-table dedupe, +3 OCR name correction).

**Delivered (Phase 20 — 2026-05-21 — bug-report screenshots + 查閱 viewer delete/sync, `aca3050` + `dfaa7ab`):**
- **🐞 回報問題 screenshot upload** — the bug-report modal gains an image picker (≤10 images, 10 MB each, thumbnail preview). `bug_report.write_report_bundle()` bundles the scrubbed report + screenshots into one `.zip` under `DATA_DIR/bug_reports/`. Screenshots attach ONLY to the private 「② 存成檔案」 path — never the public GitHub path (a screenshot renders PHI into pixels, can't be auto-scrubbed; a prefilled-issue URL can't carry attachments). `/api/bug-report/save` takes `images: list[UploadFile]`.
- **查閱 batch-delete date tabs** — 🗑 button in the viewer toolbar (admission source only). `POST /api/sheet/delete` deletes ONLY `^\d{8}$` admission date tabs; config tabs (主治醫師抽籤表/下拉選單/值班總數統計/…) and the 排班 spreadsheet are rejected 400 (server-side guardrail); the last worksheet is never deleted.
- **Live field mirror** — `ordering_service.propagate_field_edit()` mirrors 備註↔註記 / 術前診斷 / 預計心導管 between the N-V ordering block and the sub-tables on every single-cell edit, matched by 病歷號. Wired into `/api/step4/cell` AND `/api/sheet/write_cell`, so edits in Step 2/3/4 or the 查閱 viewer all stay consistent. Column number alone is ambiguous (sub F/G/H = cols 6/7/8 vs main 姓名/性別/年齡) so the edited row is validated against the real row maps.

**Delivered (Phase 19 — 2026-05-21 — 6-issue field-bug batch, GitHub #2-#7, `d7b3450`):**
- **入院序少一位** — `/api/sheet/read` sliced the N-V ordering block by `main_end` (main A-L's last row). When N-V is longer than main A-L the trailing 序號 row was cut. N-V extent is now walked independently (col N/P until blank).
- **`integrate_ordering` appends missing** — it used to only patch existing N-V rows; a sub-table patient absent from N-V is now appended (returns `appended`).
- **lottery H→R** — `首次抽籤` (`lottery_with_pins`) now carries sub-table H 註記 into N-V R 備註 (previously only ③ integrate did).
- **name cleanup** — `parse_subtables_grid` strips OCR `?` marks via `clean_name`; `integrate_ordering` refreshes P 姓名 from the (EMR-corrected) sub-table instead of keeping the stale N-V name.
- **入院序結果 備註(住服) editable** — `renderOrderResult` Q-col cell is inline-editable, synced to the Sheet on blur via `/api/step4/cell`.
- **bug-report buttons** — `.bug-actions button` inherited the global `color:#fff` on a near-white background → invisible; now solid dark.
- **cathlab verify honours 不排** — `cathlab_service.verify()` accepts `overrides` like `keyin()`; un-checking 不排 in 預覽排程 now affects 與現有排程對照.
- **main↔sub-table chart_no reconcile** — `_apply_diff_to_subtables` reconciles sub-tables against the FULL new main list by 病歷號 only: a chart already in a sub-table is never duplicated; a main chart missing from every sub-table is appended (self-heal). See [[ocr-reupload-membership-only]].

**Done (2026-05-14):** Phase 1–10 shipped. Phases 1–8 = 3-card home + Phase A/B/C admission rule backport + Phase 8 packaged distribution. Phase 9 (2026-05-13) = UI usability pass. Phase 10 (2026-05-14) = workflow re-architecture + EMR/UI overhaul.

Phase 9 highlights (`92c8458`):
- Global `📋 查閱` sheet viewer (`/api/sheet/read`) + 🔗 Sheet topbar links
- Native date picker + auto-weekday (= admission + 1, see [[feedback-weekday-field-is-op-day]] in memory)
- 資料檢查 standalone card, marked `[選用]`
- Sub-table auto-update on Step 1 OCR overwrite (`ocr_service._apply_diff_to_subtables`)
- /settings button order hint + green primary 儲存 button

Phase 10 highlights (uncommitted at time of writing):
- **Step 2 redesign** — `subtable_service.build_subtables_from_main` replaces the old lottery flow. See [[step2-no-lottery]].
- **Step 4 redesign** — `lottery_service.lottery_with_pins` with 3 independent pin layers. UI: 2× `<details>` pin panels above sub-tables. See [[pin-layers-separated]].
- **EMR fetch frame-walk** — `fetch_raw_html` rewritten for the NCKUH frameset with `FALLBACK_DOCTORS`. See [[nckuh-emr-frameset]].
- **EMR writeback** — `write_results_to_subtables` + `sheet_service.batch_write_cells`. See [[step3-must-writeback]].
- **F/G datalist** — `<input list>` combobox; custom F → OTHERS_PDI, custom G → 備註. See [[fg-combobox-not-select]].
- **Sheet viewer all-worksheets** — `/api/sheet/raw` for non-date tabs.
- **Button loading states** — `withBusy()` helper on all 14 async buttons.
- **Cache-buster** — `?v={static_version}` per-startup timestamp.
- **Gemini info on /settings** — RPM/RPD/TPM comparison table. See [[gemini-free-tier-2026]].

**Delivered (Phase 13 — 2026-05-15 evening — F/G UX overhaul + Card 1 alignment + Phase 13 misc):**
- **F/G option lists from Sheet「下拉選單」** — `sheet_service.read_fg_options_from_sheet()` reads col A (F) + col D (G) of the user-maintained `下拉選單` worksheet. `emr_service.get_fg_options()` Sheet-first, hardcoded fallback. `/api/options/fg` returns `{f, g, source}`; `/api/options/fg/refresh` for cache bust. See `feedback_fg_options_from_sheet_dropdown_tab`.
- **Custom F/G popup widget** — `<datalist>` replaced with `<span class="fg-cell">` containing input + `<button class="fg-chev">▼</button>` + `<ul class="fg-popup">`. Click ▼ → ALL options unfiltered (`open(false)`); typing → auto-open + filter (`open(true)`). Click outside or option → close. CSS specificity guard: `table.data td input.fg-input` to win against generic `table.data td input` rule. See `feedback_fg_popup_must_show_all_on_click`.
- **Sheet F/G data validation** — `sheet_service.set_fg_validation(ws, start_row, end_row, f_opts, g_opts)` sets `ONE_OF_LIST` rule with `strict=False` (allow custom values) on F/G of sub-table area. Called after sub-table build / diff / EMR writeback. Sheet's native dropdown matches the `下拉選單` worksheet content.
- **Plan-section F/G auto-detect (5/15 learning)** — ported from `daily-admission-list-public@4f7b53e`. New `extract_plan_signal()` (bottom 60 lines, procedure/admission keyword filter), `PLAN_F_RULES`, `PLAN_G_RULES`, `PLAN_G_TO_F`, `_SOFT_COMORBID_F` CAD override. `_clean_past_tense_pci` expanded to 200-char lookahead for `s/p percutaneous coronary intervention (PCI)`. Updated `extract_dx_section` to handle `* (Dx)` numbered Web EMR form. Reduced F mismatch 58→26%, G 25→16%.
- **Step 3 EMR cards inline F/G editor** — `renderEmrResults` uses `fgInput()` per row with `r.row` from sub-table lookup; saves via `/api/step4/cell`. **Bidirectional sync** with Step 4: editing in either view updates the other view's input value directly (no API refetch). See [[no-column-letters-in-ui]] for the field-name discipline.
- **EMR auto-corrects main 姓名/性別/年齡** — `apply_emr_main_fixes(date, results)` writes back to main F/G/H if EMR `emr_name/gender/age` differ. Empty EMR values don't overwrite. UI shows yellow "📝 EMR 自動更正主表 N 處" diff table.
- **Card 1 (排班) — upstream alignment with Key-Schedule-APP**:
  - `cv_solver.QOD_EXEMPT_NAMES = VS_LIST ∪ {展瀚, 建寬}` (was just 展瀚)
  - `solve_month` accepts `vs_holiday_exempt`, `prev_tail`, `seed` params
  - QOD relaxation `max_qod=0..QOD_RELAX_CAP=10`, returns minimum-violation feasible
  - `_holiday_target` + `_derive_sat_sun_caps`: total CR holiday cap (3-3-2 split when >6); sat/sun sub-caps DERIVED from holiday cap → all 3 jointly feasible
  - `compute_initial_targets` adds `cr_holiday_total / cr_weekday_total / cr_per_doctor` for UI projection
  - `random.Random(seed=None)` jitter `rng.uniform(0, 1.49)` on balance score → re-runs yield different valid schedules
  - Fast-fail when `cr_total > CR_TOTAL_CAP * len(CRS)`
  - `_compute_stats` / `_scan_qod` skip QOD count for `QOD_EXEMPT_NAMES`
- **Card 1 ↔ Card 2 handoff** — `POST /api/sched/handoff-to-keyin` reads `_solve_cache`, splits schedule into vs/cr/holidays, pushes to `keyin_routes._set_prefill()`. UI: "🔑 前往 Key 班 (帶入此月排班)" button on schedule_gen.html. Plus "🎲 重新跑 solver" button uses jitter to get alternates.
- **Prevent double-count on same-month rewrite** — `scheduling_service.read_monthly_stats()` reads existing `{YYYYMM} 班數統計` BEFORE overwriting. `update_cumulative_stats(..., previous_monthly=)` subtracts prev before adding new.
- **📂 Load existing date sheet** — green panel above Step 1 on /admission. Reads via `/api/sheet/read`, then renders main A-L into Step 1 OCR table, reverse-builds Step 3 EMR cards from sub-table A-G (including `XX y/o gender\n` prefix parse → age + gender), auto-clicks `#load4-btn`, auto-jumps to Step 4 tab.
- **📋 查閱 modal — split sources** — two source tabs (📥 每日入院清單 / 📅 排班) above the dropdown. Per source: 📋 其他工作表 (下拉選單 / 主治醫師抽籤表 / 值班總數統計) FIRST, then 📆 dates. `/api/sheet/list` returns `{admission, schedule}`; `/api/sheet/raw?source=` and `/api/sheet/write_cell?source=` route to the right spreadsheet.
- **Draft (草稿) feature** — `app/services/draft_service.py` (file-based JSON under `<user_data>/drafts/<bucket>/`); endpoints `/api/draft/{bucket}/save|list|load|delete` for `bucket ∈ {sched, keyin}`. Both `schedule_gen.html` + `keyin.html` get a 💾 草稿 panel.
- **操作說明 modal — tabbed** — base.html `#help-modal` now has 3 tabs (🩺 入院 / 📅 排班 / 🔑 Key 班), auto-picks initial tab based on current page URL.
- **Settings: LINE Bot tutorial** — `<details>` "沒有 LINE Bot？點這裡看怎麼建立" with full Messaging API setup walkthrough.
- **Step 4 button differentiation** — yellow ② "首次抽籤 + 寫入入院序 (會清掉備註住服/改期)" + green ③ "整合寫入入院序 (保留備註住服/改期)" + foldable 流程說明 details. All copy uses Chinese field names — no F/G/N-V/Q/V/T/U letter codes anywhere user-facing.
- **Watermark** — fixed bottom-right `此系統由 114 級 NCKUH CV 陳常胤醫師 與 Claude Code 合作開發` (semi-transparent, all pages, hidden in print).
- **Step 2 panel hidden** — `style="display:none"` + removed from stepper. `step1Write()` auto-calls `/api/step2/build_subtables` after main A-L write succeeds (idempotent: server refuses if sub-tables already exist). Stepper renumbered: ① 匯入名單 / ② EMR 擷取 / ③ 入院序整合 / ④ 導管排程 / ⑤ LINE 推播.
- **Tests**: 320 → 331. New: `get_fg_options` 2 cases, `apply_emr_main_fixes` 3 cases, plan-section detect 5 new + 1 updated for plan PCI override.

**Delivered (Phase 12 — 2026-05-15 same-day field-test fixes):**
- **Chart-no TEXT format proactive** — `sheet_service.ensure_chart_text_format(ws)` covers main I (col 8), order S (col 18), sub-table B (col 1) over rows 2..500. Called from `ensure_date_sheet` AND defensively before every chart-writing path. Stops USER_ENTERED parsing from silently stripping leading zeros. See memory `feedback_sheet_writes_must_text_format_chart`.
- **EMR fetch hardened** — `emr_service.fetch_raw_html` rewritten with `window.frames['topFrame'|'leftFrame'|'mainFrame']` named accessors (NOT iterate-all-frames), sentinel-stamp body + 12s polled wait, `div.small` extraction restricted to mainFrame only. New helper `is_index_page_boilerplate()` + `INPATIENT_ONLY_TEXT` mark inpatient-only patients clearly when fetch lands on chart-summary index page (`住院資料量較大,請點選個別項目後瀏覽`). Added `NAME_ALIASES` for 林佳凌 / 林佳淩 Unicode siblings. Reference impl: `每日入院名單 Claude\fetch_emr.py`.
- **EMR writeback auto-builds sub-tables** — `write_results_to_subtables` calls `subtable_service.build_subtables_from_main(date)` when no sub-tables exist, then writes C/F/G. UI now shows `（已自動建立子表格）` in the success message and surfaces `wb.error` if write failed.
- **Lottery overwrites trailing rows** — `lottery_service.lottery_with_pins` reads pre-existing N-V length, then `clear_range` the tail if new is shorter. Returns `cleared_trailing: N`.
- **Editable 📋 查閱 viewer** — `POST /api/sheet/write_cell` (any worksheet, 1-indexed row/col). JS adds `contenteditable="true"` + `data-row`/`data-col` to every viewer cell; blur or Enter commits. Visual feedback: hover=yellow / focus=indigo / saving=blue / saved=green / error=red.
- **OCR auto-fills #date-input** — Step 1 picks the most-common `admit_date` from OCR rows (accepts `YYYY/MM/DD`, `YYYY-MM-DD`, `MM/DD` + current year, `YYYYMMDD`), populates the date input and dispatches `change` to sync weekday + native date-picker.
- **Unified topbar** — `schedule_gen.html` + `keyin.html` now `{% extends "base.html" %}`. New `{% block head_extras %}` in base.html for Tailwind CDN. Sub-pages set `tailwind.config = {corePlugins:{preflight:false}}` to preserve base.html topbar styling. `keyin_routes.keyin_index` passes `cfg` + `ready` + `static_version` (required by base.html). See `feedback_all_pages_share_topbar`.

**Delivered (Phase 11 — 2026-05-15 pending-list cleanup):**
- **Card 2 (Key 班)** — ported from `https://github.com/alexdodochen/Key-Schedule-APP`. New modules: `app/services/keyin_scheduler.py`, `app/services/keyin_excel_parser.py`, `app/services/keyin_routes.py` (APIRouter mounted at `/keyin`). New template `app/templates/keyin.html`. Auth + audit stripped per `feedback-strip-auth-for-local-ports`. `ConnectionManager` + `SchedulerSession` drive the Playwright EDR keyin; `build_schedule_from_config` is the deterministic schedule builder. New deps: `openpyxl`, `xlrd`. `home.html` Card 2 now links to `/keyin` (no more `即將推出` badge); topbar `base.html` gets a `Key 班` nav entry.
- **N-V auto-rebuild on OCR diff** — new `ordering_service.sync_ordering_after_diff(date)`. After `_apply_diff_to_subtables` succeeds, `ocr_service.write_to_sheet` calls it: drops rows for charts no longer in sub-tables, appends new rows in main-table doctor order × within-doctor sub-table order, refreshes O (主治醫師) + T/U from sub-tables, preserves Q (住服) + R + V (改期) verbatim, renumbers 序號. **Never re-randomises** — least-surprise rebuild.
- **Auto-create sub-table for new doctor** — `_apply_diff_to_subtables` now has an `_ensure_doctor(doc)` helper. Patients added/moved with a doctor lacking a sub-table cause a new block (title + SUB_HEADER + patient rows) to be appended after the existing blocks, with the standard 2-row gap. Old `unattached_added`/`unattached_changed` paths only fire now when the new doctor name is itself blank. New `auto_created_doctors: [str]` field in the result.
- **Static data setup documented** — the 3 files `app/data/static/cathlab_id_maps.json`, `doctor_codes.json`, `cathlab_schedule.json` are still under `.gitignore` (PHI hygiene — don't commit doctor codes / chart-no maps to a public repo). For a fresh clone, regenerate them as follows: copy `cathlab_id_maps.json` from `C:\Users\dr\Downloads\Y\每日入院名單 Claude\`; transcribe `doctor_codes.json` from the `DOCTOR_CODES` + `ROOM_CODES` dicts in `cathlab_keyin.py` (top of file in the same private dir); transcribe `cathlab_schedule.json` from the `_dump_schedule.txt` grid (Mon-Fri × AM/PM × H1/H2/C1/C2; weekday keys are str("0".."4")). Once present, the cathlab tests pass — suite size went from 294 to 316 with the new Phase 11 tests included.

**Still pending:**
- **Dropped:** the 5/4 LLM-EMR-summary feature — D column stays a header placeholder, not autofilled.
- **Auth:** intentionally stripped from the 排班 port and from the Key 班 port (single-user local app). Don't reintroduce login/users/audit — those belong to the server-deployed source repos, not this local-only app.

## Test conventions

17 test files under `tests/`, all pure-logic (no network) — service modules are tested by monkeypatching `sheet_service` / `get_llm()`. The `test_main_endpoints.py` suite uses FastAPI `TestClient` for endpoint shape checks. When adding a new service function, add coverage there in the same pattern (mock `sheet_service.get_worksheet` to return a fake with `.get()` / `.update()` / `.update_cell()`).

`test_cv_solver.py` covers the pure scheduling surface (holiday classification, `month_h_w`, `compute_initial_targets` shape, `_qod_count` / `_scan_qod`). The full backtracking solver path is **not** unit-tested — its runtime varies wildly with baseline and can take minutes on a uniform-zero baseline. Verify solver changes through the `/sched` UI on a real month, not pytest.
