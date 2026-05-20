---
name: emr-preserve-existing
description: "Step 3 EMR writeback must NOT overwrite a sub-table row that already has user data in C/F/G. Re-fetch requires user to clear those cells first."
metadata:
  type: feedback
---

User correction (2026-05-21):
> step3 EMR擷取 如果該病歷號已經有資料 注意不要覆寫 要保留原本的樣態

**Why:** When the user adds 1 new patient to an existing date and re-runs
Step 3 EMR for the whole batch (or just to fetch the new one), the old
behavior overwrote every chart's C/F/G — destroying any F that the user
had typed manually, or any 註記 in C that the user had edited.

**Rule (per-chart, all-or-nothing):**
- If sub-table row's `emr` (C) OR `diagnosis` (F) OR `cathlab` (G) is
  non-empty → preserve the row entirely. No patches at all for that chart.
- All three empty → write normally.
- Error results (failed fetch) → skipped regardless (not "preserved").

**To re-fetch a previously-EMR'd chart:** manually clear C/F/G in the
sub-table (via the editable 📋 查閱 viewer or directly in Google Sheet),
then re-run Step 3.

**How to apply:**
- `emr_service.write_results_to_subtables` reads existing sub-table state
  via `ordering_service.read_doctor_subtables(date)` and builds
  `chart_to_existing: {chart: {emr, diagnosis, cathlab}}`.
- Returns `preserved: [chart_no, ...]` so UI can report the count.
- UI: `app.js` lottery flash shows `保留既有 N 位（已有資料未覆寫）`.
- Tests: `tests/test_emr_service.py::test_writeback_preserves_*`.

**Don't:**
- Don't add a "force overwrite" flag without surfacing it explicitly in
  the UI — silent overwrite is exactly what this rule exists to prevent.
- Don't apply this rule field-by-field — user said "保留原本的樣態" which
  means the WHOLE row, not just one cell.
