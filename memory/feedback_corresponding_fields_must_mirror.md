---
name: corresponding-fields-must-mirror
description: "Fields that mean the same thing in different sheet blocks must stay synced — editing one anywhere (Step 2/3/4, 查閱 viewer) propagates to its twin by 病歷號."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 416a5492-226f-48ec-b648-4eeae4b820b4
---

User rule (2026-05-21, verbatim): "我希望 google sheet 的各種欄位跟 app
內的各種對應欄位 全部都要連動 … 所有互相對應的欄位 在任意地方經過編輯後
都要可以連動！"

The N-V 入院序 block and the per-doctor sub-tables hold the SAME fact
twice for each patient. These pairs must mirror live:

| 子表格 (sub-table) | N-V 入院序 |
|---|---|
| H 註記 | R 備註 |
| F 術前診斷 | T 術前診斷 |
| G 預計心導管 | U 預計心導管 |

Implemented by `ordering_service.propagate_field_edit(date,row,col,value)`,
called AFTER the write in BOTH `/api/step4/cell` and `/api/sheet/write_cell`.
Match key is 病歷號. So an edit in Step 2/3 sub-table inputs, Step 4
入院序結果, or the 查閱 viewer all reach the twin cell.

**Why:** before this, the 查閱 viewer wrote a raw cell with no propagation,
so editing N-V 備註 there left sub-table H stale — and cathlab keyin reads
sub-table H, so the edited note never reached WEBCVIS 備註. F/G already
synced between Step 2/3 (shared inputs); the viewer + H/R were the gap.

**How to apply:**
- Column number ALONE is ambiguous: sub-table F/G/H = cols 6/7/8 collide
  with main-table 姓名/性別/年齡. `propagate_field_edit` validates the
  edited `row` against the real N-V / sub-table row maps — a main-table
  edit must never propagate.
- If a new shared field is added, wire it into the `_MIRROR_*` maps so it
  mirrors too — don't leave a field that's editable in one place only.
- 病歷號 / 主治醫師 are NOT mirrored this way — 病歷號 is the join key,
  主治醫師 change is structural (moves sub-table blocks). Different flow.
- cathlab keyin already reads sub-table H 註記 → WEBCVIS 備註; with the
  mirror in place, a 備註 edit made anywhere reaches H. See
  [[subtable-h-to-r-ordering]].
- Tests: `test_ordering_service.py` `test_propagate_*` (4).
