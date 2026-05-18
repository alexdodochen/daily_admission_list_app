---
name: 3-card app integration state
description: Current state of the daily_admission_list_app — what's delivered, what's pending in the CV_APP 3-card consolidation
type: project
originSessionId: 72454ca2-3f8b-459c-b668-ba750a7a2e97
---
This repo (`daily_admission_list_app`, cloned at `C:\Users\dr\Downloads\Y\排班 Key班 DayList APP`) is the **public integration target** for a 3-card home (排班 / Key班 / 入院清單).

State as of 2026-05-18 (Phase 14 — Card 1 full UI port from Key-Schedule-APP + Step 5 manual edit + exe delivery):

**Delivered (Phase 14 — 2026-05-18):**
- **Card 1 UI fully ported from Key-Schedule-APP** (was: solver aligned but UI/endpoints didn't surface it). `scheduling_service.previous_year_month` + `read_calendar_tail` (local calendar layout byte-identical to upstream → parser reused verbatim). `/api/sched/init` returns `prev_tail`+`prev_year/month`; `/api/sched/compute` forwards `vs_holiday_exempt`; `/api/sched/solve` forwards `prev_tail`+`vs_holiday_exempt`, caches `targets`, returns `projected_cumulative` (baseline−prev+new per cell) + `cr_holiday_target`. `_build_projection()` shared helper. UI: 上月末跨月限制 box, VS 不值假日 checkboxes (toggle → recompute), CR 預估表, 寫入後預估值班總數統計 table.
- **Step 5 manual schedule edit** (Key-Schedule-APP `7b6ccf4`, the LAST sync from that repo). `cv_solver.recompute_from_schedule()` pure fn (same classification as solver). `POST /api/sched/apply-edits` overwrites cache so write/handoff emit edited result. UI: every calendar cell → editable `<select>`, changed cells amber, `✎ 套用手調並重算` / `↺ 還原 solver 原班`, edit-aware QOD banner, draft stores revert point.
- **schedule_gen.html ported verbatim from upstream** + local infra re-applied: `extends base.html`, IIFE-scoped `$` (see [[feedback-subpage-iife-scope]]), draft fns rewired to local `/api/draft/sched/*`, dropped dup watermark. `.day-btn.selected` restored to solid indigo + white (upstream's rgba 0.40 was too faint — user correction).
- **exe built + delivered** — `pyinstaller packaging.spec` → `dist/每日入院名單/每日入院名單.exe` (onedir, 882MB w/ bundled Chromium + SA). Zipped (Windows `tar.exe`, NOT Git Bash tar — that treats `C:/` as remote host) to `C:\Users\dr\Downloads\Y\每日入院名單 for 麒翔.zip` (380MB, outside repo). exe boots + bundled SA connects to Sheet (verified).
- **Sync source cutover** — Key-Schedule-APP no longer pulled from; future updates only from `daily_admission_list_app`. See [[feedback-card1-sync-source-cutover]].
- **Tests**: 335/335 (unchanged count — recompute_from_schedule/apply-edits not yet unit-tested; pure-logic candidates for next session).
- Commits: `7a94419` (/sched $ collision fix), `101f0f1` (Card 1 port + Step 5). Both pushed to `daily_admission_list_app` main.

State as of 2026-05-15 (Phase 13 — same-day field-test + upstream-alignment burst):

**Delivered (Phase 13):**
- **F/G dropdown sourced from Sheet「下拉選單」worksheet** — `sheet_service.read_fg_options_from_sheet()` reads col A (術前診斷) + col D (預計心導管) from the user-maintained `下拉選單` tab (55 F + 22 G in current sheet). `emr_service.get_fg_options()` reads Sheet first, falls back to `DIAG_RULES`/`CATH_RULES` outputs. Cached for the session, busted via `reset_cache()`. Endpoint `POST /api/options/fg/refresh` for explicit refresh. See [[fg-options-from-sheet-dropdown-tab]].
- **Custom F/G popup (no native datalist)** — `<datalist>` autocomplete UX was non-discoverable (popup only opens on typing or arrow keys). Replaced with `<span class="fg-cell">` containing input + `<button class="fg-chev">▼</button>` + `<ul class="fg-popup">`. Click ▼ → `open(false)` shows ALL options unfiltered; typing → `open(true)` filters by current value. Click outside closes. See [[fg-popup-must-show-all-on-click]].
- **Step 3 EMR cards F/G inline editor** — `renderEmrResults` uses `fgInput()` per row with `r.row` from sub-table lookup; saves via `/api/step4/cell` and live-refreshes Step 4 view. Backend `/api/step3/run` now enriches each result with `row` from `ordering_service.read_doctor_subtables`.
- **EMR auto-corrects main 姓名/性別/年齡** — `emr_service.apply_emr_main_fixes(date, results)` writes back to main F/G/H if EMR `emr_name/gender/age` differ. Empty values from EMR don't overwrite. UI shows yellow "📝 EMR 自動更正主表 N 處" table with old → new diffs.
- **Plan-section F/G auto-detect (5/15 learning)** — ported from `daily-admission-list-public@4f7b53e`. New `extract_plan_signal()` (bottom 60 lines, procedure/admission keyword filter), `PLAN_F_RULES`, `PLAN_G_RULES`, `PLAN_G_TO_F`, `_SOFT_COMORBID_F` CAD override (Unstable/Angina/Syncope/VPC/CHF → CAD if CAD keyword present in Dx). Key insight: G is cath-lab BOOKING slot, not procedure outcome (`plan PCI` → Left heart cath., not PCI). `_clean_past_tense_pci` expanded to allow 200 chars between `s/p` and `PCI` (catches `s/p percutaneous coronary intervention (PCI)`). Reduced F mismatch 58→26%, G 25→16% on the 248-row training corpus. Updated `extract_dx_section` to handle the new Web EMR `* (Dx)` numbered form.
- **Sheet F/G data validation** — `sheet_service.set_fg_validation(ws, start_row, end_row, f_opts, g_opts)` sets `ONE_OF_LIST` rule with `strict=False` (allow custom values) on F/G of sub-table area. Called from `subtable_service.build_subtables_from_main`, `ocr_service._apply_diff_to_subtables`, and `emr_service.write_results_to_subtables`. Sheet now has native dropdown matching the Sheet's own `下拉選單` worksheet content.
- **📂 Load existing date sheet** — green panel above Step 1 on /admission. Picks any existing `YYYYMMDD` tab from a dropdown (defaults today), reads via `/api/sheet/read`, then: (a) renders main A-L into editable Step 1 OCR table, (b) `subsToEmrResults()` reverse-builds Step 3 EMR cards from sub-table A-G + parses `XX y/o gender\n` prefix from c_text, (c) auto-clicks `#load4-btn` to populate Step 4 sub-tables, (d) auto-jumps to Step 4 tab so the rendered view is visible (otherwise hidden behind active panel).
- **Card 1 ↔ Card 2 handoff** — new `POST /api/sched/handoff-to-keyin` reads `_solve_cache`, splits schedule into vs/cr/holidays, pushes to `keyin_routes._set_prefill()`. Schedule_gen.html "🔑 前往 Key 班 (帶入此月排班)" button calls it then redirects to /keyin which consumes the prefill once.
- **Card 1 prevent double-count on rewrite** — `scheduling_service.read_monthly_stats()` reads existing `{YYYYMM} 班數統計` tab. `update_cumulative_stats()` accepts `previous_monthly=` param; subtracts prev before adding new so re-running same month doesn't double in 值班總數統計. `/api/sched/write` reads BEFORE overwriting and passes through.
- **Card 1 solver upgrades** — `cv_solver` ported from upstream Key-Schedule-APP:
  - `QOD_EXEMPT_NAMES = VS_LIST ∪ {展瀚, 建寬}` (was just 展瀚)
  - `vs_holiday_exempt` param: VS who skip all holidays this month, slots redistributed to CR
  - `prev_tail` param: cross-month back-to-back / QOD boundary check via `neighbor_doctor()` helper
  - QOD relaxation: tries `max_qod=0..QOD_RELAX_CAP=10`, returns minimum-violation feasible (was binary strict→relaxed)
  - `_holiday_target` + `_derive_sat_sun_caps`: total CR holiday cap (3-3-2 split when >6 holidays); 週六/週日 sub-caps DERIVED from holiday cap so all 3 are jointly feasible
  - `compute_initial_targets` returns `cr_holiday_total / cr_weekday_total / cr_per_doctor` for UI projection
  - Fast-fail when `cr_total > CR_TOTAL_CAP * len(CRS)` (avoids minutes in QOD relax loop)
  - `random.Random(seed=None)` jitter `rng.uniform(0, 1.49)` on balance score → re-running solver yields different valid schedules. UI: "🎲 重新跑 solver (取得不同班表)" button.
  - `_compute_stats` / `_scan_qod` skip QOD count for `QOD_EXEMPT_NAMES`
- **📋 查閱 modal — split sources** — added two source tabs (📥 每日入院清單 / 📅 排班) above the dropdown. Per source: 📋 其他工作表 (下拉選單 / 主治醫師抽籤表 / 值班總數統計 / etc.) shown FIRST, then 📆 date / month sheets. `/api/sheet/list` returns `admission` + `schedule` arrays; `/api/sheet/raw?source=` routes to the right spreadsheet. `/api/sheet/write_cell?source=` likewise for inline edits.
- **Draft (草稿) feature** — single `draft_service.py` (file-based JSON under `<user_data>/drafts/<bucket>/`); endpoints `/api/draft/{bucket}/save|list|load|delete` for `bucket ∈ {sched, keyin}`. Both `schedule_gen.html` + `keyin.html` get a 💾 草稿 panel: name input + 存 / 載入 / 刪 / dropdown.
- **操作說明 modal tabbed** — base.html now has 3 tabs (🩺 入院 / 📅 排班 / 🔑 Key 班), auto-picks initial tab based on current page URL.
- **Settings: LINE Bot tutorial** — `<details>` "沒有 LINE Bot？點這裡看怎麼建立" with full Messaging API setup walkthrough (provider/channel/access token/group_id via webhook.site).
- **Step 4 button clarification** — yellow ② "首次抽籤 + 寫入入院序 (會清掉備註住服/改期)", green ③ "整合寫入入院序 (保留備註住服/改期)" + foldable 流程說明 details. All copy uses Chinese field names instead of letter codes (no more F/G/N-V/Q/V/T/U).
- **Watermark** — fixed bottom-right `此系統由 114 級 NCKUH CV 陳常胤醫師 與 Claude Code 合作開發` (semi-transparent, all pages, removed from print).
- **EMR 主表 / 子表格自動建子表格** — `write_results_to_subtables` calls `subtable_service.build_subtables_from_main(date)` if no sub-tables exist. Auto-creates sub-table for new doctor on OCR diff (`_apply_diff_to_subtables._ensure_doctor`).
- **Tests**: 320 → 331. New: `get_fg_options` 2 cases, `apply_emr_main_fixes` 3 cases, plan-section detect (5 new + 1 updated for plan PCI override).

State as of 2026-05-15 (Phase 12):

**Delivered (Phase 12 — 2026-05-15 same-day field-test fixes):**
- **Chart-no TEXT format proactive** — `sheet_service.ensure_chart_text_format(ws)` runs on `ensure_date_sheet` and before every chart-writing path (OCR, sub-table build, sub-table diff, lottery, EMR writeback, viewer cell write). Stops USER_ENTERED parsing from eating leading zeros. See [[sheet-writes-must-text-format-chart]].
- **EMR fetch hardened** — `fetch_raw_html` rewritten with named frames (`window.frames['topFrame'|'leftFrame'|'mainFrame']`), sentinel-stamped body wait (12s max), and **mainFrame-only** `div.small` extraction. Drops the bug where leftFrame's chart-summary index ("住院資料量較大,請點選個別項目後瀏覽") was being read as SOAP. New helper `is_index_page_boilerplate()` + `INPATIENT_ONLY_TEXT` mark inpatient-only patients clearly. Added `NAME_ALIASES = {"林佳凌": ["林佳凌","林佳淩"], "林佳淩": ["林佳凌","林佳淩"]}`. See updated [[nckuh-emr-frameset]].
- **EMR writeback auto-builds sub-tables** — when `write_results_to_subtables` finds no sub-tables, it calls `subtable_service.build_subtables_from_main(date)` first, then writes C/F/G. UI message shows "（已自動建立子表格）". `wb.error` now surfaced in the JS message.
- **Lottery overwrites trailing rows** — `lottery_with_pins` reads existing N-V length before write, then `clear_range` the tail if new shorter. Returns `cleared_trailing: N` in result. User: "再生成新的住院序 你要覆寫入院序列".
- **Editable sheet viewer** — `POST /api/sheet/write_cell` lets the 📋 查閱 modal commit any cell edit straight to Google Sheet. JS adds `contenteditable="true"` + `data-row`/`data-col` to every cell; blur or Enter triggers write. Visual: hover=yellow / focus=indigo / saving=blue / saved=green (fades) / error=red (reverts).
- **OCR auto-fills #date-input** — Step 1 picks most-common `admit_date` across rows (accepts `YYYY/MM/DD`, `YYYY-MM-DD`, `MM/DD` with current year, raw `YYYYMMDD`), populates the date input and dispatches `change` so weekday + native date-picker sync.
- **Unified topbar via extends base.html** — `schedule_gen.html` + `keyin.html` now `{% extends "base.html" %}`. Tailwind preflight disabled via `tailwind.config = {corePlugins:{preflight:false}}` so base.html topbar styles survive. New `{% block head_extras %}` in base.html for page-specific head injection. `keyin_routes.keyin_index` passes `cfg` + `ready` + `static_version` (base.html needs all 3). See [[all-pages-share-topbar]].

State as of 2026-05-15 (earlier in session):

**Delivered (Phase 11 — 2026-05-15 pending-list cleanup):**
- **Card 2 (Key 班) ported** from `https://github.com/alexdodochen/Key-Schedule-APP`. Modules: `app/services/keyin_scheduler.py` + `keyin_excel_parser.py` + `keyin_routes.py` (APIRouter mounted at `/keyin`); template `app/templates/keyin.html`. Auth + audit stripped. `home.html` Card 2 enabled; `base.html` topbar gets `Key 班` link. Deps: `openpyxl`, `xlrd`. 22 new tests in `test_keyin_*.py`.
- **N-V auto-rebuild on OCR diff** — `ordering_service.sync_ordering_after_diff(date)` called by `ocr_service.write_to_sheet` after sub-table update. Drops removed, appends added (preserves Q/V markers keyed by chart_no), refreshes O/T/U from sub-tables, renumbers 序號. Never re-randomises. 4 new tests in `test_ordering_service.py`.
- **Auto-create sub-table for new doctor** — `_apply_diff_to_subtables` gets `_ensure_doctor(doc)` helper. Patients added/moved to a doctor lacking a sub-table now create a new block at the end (title + SUB_HEADER + rows, 2-row gap). Result has new `auto_created_doctors: [str]` field; `unattached_*` only fires when new doctor name is blank. 2 new tests in `test_ocr_service.py`.
- **Static data shipped** — `app/data/static/cathlab_id_maps.json` (from `C:\Users\dr\Downloads\Y\每日入院名單 Claude\`), `doctor_codes.json` (transcribed from cathlab_keyin.py constants), `cathlab_schedule.json` (transcribed from `_dump_schedule.txt`). Previously-failing ~35 cathlab tests now pass. Total suite 294 → 316.
- **2 stale resolve_diag tests updated** — `test_resolve_diag_unknown` (test_cathlab_service.py) + `test_resolve_diag_unknown_still_empty` (test_cathlab_enrich_plan.py) were asserting the pre-OTHERS-fallback behaviour. Now updated to expect `(Others:<text>, OTHERS_PDI)` per `feedback_others_diag_freetext.md`.

State as of 2026-05-13:

**Delivered (Phase 1–8):**
- Card 1 (排班) — ported from local `CV-Schedulling-APP` clone (commit `e5fb122`). Routes: `/sched` + `/api/sched/{init,compute,solve,write}`. Modules: `app/services/cv_solver.py` + `app/services/scheduling_service.py` (Sheet I/O via `cfg.schedule_sheet_id`).
- Card 3 (入院清單) — original 6-step admission flow at `/admission` (template renamed `index.html` → `admission.html`). Phase A/B/C backported from origin:
  - **Phase A** (`d784152`) — admission rule deltas: cathlab third doctor, Mon EP forces 洪晨惠, 25 房 ROOM_CODES, EMR age from DOB, WEBCVIS DEL via chk-checkbox, week-scan Mon-Fri before ADD, `_normalize_diag` angina→CAD, reschedule full-move, etc.
  - **Phase B** (`85c8d51`) — `reschedule_service.py` + WEBCVIS DEL + verify_main_emr
  - **Phase C** (`5852983`) — packaged .exe distribution + in-app help modal + `install.bat`/`start.bat`/`packaging.spec`
- **Distribution pipeline** (`fd9b465`) — in-app self-update + GitHub Actions auto-release. `app/services/updater.py` + `sync_manifest.py`.
- **Multi-source upstream check** (`a1f3d3a`) — `app/services/upstream.py` polls 3 GitHub repos at startup.
- 3-card home page at `/`, custom CSS (not Tailwind).

**Delivered (Phase 9 — 2026-05-13 UI usability pass):**
- **Global sheet viewer** — topbar `📋 查閱` link opens a modal on every page. Backed by `GET /api/sheet/read?date=YYYYMMDD` (reads A:W + parses sub-tables via `format_check_service.parse_structure`). See `app/main.py:api_sheet_read`.
- **Google Sheets jump links** — topbar `🔗 入院 Sheet` / `🔗 排班 Sheet` open the live Sheet in a new tab (only render if respective sheet_id is configured).
- **Date input upgrade** — admission page now has both a native `<input type="date">` calendar picker AND the YYYYMMDD text input, bidirectionally synced via `setupDateInputs()` in `app.js`.
- **Auto weekday** — weekday `<select>` is auto-filled by (admission_date + 1).weekday. Reflects 開刀日, not 住院日. See [[feedback-weekday-field-is-op-day]].
- **資料檢查 standalone card** — format check + finalize check moved out of `.date-row`, placed in own card marked `[選用]` with hint "需要整理 Google Sheet 格式問題時再使用即可".
- **Sub-table auto-update** — Step 1 OCR overwrite now updates per-doctor sub-tables to reflect diff: removed rows dropped, doctor-changed rows moved (E cleared), added rows appended to their A-L doctor (if existing sub-table). Function: `ocr_service._apply_diff_to_subtables`. Unattached added/changed (no sub-table for new doctor) reported in result, not silently dropped.
- **Settings UX** — button order made explicit: ① 儲存 (green primary) → ② 測試連線, with yellow hint box explaining "test uses persisted config, save first".

**Delivered (Phase 10 — 2026-05-14 workflow re-architecture):**
- **Step 2 redesign** — no longer "Lottery". Now `subtable_service.build_subtables_from_main(date)` walks A-L and writes per-doctor sub-tables in main-table appearance order. Refuses to overwrite existing sub-tables. See [[step2-no-lottery]].
- **Step 4 redesign — lottery + 3-layer pin** — `lottery_service.lottery_with_pins(date, weekday, patient_pins, doctor_pins)`. Three independent pin layers (E col within-doctor, patient_pins global, doctor_pins RR rank). UI: 2× `<details>` pin panels above sub-tables; pins persist in localStorage keyed by date. See [[pin-layers-separated]].
- **EMR fetch frameset fix** — `emr_service.fetch_raw_html` rewritten with frame-walk + `#txtChartNo` / `#BTQuery` + FALLBACK_DOCTORS. Returns `(soap, divUserSpec, visit_label)`. See [[nckuh-emr-frameset]].
- **EMR writeback** — `emr_service.write_results_to_subtables(date, results)` + `sheet_service.batch_write_cells(ws, patches)`. Step 3 endpoint now writes C/F/G to sub-tables (was silent bug). See [[step3-must-writeback]].
- **F/G as datalist combobox** — replaced `<select>` with `<input list>` so user can pick OR type free text. Custom F → `Others:<text>` + `OTHERS_PDI` in cathlab keyin; custom G → 備註 field. See [[fg-combobox-not-select]].
- **Sheet viewer for all worksheets** — `/api/sheet/raw?name=<>` reads any tab as raw A:Z. Viewer dropdown groups "日期分頁" + "其他工作表" (主治醫師抽籤表, 值班總數統計, etc.).
- **Button loading states** — `withBusy(btn, text, fn)` helper wraps every async click handler. Button turns orange + spinner + disabled while pending.
- **Cache-buster** — `?v={{ static_version }}` (per-startup timestamp) on /static/app.css and /static/app.js URLs. No more Ctrl+F5 needed after restart.
- **Gemini info in /settings** — `<details id="gemini-info">` shows model RPM/RPD/TPM table when provider = Gemini. App default = `gemini-2.5-flash-lite`. See [[gemini-free-tier-2026]].

**Pending:**
- Card 2 (Key 班) is still a **disabled placeholder card**. Upstream `CV-Schedulling-APP` has it as "即將推出". Port `keyin_routes.py + keyin_scheduler.py + keyin_excel_parser.py + keyin_index.html` once they exist there.
- N-V 入院序 still NOT auto-rebuilt on OCR diff — user must manually rerun Step 4 (lottery) after material adds/removes.
- Auto-create sub-table for newly-appeared doctor — not implemented (layout/gap guessing too fragile). Such patients land in `unattached_added` / `unattached_changed` result fields.
- Missing static data: `app/data/static/cathlab_id_maps.json` / `doctor_codes.json` / `cathlab_schedule.json` — `app/data/` is `.gitignored`. ~35 cathlab tests fail with `FileNotFoundError` and Step 5 (cathlab) 500s until copied in from `C:\Users\dr\Downloads\Y\每日入院名單 Claude\`.

**Why:** This branch (`main`) is now ahead of origin by the Phase 9 UI work; multi-device parallel development resolved earlier this session via merge commit `3d03c54` (which also brought Phase A/B/C from another machine into this clone — they were previously only on origin).

**How to apply:**
- When user mentions a feature added "this week" — check `git log --since="2026-05-10"` against this list before assuming it's a new request.
- Sub-table sync runs only when sheet already has data on overwrite. First-time Step 1 (empty sheet) writes A-L straight through, no diff path.
- Don't auto-create new sub-tables; leave to user via Step 2 lottery re-run for new doctors.
