---
name: step2-no-lottery
description: "Step 2 in the admission flow is \"build sub-tables from main A-L order\" — NOT lottery. Lottery moved to Step 4."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 202e121c-0c8f-4e62-891f-fd58ee1476b3
---

User correction (2026-05-14):
> step 2 你沒有讀到主治醫師抽籤表，而且你現在 Step 2 讓人誤會，step 2 還不用抽籤
> 依照你的主表順序直接生成 subtable

The original CLAUDE.md described Step 2 as "Lottery". That was wrong for the
in-app workflow. Correct mental model:

| Step | What | Module |
|------|------|--------|
| 1 | OCR screenshot → A-L | `ocr_service` |
| 2 | Build per-doctor sub-tables from A-L order | `subtable_service.build_subtables_from_main` |
| 3 | EMR extract → write back to sub-tables C/F/G | `emr_service` |
| 4 | Lottery + write N-V (with 3-layer pin) | `lottery_service.lottery_with_pins` |
| 5 | Cathlab keyin to WEBCVIS | `cathlab_service` |
| 6 | LINE push | `line_service` |

**Why:** Step 2's lottery used to read 主治醫師抽籤表 which (a) requires the
sheet tab to exist, (b) requires the weekday row to match, (c) conflated two
concerns. Splitting: Step 2 is structural (sub-tables), Step 4 is decisional
(who goes first in 入院序).

**How to apply:**
- Don't restore an `/api/step2/run` lottery + N-S write path. The old
  legacy routes + `read_main_patients` / `draw` / `round_robin` /
  `write_to_sheet` helpers were deleted 2026-05-27 — only `lottery_with_pins`
  + `read_lottery_tickets` + `weighted_doctor_shuffle` + `parse_ticket_cell`
  remain in `lottery_service`.
- `subtable_service.build_subtables_from_main` REFUSES to overwrite existing
  sub-tables; user must go through Step 1 OCR diff path to preserve F/G.
- Rescue path for corrupted sub-tables: `subtable_service.smart_rebuild` via
  `POST /api/step2/rebuild_subtables`.
