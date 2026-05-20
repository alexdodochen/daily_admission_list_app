---
name: load-existing-no-tab-jump
description: 📂 載入這個日期 button never auto-switches the step tab. User stays on whichever step is active so they can decide which step to inspect next.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: ce6d4b16-317d-413d-acf4-d054f69112cf
---

User rule (2026-05-20, verbatim):
> "載入這個日期後 我希望留在原畫面 不要跳轉到step 3"

Previously the load-existing-btn handler called
`document.querySelector('.step[data-step="4"]').click()` to land the user
on the sub-table view, on the assumption that "they probably want to see
the loaded data". Wrong — when the user is mid-flow on Step 1 or 2 and
just wants to refresh the Sheet data, the auto-jump is disruptive.

**Fix:** the auto-jump block in the load-existing-btn handler is removed.
The success message no longer mentions "已切到 Step 4".

**Why:** users open this button for many reasons — refresh after manual
sheet edits, reload after Step 5 cathlab edits, prepare for re-OCR — not
just to look at sub-tables. Forcing one specific landing tab is wrong.

**How to apply:**
- Any "load / refresh" surface that hydrates multiple panels should leave
  tab focus where it was. Hydrate the data; don't move the user.
- Same principle as keeping focus position on form re-renders.
- This is a specific instance of "the system shouldn't pre-decide for the
  user when it doesn't have to".
