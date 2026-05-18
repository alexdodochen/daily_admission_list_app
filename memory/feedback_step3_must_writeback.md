---
name: step3-must-writeback
description: Step 3 EMR endpoint must write extracted C/F/G back to sub-tables. Returning to UI alone is a bug.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 202e121c-0c8f-4e62-891f-fd58ee1476b3
---

User bug report (2026-05-14): "都沒抓到 EMR 資料".

Root cause: `api_step3_run` extracted EMR data via Playwright and returned it
to the frontend, but **never wrote it to the Google Sheet**. The docstring on
`emr_service.process_patient` said "writeback is caller's responsibility" but
the caller (the endpoint) skipped it.

**The contract:**
- `extract_patients(session_url, patients, admission_date)` returns
  `[{chart_no, name, doctor, c_text, f, g, ...}]` — pure data, no sheet I/O.
- `write_results_to_subtables(date, results)` writes each result's C/F/G back
  to its sub-table row (matched by `chart_no`).
- The endpoint MUST call writeback when `date` is supplied (default: pass the
  Step 1 `date-input` value).

**Writeback mechanism:**
- `sheet_service.batch_write_cells(ws, patches)` — single gspread `batch_update`
  call. Avoids 1 API call per cell (3 cells × N patients = expensive).
- `patches = [(a1, value), ...]`. Skip empty values to keep the request lean.

**Why this is easy to miss:** the UI shows EMR results immediately after
Playwright returns, so it LOOKS like it worked. Only when the user reloads
the sheet does the missing writeback become obvious.

**How to apply:**
- Any future EMR-like flow (Playwright fetch + render to UI) must include a
  sheet writeback step in the endpoint, not punted to "caller's responsibility".
- The UI response shows `writeback.written` / `writeback.missing` so the user
  can confirm sheet was actually updated.
- See `app/services/emr_service.py::write_results_to_subtables`.
