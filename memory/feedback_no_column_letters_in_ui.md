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

Generalised (2026-05-19): the rule is NOT only column letters — ALL
internal / engineering jargon in user-facing copy must become plain
Chinese. Confirmed on the Step 5 cathlab UI:
- `dry-run` → 預覽（不寫入）
- `驗證` (verify) → 與現有排程對照（只查不寫）
- `Keyin` / `ADD` → 建立排程；`UPT` → 補上術前診斷與預計術式
- `pdijson` / `phcjson` → never shown; they are just the data format of
  術前診斷 / 預計術式 (pdi=術前診斷, phc=預計心導管術式) — user need not know
- result states `ok/skip/error`, `OK/NG/SKIP`, `MISSING` → ✓成功 / 已存在略過 /
  ✗失敗 / ✓已在排程 / 還沒進排程 / 沒寫進去
- OCR uncertainty `?？�` in names must never reach the screen — strip at
  backend read AND add a display-layer `cleanName()` safety net

**Why:** "用欄位英文字母 別人看不懂 請用欄位名稱代替" (2026-05-15) +
"請用一般使用者看得懂的方式呈現 … UPT 是啥? pdijson phcjson 是甚麼?"
(2026-05-19). Incoming 行政總醫師 won't know any of this shorthand.

**How to apply:**
- Modal step descriptions, button tooltips, flash messages, table headers,
  result status cells → plain Chinese only; add a foldable 說明 explaining
  multi-phase flows in lay terms
- Internal docs (CLAUDE.md, memory, code comments) → letters/jargon fine
- F/G in UI element classes / IDs (.fg-cell, fg-input) → fine (DOM-only)
- Backend response keys can stay short ({"f":..., "g":...}, add/upt) since
  not user-visible — only the rendered label matters
