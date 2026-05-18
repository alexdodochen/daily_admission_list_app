---
name: fg-popup-must-show-all-on-click
description: F/G chevron click must show ALL options unfiltered; only typing filters
metadata: 
  node_type: memory
  type: feedback
  originSessionId: e1e4fa8a-6914-4b37-bcf3-9dce2ff239ad
---

The F/G dropdown UX rule (after multiple failure rounds with native datalist
and buggy filter logic in 2026-05-15):

- **Click ▼ chevron** → popup MUST show ALL options unfiltered, regardless of
  what's already in the input. Pass `open(false)` from chevron handler.
- **Type in input** → popup auto-opens (if hidden) with filter by current
  value; existing popup re-runs `buildList(inp.value)` to narrow.
- **Click outside `.fg-cell`** → close all popups.
- **Click an option** → set value, close popup, dispatch `change` to commit.

**Why:** User repeatedly hit the bug "目前就只有我key的那一項東西 沒有別的"
— the buggy version called `buildList(inp.value)` from chevron's `open()`,
filtering 55 options down to just the 1 currently in the cell. Native
`<datalist>` is also unreliable: its popup only opens on typing or arrow
keys (no click-to-open), so users think the dropdown is broken.

**How to apply:**
- The `open()` helper takes `filterByValue` arg — chevron passes `false`,
  input handler passes `true`.
- Keep using a custom `<ul class="fg-popup">`, NOT native datalist. The
  ▼ button must be the discoverability affordance.
- Don't try to use `inp.showPicker()` — also unreliable across browsers,
  and forced people to type before seeing anything.
- See [[fg-combobox-not-select]] for why it's still combobox (typeable),
  not strict <select>.
