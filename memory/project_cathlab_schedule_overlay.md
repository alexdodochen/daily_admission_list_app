---
name: cathlab-schedule-overlay
description: "Cathlab Step 5 reads 主治醫師導管時段表 from the admission Sheet to derive default second/third doctors (e.g. 詹世鴻 週三 → 許毓軨)."
metadata:
  type: project
---

User correction (2026-05-21):
> 你也沒有按照 https://github.com/alexdodochen/daily-admission-list-public
> 的規矩 自動把第二醫師 key in 例如詹世鴻醫師週三有第二醫師許毓軨 你就沒有 key

**Why:** Source repo `每日入院名單 Claude/schedule_lookup.py` reads
`主治醫師導管時段表` from the admission Sheet and parses cells like
`詹世鴻(軨)` to derive per (primary doctor × weekday) default
attendingdoctor2. The app was missing this entirely — only the
`SECOND_DOCTORS` abbrev table + 註記 parser existed, so a doctor pair
that the user maintained in the schedule table was silently dropped.

**How to apply:**
- `cathlab_service.read_schedule_overlay()` reads `主治醫師導管時段表`
  (A1:G15) once per Step 5 operation. Cache busts on every `plan()` /
  `keyin()` entry, so mid-session edits take effect.
- Cell parse rules (mirror source `schedule_lookup.py`):
  - `陳柏升` → primary, no extras
  - `詹世鴻(軨)` → primary + second
  - `黃鼎鈞(浩、晨)` → primary + second + third
  - `EP(李柏增)(晨)` → study type, tags=[李柏增, 晨]
  - `(陳則瑋)` → continuation, no primary (ignored for overlay)
- Tag resolution: `SECOND_DOCTORS` abbrev (浩/寬/晨/嘉/軨) → full name; full
  names also accepted via `doctor_codes()` lookup.
- Layout: cols B=room, C=Mon..G=Fri; rows 2-7=AM (H1 spans 2-4, H2 r5,
  C1 r6, C2 r7), rows 8-12=PM (H1 spans 8-9, H2 r10, C1 r11, C2 r12).
- Resolution priority in `_enrich`:
  1. 備註 typed second (`_pick_second_doctor`) — explicit user wins
  2. Overlay default (this rule)
  3. 陳則瑋 + 劉秉彥 OPD → override
  4. Mon + EP → force 洪晨惠, push prior second to third
- Missing worksheet / read fail → silently returns `{}`. Lookup yields
  empty strings; downstream behaves as before.
- Tests: `tests/test_cathlab_service.py::test_parse_schedule_cell_*` +
  `test_overlay_*` + `test_lookup_schedule_doctors_*` +
  `test_read_schedule_overlay_*`.

**Don't:**
- Don't move this lookup into `cathlab_schedule.json` — the user
  maintains the schedule in the Sheet, JSON would go stale.
- Don't add the overlay's second/third to `compute_slot`'s 3-key return
  (`session/room/in_schedule`) without thinking through every caller —
  use `lookup_schedule_doctors()` for second/third lookup, keep
  `compute_slot` shape stable.
