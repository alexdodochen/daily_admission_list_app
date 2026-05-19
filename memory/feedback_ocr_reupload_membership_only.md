---
name: ocr-reupload-membership-only
description: "Re-uploading a Step 1 admission screenshot must NOT overwrite kept patients' rows — new screenshot is consulted for membership (add/remove) only"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 8f6f0aa1
---

User rule (2026-05-19, verbatim intent): "新截圖來 看看有沒有新增或
減少的 如果有就修正主表和子表 如果沒有 就照舊 ... 我原先key好的
不要動 除非新截圖沒有的資料 就要把舊的刪除 以新的為主".

`ocr_service.write_to_sheet` (re-upload, sheet already has data):
- **No add / no remove** → write NOTHING (return `unchanged: True`).
  Every keyed A-L cell + sub-table stays exactly as the user left it.
- **Add / remove present** → keep each kept patient's A-L row VERBATIM
  (never re-OCR keyed cells), only drop removed-chart rows + append
  added-chart rows; then the existing `_apply_diff_to_subtables` +
  `sync_ordering_after_diff` reconcile runs.
- `doctor_changed` WITHOUT any add/remove → counts as 照舊: NOT
  auto-applied to main (UI only notes "偵測到 N 位醫師不同，維持
  原狀"). Revisit only if the user later asks for doctor-change
  propagation.

**Why:** the old code blindly rewrote A2:L from the new OCR, wiping
user-corrected 姓名/年齡/病床號/提示 and blanking cells OCR missed.
The screenshot is authoritative for *who is on the list*, never for
overwriting cell contents the user already curated.

**How to apply:**
- Never reintroduce a wholesale `write_range("A2:L…", _patients_to_ab_rows(patients))`
  on a sheet that already has data — that is the exact regression.
- Sub-tables already diff-preserve F/G/E/H; the bug was main-table only.
- UI must report outcome in plain Chinese counts (no "A2:L34" range
  jargon) — see [[no-column-letters-in-ui]].
- Covered by tests `test_reupload_no_membership_change_is_noop` +
  `test_reupload_keeps_kept_rows_verbatim_on_membership_change`.
