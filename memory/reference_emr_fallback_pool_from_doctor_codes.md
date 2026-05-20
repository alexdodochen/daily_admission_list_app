---
name: emr-fallback-pool-from-doctor-codes
description: "EMR FALLBACK_DOCTORS pool is loaded at import time from app/data/static/doctor_codes.json's keys, unioned with a hardcoded consult floor — never edit the runtime list by hand."
metadata: 
  node_type: memory
  type: reference
  originSessionId: ce6d4b16-317d-413d-acf4-d054f69112cf
---

`emr_service.FALLBACK_DOCTORS` is built by `_load_cv_doctor_pool()` at
module import. The pool is:

  1. `_HARDCODED_FALLBACK` = ["劉秉彥", "趙庭興", "蔡惟全", "許志新",
                              "陳柏升", "李貽恒"] — consult-only floor
     (kept for sanitised CI installs that ship without doctor_codes.json
     per [[cathlab-static-decouple]]).
  2. Plus every key in `app/data/static/doctor_codes.json["doctors"]`
     (25 NCKUH CV attendings as of 2026-05-20).
  3. Deduped, hardcoded-first, in insertion order.

Result: ~28 names searched when the primary doctor has no 一年內門診紀錄.

**Why the union, not just the JSON:**
- doctor_codes.json is PHI-gitignored (per cathlab-static-decouple); a
  fresh CI install ships without it, so the JSON-loader must degrade
  gracefully to the hardcoded floor.
- Conversely, the hardcoded six don't cover every CV attending — 麒翔's
  2026-05-20 field report showed 吳石秀 / 魏瑞泰 falling through because
  their consulting doctor was in doctor_codes.json but not the hardcoded
  six.

**How to apply:**
- Don't hand-edit `FALLBACK_DOCTORS` in code. To add coverage for a new
  attending, edit `doctor_codes.json` (which also feeds cathlab keyin).
- Don't shorten `_HARDCODED_FALLBACK` — it's the floor for sanitised
  installs.
- If a chart still hits "查無 EMR" after this 28-doctor sweep, the patient
  genuinely has no 門診 record in the past year for ANY known CV doctor;
  user should fill F/G/註記 manually from inpatient notes. See INPATIENT_ONLY_TEXT
  in [[nckuh-emr-frameset]].
- Reference impl `daily-admission-list-public/fetch_emr.py` has only the
  6-name hardcoded list — the JSON-union strategy is local-only.
