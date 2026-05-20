---
name: lottery-empty-tickets-warning
description: "Lottery must surface a prominent warning when weekday is set but tickets came back empty — silent fall-through to non-時段 shuffle was hiding mis-keyed sheets."
metadata:
  type: feedback
---

User correction (2026-05-21):
> 你明明就沒有按照邏輯抽籤 現在 5/26 有一位劉嚴文醫師住院 他 5/27 沒有時段
> 卻被排到第一位 你好好檢查好嗎
>
> [Q: flash showed?] 顯示「（無）」（沒讀到時段醫師）

The 時段組-first invariant was correct on paper, but
`read_lottery_tickets("週三")` returned `{}` so EVERY doctor (including
non-時段 劉嚴文) fell into Group 2 and got shuffle-ordered. The flash
message did say `抽籤表 週三：（無）`, but it was buried in a noisy
success line — user missed it.

**Why:** A weekday-shaped lottery with empty tickets is almost certainly
a mis-keyed sheet, not a legitimate config. The right response is a
prominent yellow warning banner, NOT silent fall-through. Hiding this
failure mode in 12 chars of grey text made the bug invisible until the
field-test made it visible.

**Actual 5/26 root cause** (user confirmed by pasting the row):
- Sheet's A-column label is `星期三` (not `週三`).
- JS `WEEK_LABELS = ['週日'..'週六']` sends `週三`.
- Old exact-string compare: `『星期三』 != 『週三』` → tickets={} → all
  doctors fell into 非時段組 random shuffle → 劉嚴文 ended up #1.

Fix: `_normalize_weekday_label` now folds `星期X → 週X` before compare.
The Sheet can use either notation freely.

**Other sheet-side variants still covered by normalize:**
- whitespace / fullwidth-space / BOM
- trailing `:` `、` `,`
- extra leading/trailing spaces

**How to apply:**
- `lottery_with_pins` returns `warning: str` populated only when
  `weekday` was set but `tickets == {}`.
- The click handler in `app.js` prepends a yellow-bordered banner to
  `#order-result` AFTER `renderOrderResult` (so the table render
  doesn't wipe it).
- `read_lottery_tickets` now uses `_normalize_weekday_label()` —
  strips whitespace, fullwidth-space, BOM, and punctuation (`:` `、`
  `,`). `『週三 』` / `『週三：』` / `『 週三』` all match.
- Lottery response also includes `doctor_groups: {doctor: "時段組" |
  "非時段組"}` — UI shows it inline (`🟦 時段組` / `🟧 非時段組`) so user
  can visually verify grouping.
- DO NOT add silent fallbacks here. If tickets are empty AND user
  supplied a weekday, the right behavior is "show warning and still
  produce a shuffle" — not "guess the user meant 假日" or "skip
  lottery entirely".
