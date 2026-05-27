---
name: 3-card app integration state
description: daily_admission_list_app shape — 3-card home (排班 / Key班 / 入院清單), public repo, .exe distribution
type: project
---

`daily_admission_list_app` (public on GitHub) is the integration target for a
3-card home (排班 / Key班 / 入院清單). Ships as a double-clickable `.exe` (PyInstaller
onedir, ~880 MB with bundled Chromium + service-account) to each year's
incoming 行政總醫師. Recipients pull updates via in-app 更新 button — never
re-ship the zip after the first install.

**Card 1 (排班)** — `/sched`, `schedule_gen.html`, Tailwind via CDN. Solver in
`cv_solver.py`, Sheets I/O in `scheduling_service.py` (separate spreadsheet
keyed on `cfg.schedule_sheet_id`). Solver cache at `main._solve_cache`.
Calendar cells are editable `<select>` → `POST /api/sched/apply-edits`
overwrites the cache. `POST /api/sched/handoff-to-keyin` ships the schedule
into Card 2's prefill state.

**Card 2 (Key 班)** — `/keyin`, `keyin.html`, ported from
`alexdodochen/Key-Schedule-APP`. APIRouter at `/keyin/api/*`. Auth + audit
stripped per [[strip-auth-for-local-ports]].

**Card 3 (入院清單)** — `/admission`, `admission.html`. The 6-step admission
workflow (OCR / build sub-tables / EMR / lottery / cathlab keyin / LINE).
Format check + finalize panel at bottom of the page.

**Cross-cutting**:
- `📋 查閱` viewer modal — `/api/sheet/read` (date sheet structured) +
  `/api/sheet/raw` (any tab). Editable cells via `/api/sheet/write_cell`.
  Batch-delete date tabs via `/api/sheet/delete` (admission sheet only,
  `^\d{8}$` tabs only; last worksheet never deleted).
- `🐞 回報問題` modal — bug_report scrub (PHI/creds) → public GitHub
  prefilled issue OR private `.zip` (with screenshots, never public).
- Live field mirror — sub-table H/I/F/G ↔ N-V R/Q/T/U via
  `ordering_service.propagate_field_edit`, fired on every single-cell edit.
- Cache-buster: `?v={static_version}` (per-startup timestamp).
- Watermark: bottom-right, hidden in print.
- Sub-pages must `{% extends "base.html" %}` + IIFE-wrap their inline script.

Historical phase log lives in git log + commit history.
