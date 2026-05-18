---
name: fg-options-from-sheet-dropdown-tab
description: "F/G option lists must come from Sheet「下拉選單」worksheet, not hardcoded"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: e1e4fa8a-6914-4b37-bcf3-9dce2ff239ad
---

The user maintains the canonical F (術前診斷) + G (預計心導管) option lists
in a worksheet titled `下拉選單` inside the admission spreadsheet. Column A
holds F options (with column B = 主/子 hierarchy label), column D holds G
options. Read 55+ F entries and 22+ G entries from there.

`emr_service.get_fg_options()` reads `下拉選單` first via
`sheet_service.read_fg_options_from_sheet()`; only falls back to hardcoded
DIAG_RULES/CATH_RULES outputs if the worksheet is missing/unreachable.

**Why:** User wants single source of truth — adding a new diagnosis to the
sheet should immediately appear in app dropdowns AND Sheet's own native
dropdown (data validation reads from same source). Hardcoded lists drift
out of sync. Source: 2026-05-15 user message "像 [Sheet URL] 都有依照下拉
選單工作表在FG產生下拉清單了".

**How to apply:**
- Never hardcode F/G option lists for UI
- `/api/options/fg` returns `{f, g, source}` where source = "sheet" or "fallback"
- `set_fg_validation` on Sheet sub-tables uses same option list (allow_invalid=True
  so user-typed values still pass)
- Cache via `_fg_cache` in sheet_service; bust via `reset_cache()` (called on
  settings save) or `POST /api/options/fg/refresh`
- See [[fg-combobox-not-select]] for Sheet-side validation rule (strict=False)
