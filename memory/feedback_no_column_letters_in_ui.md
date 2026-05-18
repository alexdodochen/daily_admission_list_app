---
name: no-column-letters-in-ui
description: "User-facing copy must use Chinese field names, not Sheet column letters"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: e1e4fa8a-6914-4b37-bcf3-9dce2ff239ad
---

In any UI text the user reads (panels, hints, button labels, modals,
flash messages), refer to fields by their Chinese names — never by the
Sheet column letter codes that only Claude knows.

Mapping for /admission (date sheet):
- E (sub-table col 5) → 同醫師排序 / 同醫師內排序
- F (sub-table col 6) → 術前診斷
- G (sub-table col 7) → 預計心導管
- N-V (cols 14-22) → 入院序 / 入院序區塊
- O (col 15)        → 主治醫師（在入院序）
- Q (col 17)        → 備註(住服)
- T (col 20)        → 術前診斷（在入院序）
- U (col 21)        → 預計心導管（在入院序）
- V (col 22)        → 改期

For main A-L:
- F (col 6) → 姓名
- G (col 7) → 性別
- H (col 8) → 年齡
- I (col 9) → 病歷號
- D (col 4) → 主治醫師

**Why:** "用欄位英文字母 別人看不懂 請用欄位名稱代替" (2026-05-15). Other
users (incoming 行政總醫師) won't know the column-letter shorthand —
needs to be self-explanatory.

**How to apply:**
- Modal step descriptions, button tooltips, flash messages → Chinese only
- Internal docs (CLAUDE.md, memory, code comments) → letters fine (Claude reads them)
- F/G in UI element classes / IDs (.fg-cell, fg-input) → fine (DOM-only, not user-visible)
- Backend response keys can stay short (e.g. {"f": ..., "g": ...}) since not user-visible
