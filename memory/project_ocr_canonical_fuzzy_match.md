---
name: ocr-canonical-fuzzy-match
description: OCR doctor-name correction has two layers — hardcoded misread map + fuzzy match against an 18-doctor canonical CV attending pool. Fuzzy layer fires ONLY for the doctor field, never patient names.
metadata:
  type: project
---

## What

`app/services/ocr_service.py` corrects OCR-misread cardiology attending names
via two layers, in order:

1. **`OCR_NAME_CORRECTIONS`** — hardcoded `{wrong: canonical}` map for known
   recurring misreads (廖瑤→廖瑀, 柯星諭→柯呈諭, 劉獻文→劉嚴文, 廖世鴻→詹世鴻).
   Applied to BOTH `doctor` and `name` fields — the explicit list is curated
   so it's safe to blanket-apply.

2. **`_fuzzy_canonical_match()`** — fallback against `CANONICAL_CV_DOCTORS`
   (Python frozenset constant at the top of `ocr_service.py`, 18 names).
   Same-length, exactly-one-character difference, and EXACTLY ONE such
   neighbor exists → auto-correct. Otherwise return `None`. Applied ONLY
   when `is_doctor=True` (so only to the `doctor` field, NOT patient
   `name`). Constant is in-source (not JSON) because `app/data/` is
   gitignored for PHI safety — keeping the canonical list in Python makes
   it always shippable + git-trackable.

## Why

User asked 2026-05-27: "OCR 抓到的主治醫師名字跟我列的 18 人名單不符的話，
有辦法判斷是哪個嗎？" Gemini already returned the wrong glyph — re-asking
the LLM won't help. A finite canonical list + 1-char-diff fuzzy match
catches >95% of glyph collisions deterministically.

## How to apply

- **Extending canonical list** — edit `CANONICAL_CV_DOCTORS` frozenset at
  the top of `app/services/ocr_service.py`.
- **Adding a known misread that the fuzzy layer doesn't catch** (e.g.
  different length, multi-char diff, ambiguous) — add to
  `OCR_NAME_CORRECTIONS` dict at the top of `ocr_service.py`.
- **NEVER apply fuzzy to patient name** — a real patient named 陳柏勝 is
  plausible and 1 char from canonical 陳柏升. The `is_doctor=False` default
  on `_correct_ocr_name()` enforces this. If a future caller passes a
  doctor field, pass `is_doctor=True` explicitly.
- **Ambiguous case** — if a non-canonical OCR result has ≥2 same-length
  distance-1 canonical neighbors (e.g. 陳柏勝 → 陳柏升 or 陳柏偉?), function
  returns `None` and the name is left alone. Surface to user via the
  Step 1 OCR preview table for manual fix.

Related: [[reference-ocr-doctor-misreads]] (legacy — superseded by this
two-layer scheme), [[corresponding-fields-must-mirror]].
