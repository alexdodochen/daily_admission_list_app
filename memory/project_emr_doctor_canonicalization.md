---
name: emr-doctor-canonicalization
description: Step 3 EMR fetch now canonicalises 主治醫師 from the matched visit_label and patches main A-L D col; only fires when matched_doctor=True (not on FALLBACK_DOCTORS visits).
metadata: 
  node_type: memory
  type: project
  originSessionId: ce6d4b16-317d-413d-acf4-d054f69112cf
---

Shipped 2026-05-20 (commit c47d357). Closes the long-standing gap where
OCR-mistyped doctor names (e.g. "李文堭" vs canonical "李文煌") were
never auto-corrected by EMR.

**Flow:**
1. `_name_variants(name)` strips trailing OCR "?" / "？" so "李文煌?" still
   matches the EMR anchor "2026/04/12 李文煌 門診". Was a silent failure
   before — fell through to FALLBACK_DOCTORS and lost the canonical name.
2. `fetch_raw_html` now returns 4 values:
   `(soap_text, div_user_spec, visit_label, matched_doctor)`.
   `matched_doctor=True` iff the visit anchor matched the OCR doctor
   (not a fallback pick).
3. `extract_visit_doctor(visit_label)` parses `<date> <doctor> 門診` →
   doctor token.
4. `extract_patients` puts the parsed doctor into `emr_doctor` (only
   when matched_doctor=True; else empty — fallback visits' doctor is
   NOT the patient's real attending).
5. `apply_emr_main_fixes` adds D-col (主治醫師) to its patch list when
   `matched_doctor=True` and `emr_doctor` differs from existing D.
6. UI fix list shows the patch with Chinese field label "主治醫師"
   alongside the existing 姓名 / 性別 / 年齡 patches.

**Known limitation (won't fix unless asked):** sub-table title rows
(`<doctor>（N人）`) are NOT auto-renamed when D-col gets canonicalised.
The patient stays in the same sub-table block under the old (mis-spelled)
title. Cost of fixing: structural sheet rewrite for one cosmetic patch.
Workaround: user can manually rename the title via the editable 📋 查閱
viewer.

**Why FALLBACK visits don't count:** if OCR doctor was so wrong that no
substring matched any anchor, the click fell through to a FALLBACK_DOCTORS
(consult attending) anchor. That doctor saw the patient as a CONSULT, not
as primary — so their name is NOT the canonical 主治醫師. Refusing to
patch on `matched_doctor=False` keeps a wrong rename from happening.

**How to apply:**
- Future EMR-based field corrections (e.g. department canonicalisation)
  should follow the same `matched_doctor` gating.
- Tests covering `extract_visit_doctor` and the matched_doctor flag live
  in `tests/test_emr_service.py`.
