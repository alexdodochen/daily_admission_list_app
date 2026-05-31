---
name: long-forms-get-bottom-nav
description: Long multi-step forms must duplicate their top stepper / nav at page bottom so users don't scroll back up to switch step after filling the last field
metadata:
  type: feedback
---

For any long admission/cathlab workflow page with a top `.stepper`, also render a `.stepper.stepper-bottom` at page bottom (same buttons, same `data-step`). The click handler must:

1. Sync the active class to BOTH stepper instances (top + bottom) for the clicked `data-step`.
2. Toggle `.panel` visibility by `data-step` once (not duplicated).
3. When the clicked button is inside `.stepper-bottom`, smooth-scroll to top of page so the newly-shown panel is visible without manual scroll.

**Why:** 2026-05-26 user worked through `/admission` Step 3 EMR cards (~20 patient cards tall) and asked for a bottom nav: "填完東西到畫面最底層就不用回到最上面才能做事". The top-only stepper forced a long scroll to switch between Step 2 → Step 3 → Step 4.

**How to apply:** Pattern lives in `app/templates/admission.html` + the `.stepper` handler in `app/static/app.js` (search for `document.querySelector('.stepper')`). When porting to a new long-form page (`/sched`, `/keyin`) or extending an existing one, duplicate the stepper at the bottom and the existing handler already covers both via `.stepper-bottom` detection.

Do NOT add sticky/fixed positioning — user did not ask for it; floating bars conflict with the existing 🐞 + 📜 + ⬆ corner-button stack.
