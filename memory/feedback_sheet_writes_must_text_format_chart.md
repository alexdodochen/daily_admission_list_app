---
name: sheet-writes-must-text-format-chart
description: Any write of 病歷號 to Google Sheet must apply TEXT numberFormat to the column FIRST — USER_ENTERED with no format strips leading zeros silently.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 2e27ecbd-39a1-425a-b28b-3c4df41994ad
---

Before any `write_range` / `update_cell` that lands a 病歷號 in a column,
call `sheet_service.ensure_chart_text_format(ws)`. Otherwise Google Sheets'
USER_ENTERED parser sees `"01937569"` as a number, stores it as `1937569`,
and the leading zero is lost forever (re-format-as-TEXT doesn't recover it).

**Why:** User reported (2026-05-15): "病歷號沒有用文字格式儲存 導致開頭0被吃掉".
The pre-existing `format_check_service.fix(types=['chart_text_format'])`
applies TEXT format but only retroactively — it doesn't restore digits
already eaten by USER_ENTERED parsing on a prior write.

**How to apply:**
- Wired in `sheet_service.ensure_date_sheet` (covers new sheets).
- Defensive calls in `ocr_service.write_to_sheet`, `subtable_service.build_subtables_from_main`,
  `_apply_diff_to_subtables`, `lottery_service.lottery_with_pins`,
  `emr_service.write_results_to_subtables`, `api_sheet_write_cell`.
- TEXT range = cols I (main, idx 8), S (ordering, idx 18), B (sub-tables, idx 1),
  rows 2..500.
- If a user encounters already-stripped chart numbers on an old sheet:
  *re-run Step 1 OCR with overwrite* on that date — the new code path
  applies TEXT format before writing, so OCR'd "01937569" survives intact.
  Format-fix alone doesn't bring the zero back.

**Related:** [[nckuh-emr-frameset]] (chart-no consistency matters for the
EMR fetch matching too — if Sheet has `1937569` but EMR expects 8 digits,
chart lookup fails).
