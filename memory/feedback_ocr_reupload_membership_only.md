---
name: ocr-reupload-membership-only
description: "Re-uploading a same-day screenshot is MEMBERSHIP-only (add/remove). Existing chart_no rows are NEVER touched — including their 主治醫師 — even if the new OCR shows a different doctor."
metadata:
  node_type: memory
  type: feedback
  originSessionId: 8f6f0aa1
---

User rule (verbatim across two corrections):
- 2026-05-19: "新截圖來 看看有沒有新增或減少的 如果有就修正主表和子表 如果沒有 就照舊 ... 我原先key好的不要動 除非新截圖沒有的資料 就要把舊的刪除 以新的為主"
- 2026-05-20: "同病歷號的列『完全不要動』（含主治醫師欄），即使新截圖醫師欄不同也保持原本"

`ocr_service.write_to_sheet` (re-upload, sheet already has data):
- **No add / no remove** → write NOTHING (return `unchanged: True`).
  Every keyed A-L cell + sub-table stays exactly as the user left it.
- **Add / remove present** → keep each kept patient's A-L row VERBATIM
  (never re-OCR keyed cells), only drop removed-chart rows + append
  added-chart rows; then the existing `_apply_diff_to_subtables` runs.
- **`doctor_changed` is ALWAYS ignored** (2026-05-20 rule). `_apply_diff_to_subtables`
  no longer has a doctor_changed branch — patients with the same chart_no
  stay in their original sub-table even if the new screenshot shows a
  different doctor. `doctor_changed` remains in the diff payload for the
  UI to surface as INFO, but is never auto-applied to either main A-L
  (already verbatim) or sub-tables (branch removed).

**Why:** the old code blindly rewrote A2:L from the new OCR, wiping
user-corrected 姓名/年齡/病床號/提示. The 2026-05-20 strengthening came
when 麒翔 re-uploaded a same-day screenshot whose OCR had a different
doctor for an existing chart and the sub-table silently moved that patient
to the new doctor — losing E/F/G work and confusing the user.

**How to apply:**
- Never reintroduce a `doctor_changed` branch in `_apply_diff_to_subtables`.
  The function signature still accepts the diff (for added/removed) but
  ignores `diff["doctor_changed"]` entirely.
- `result["moved"]` and `result["unattached_changed"]` are now always `[]`.
- EMR-based 主治醫師 canonicalization (apply_emr_main_fixes) is a SEPARATE
  flow — EMR IS authoritative, so D-col patches from matched_doctor=True
  visits are allowed (see [[emr-doctor-canonicalization]]).
- UI must report outcome in plain Chinese counts (no "A2:L34" range jargon)
  — see [[no-column-letters-in-ui]].
- Covered by tests `test_reupload_no_membership_change_is_noop`,
  `test_reupload_keeps_kept_rows_verbatim_on_membership_change`,
  `test_subtable_sync_doctor_changed_is_ignored_2026_05_20`, and
  `test_subtable_sync_doctor_change_target_also_untouched_2026_05_20`.
