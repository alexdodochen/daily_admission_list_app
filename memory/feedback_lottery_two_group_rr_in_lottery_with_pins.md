---
name: lottery-two-group-rr-in-lottery-with-pins
description: "lottery_with_pins must use two independent RRs (時段 then 非時段), not a single RR over all doctors — otherwise 非時段 patients interleave into the middle of 時段 patients."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: b6c698a8-a63e-4019-8663-6eb5e0f5e21e
---

Field bug 2026-05-24 (5/25 sheet): the lottery N-V output had 非時段組
patients mixed into the middle of 時段組 patients — violating the hard
rule that 非時段組 must come ENTIRELY after 時段組.

**Why:** `lottery_service.lottery_with_pins` (the UI's actual lottery
entry point) RR'd ALL doctors in `doctor_order` in one queue loop:
```python
queues = {d: list(by_doctor[d]) for d in doctor_order}
while any(queues[d] for d in doctor_order):
    for d in doctor_order:
        if queues[d]:
            rr_sequence.append(queues[d].pop(0))
```
With `doctor_order = [S1, S2, N1]` and 2 patients each, cycle 1 produced
`[S1.p1, S2.p1, N1.p1]` — N1's first patient landed at 序號 3, BEFORE
S1's second patient at 序號 4. The two-group invariant (see
[[lottery-roundrobin]]) was violated.

The standalone `lottery_service.round_robin()` already does it correctly
(`_rr_within_group(group1) + _rr_within_group(group2)`), but the UI calls
`lottery_with_pins` instead, which had its own RR loop.

**How to apply:**
- In `lottery_with_pins`, split `doctor_order` into `group1_docs`
  (in tickets) and `group2_docs` (not in tickets), preserving order
  within each group, then `_rr(group1) + _rr(group2)`.
- Reference impl: `每日入院名單 Claude/lottery_utils.py::two_group_round_robin`.
- doctor_pins still affect ordering WITHIN the appropriate group; the
  two-group rule wins globally. If user wants a 非時段 doctor's patient
  at 序號 1, use patient_pin (`{chart: 1}`), not doctor_pin.
- Test: `test_lottery_with_pins_groups_never_interleave`.

Related: [[lottery-empty-tickets-warning]], [[pin-layers-separated]].
