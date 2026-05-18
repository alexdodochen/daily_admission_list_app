---
name: weekday-field-is-op-day-not-admission-day
description: "The 星期 select on /admission represents the cath/operation day (= admission +1), not the admission day itself"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: f5626b5e-0f78-458a-834e-a1b5bc9ccd26
---

On `/admission`, the `<select id="weekday">` field next to the date input refers to the **next-day weekday** — i.e. the cath/operation day used to key the lottery table (主治醫師抽籤表). It is NOT the admission date's weekday.

**Why:** User correction on 2026-05-13: "20260526 是禮拜二 你就要自動跳出星期三". 5/26 is Tuesday (admission), 5/27 is Wednesday (cath). The 抽籤表 is keyed by 開刀日, so a Tuesday admission → 星期三 row in the lottery sheet. Auto-fill logic in `setupDateInputs()` (app.js) implements `(admission_date + 1).weekday → 週一..週五`. If the next day falls on Sat/Sun, the dropdown stays blank (no weekend option in the select).

**How to apply:**
- When updating the weekday UI label or hint, say "隔天 = 開刀日，抽籤表用" or similar — never "住院日的星期" since that's wrong.
- Don't naïvely set `weekday = (date).weekday` anywhere — always +1.
- The lottery service reads from the user-picked weekday, so this UI rule is load-bearing.
