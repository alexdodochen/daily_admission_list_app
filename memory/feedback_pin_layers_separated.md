---
name: pin-layers-separated
description: "Three independent pin layers for 入院序 — E col (within-doctor sort), patient pin (global seq), doctor pin (RR rank). Never conflate."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 202e121c-0c8f-4e62-891f-fd58ee1476b3
---

User correction (2026-05-14):
> 同一個醫師 123 放 E
> 單獨指定獨立出來一欄讓我設定
> 某醫師排第幾位也是自己一欄讓我設定

The mistake was bundling all pin semantics into the sub-table E column. Correct
design has THREE independent pin layers:

| Layer | Storage | Semantic |
|-------|---------|----------|
| L1 — E col | sheet sub-table col E (per row) | Within-doctor sort 1/2/3 |
| L2 — patient pin | `localStorage[pin_YYYYMMDD].patient_pins` (chart_no → seq) | Force this patient to global 序號 N |
| L3 — doctor pin | `localStorage[pin_YYYYMMDD].doctor_pins` (doctor → rank) | Force this doctor to be N-th in RR draw order |

L1 is per-sheet (persists in the Google Sheet). L2 + L3 are per-browser
(localStorage). Lost on browser cache clear; not synced across machines —
acceptable for single-session workflow.

**Lottery resolution order** (in `lottery_service.lottery_with_pins`):
1. For each doctor, sort patients by L1 (E col) if filled (all-or-nothing per
   doctor — `ordering_service.sort_by_manual_e`).
2. Build doctor RR order: L3 pins go to fixed ranks; unpinned doctors filled by
   `weighted_doctor_shuffle(tickets)` then plain shuffle for out-of-schedule.
3. Round-robin patients across doctor_order → produces base sequence.
4. Apply L2 pins: pinned patients go to their fixed positions; unpinned
   patients (from base sequence, in RR order) fill the remaining gaps.

**Validation:** Each layer validates uniqueness + range independently. Errors
return 400 with a clear Chinese message.

**Why:** User wants explicit, separated control. Bundling them confuses what
a number in E means (is it within-doctor or global?). The 3-layer design lets
user mix: e.g., 詹P 三位寫 E=1/2/3 (L1), AND say "病人X 全域第 1" (L2), AND
say "劉P 第 1 順位" (L3) without conflict.

**How to apply:**
- UI: Step 4 has two `<details>` pin panels above the sub-tables (病人 pin +
  醫師 pin). Sub-table E col stays as `editable-pin` cell.
- Pins auto-save to localStorage on every input change.
- localStorage key: `pin_YYYYMMDD` (date scoped — switching dates loads
  different pins).
