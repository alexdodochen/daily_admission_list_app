---
name: subtable-shift-down-when-main-grows
description: "On OCR re-upload, sub-table block must shift DOWN when main has grown past the original sub-table title row — otherwise the sub-table write overwrites the newly-added main row."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: b6c698a8-a63e-4019-8663-6eb5e0f5e21e
---

Field bug 2026-05-24 (5/25 sheet): user reported 「新增病人只進子表，主表沒進」
— a re-uploaded screenshot's added patient appeared in the sub-table but
NOT in main A-L.

**Why:** `ocr_service.write_to_sheet` reads `pre_grid` BEFORE writing main,
captures the original sub-table `start_row` (e.g. row 5). After adding 3
patients, merged main runs A2:L5. Then `_apply_diff_to_subtables` writes
the new sub-table block starting at A5 (the captured row), OVERWRITING
the main row that was just placed there. Net effect: the added patient is
in the sub-table block (which was rebuilt in-memory correctly) but its
main A-L row is wiped by the sub-table title.

**How to apply:**
- `_apply_diff_to_subtables` takes `main_end_row: int = 0` and
  `gap: int = 2`. `start_row = max(requested_start, main_end + 1 + gap)`.
- Caller in `write_to_sheet` passes `main_end_row=end_row` (the post-merge
  main last row).
- On shift, the gap rows (`main_end + 1 .. start_row - 1`) are cleared in
  A-H so leftover old sub-table cells don't show through.
- Default `main_end_row=0` preserves the old behavior for any test/caller
  that doesn't supply it.
- Tests: `test_subtable_sync_shifts_down_when_main_grew_into_subtable_area`,
  `test_subtable_sync_stays_in_place_when_main_didnt_grow`.

Related: [[ocr-reupload-membership-only]] (the rule that kept rows stay
verbatim — this bug was a layout bug, NOT a violation of that rule).
