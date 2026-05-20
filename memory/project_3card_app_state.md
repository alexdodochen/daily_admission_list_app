---
name: 3-card app integration state
description: Current state of the daily_admission_list_app — what's delivered, what's pending in the CV_APP 3-card consolidation
type: project
originSessionId: 72454ca2-3f8b-459c-b668-ba750a7a2e97
---
This repo (`daily_admission_list_app`, cloned at `C:\Users\dr\Downloads\Y\排班 Key班 DayList APP`) is the **public integration target** for a 3-card home (排班 / Key班 / 入院清單).

State as of 2026-05-20 (Phase 15 — 10-issue field-bug batch from 麒翔's install):

**Delivered (Phase 15 — 2026-05-20 → c47d357):**
- **② EMR 註記 ↔ ③ 入院序整合 註記 bidirectional sync** — `renderSubtables`
  H-col cell upgraded from plain `<td>` to `noteInput()` (editable text
  input with `class="fg-input note-input"`). Existing `wireFgInputsIn`
  paths in both directions pick it up automatically.
- **EMR doctor canonicalization for main D col** — see [[emr-doctor-canonicalization]].
  `fetch_raw_html` now returns 4-tuple incl. `matched_doctor` bool;
  `_name_variants` strips trailing OCR "?". `apply_emr_main_fixes` patches
  D when matched_doctor=True.
- **FALLBACK_DOCTORS pool 6 → 28** — `_load_cv_doctor_pool()` unions the
  hardcoded floor with `app/data/static/doctor_codes.json` keys at import.
  Closes the "查無 EMR" gap for inpatient-only patients consulted by any
  known CV attending. See [[emr-fallback-pool-from-doctor-codes]].
- **Re-upload doctor_changed branch removed** — `_apply_diff_to_subtables`
  no longer moves patients between sub-tables on doctor change. Same chart_no
  rows are completely untouched. See [[ocr-reupload-membership-only]].
  Two ocr_service tests rewritten.
- **Load-existing button no longer auto-jumps tabs** — see [[load-existing-no-tab-jump]].
- **資料檢查 panel moved bottom of /admission** (between Step 6 and end).
- **Scroll-to-top floating button** — `#scroll-to-top` in base.html, CSS
  fade-in past 240px, smooth scroll JS. Visible across every page.
- **③ 入院序整合 sub-table shows 性別 + 年齡** — parsed from C-col c_text
  prefix `<age> y/o <gender>\n` in `renderSubtables`. No backend change.
- **Step 5 預覽排程 per-patient overrides** — UI gains 「排」checkbox column
  (uncheck = skip from keyin) + 「導管日期」`<input type=date>` (shift this
  patient to a different day). Backend `_apply_overrides` whitelist gains
  `skip` + `cath_date`. Override collection in keyin5-btn translates
  checkbox `skip_inverted` → `skip` bool and ISO date → YYYY/MM/DD.
- **Step 5 missing_after reason column** — see [[missing-after-must-show-reason]].
  `cathlab_service.keyin` pairs each missing patient with their Phase-1
  `add_results` row; UI shows the explanation, never bare "✗ 沒寫進去".

**Tests:** 372 → 372 (2 ocr_service tests rewritten for the new "doctor
unchanged" rule, cathlab override surface covered by existing tests).

State as of 2026-05-18 (Phase 14 — Card 1 full UI port from Key-Schedule-APP + Step 5 manual edit + exe delivery):

**Delivered (Phase 14 — 2026-05-18):**
- **Card 1 UI fully ported from Key-Schedule-APP** (was: solver aligned but UI/endpoints didn't surface it). `scheduling_service.previous_year_month` + `read_calendar_tail` (local calendar layout byte-identical to upstream → parser reused verbatim). `/api/sched/init` returns `prev_tail`+`prev_year/month`; `/api/sched/compute` forwards `vs_holiday_exempt`; `/api/sched/solve` forwards `prev_tail`+`vs_holiday_exempt`, caches `targets`, returns `projected_cumulative` (baseline−prev+new per cell) + `cr_holiday_target`. `_build_projection()` shared helper. UI: 上月末跨月限制 box, VS 不值假日 checkboxes (toggle → recompute), CR 預估表, 寫入後預估值班總數統計 table.
- **Step 5 manual schedule edit** (Key-Schedule-APP `7b6ccf4`, the LAST sync from that repo). `cv_solver.recompute_from_schedule()` pure fn (same classification as solver). `POST /api/sched/apply-edits` overwrites cache so write/handoff emit edited result. UI: every calendar cell → editable `<select>`, changed cells amber, `✎ 套用手調並重算` / `↺ 還原 solver 原班`, edit-aware QOD banner, draft stores revert point.
- **schedule_gen.html ported verbatim from upstream** + local infra re-applied: `extends base.html`, IIFE-scoped `$` (see [[feedback-subpage-iife-scope]]), draft fns rewired to local `/api/draft/sched/*`, dropped dup watermark. `.day-btn.selected` restored to solid indigo + white (upstream's rgba 0.40 was too faint — user correction).
- **exe built + delivered** — `pyinstaller packaging.spec` → `dist/每日入院名單/每日入院名單.exe` (onedir, 882MB w/ bundled Chromium + SA). Zipped (Windows `tar.exe`, NOT Git Bash tar — that treats `C:/` as remote host) to `C:\Users\dr\Downloads\Y\每日入院名單 for 麒翔.zip` (380MB, outside repo). exe boots + bundled SA connects to Sheet (verified).
