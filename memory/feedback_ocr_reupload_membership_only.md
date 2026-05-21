---
name: ocr-reupload-membership-only
description: "Re-uploading a same-day screenshot is MEMBERSHIP-only (add/remove). Existing chart_no rows are NEVER touched — including their 主治醫師 — even if the new OCR shows a different doctor."
metadata:
  node_type: memory
  type: feedback
  originSessionId: 8f6f0aa1
---

User rule (verbatim across three corrections):
- 2026-05-19: "新截圖來 看看有沒有新增或減少的 如果有就修正主表和子表 如果沒有 就照舊 ... 我原先key好的不要動 除非新截圖沒有的資料 就要把舊的刪除 以新的為主"
- 2026-05-20: "同病歷號的列『完全不要動』（含主治醫師欄），即使新截圖醫師欄不同也保持原本"
- 2026-05-21: "辨識是否有新增或減少 就是以病歷號為主 病歷號相同就不用更動，不要用姓名年齡等去比對，因為那些OCR辨識常常有問題"

**Identity = 病歷號 ONLY.** Add/remove membership is decided purely by
chart_no set difference. NEVER use 姓名 / 年齡 / 性別 to decide whether a
patient is new/removed — OCR misreads those constantly and would flag a
phantom add+remove for a patient who is actually unchanged. `diff_main_data`
keys on chart_no; blank-chart_no patients fall into `unmatched_*`.

`ocr_service.write_to_sheet` (re-upload, sheet already has data):
- **No add / no remove** → write NOTHING (return `unchanged: True`).
  Every keyed A-L cell + sub-table stays exactly as the user left it.
- **Add / remove present** → keep each kept patient's A-L row VERBATIM
  (never re-OCR keyed cells), only drop removed-chart rows + append
  added-chart rows; then the existing `_apply_diff_to_subtables` runs.
- **`_apply_diff_to_subtables` reconciles main↔sub-table by chart_no
  (2026-05-21):** it iterates the FULL new main list, not just `diff.added`.
  A chart already in any sub-table → left untouched (no duplicate, no
  re-write). A main chart missing from every sub-table → appended. This
  makes re-upload idempotent AND self-heals a sheet whose main / sub-table
  drifted apart (field bug: main 9 / sub-table 10 — re-uploading used to
  duplicate the sub-table row; now it just adds the missing main row).
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
  `test_subtable_sync_doctor_changed_is_ignored_2026_05_20`,
  `test_subtable_sync_doctor_change_target_also_untouched_2026_05_20`,
  `test_subtable_sync_does_not_duplicate_existing_chart`, and
  `test_subtable_sync_selfheals_main_patient_missing_from_subtable`.
