"""Single source of truth for the NCKUH cardiology attending pool used by:
  - Step 1 OCR fuzzy-match correction (ocr_service)
  - Step 3 EMR visit-anchor matching (emr_service)

When a name is not in this set but is exactly 1 character different from
EXACTLY ONE canonical name (same length), treat it as that canonical name.
Catches glyph collisions like 廖瑤↔廖瑀, 柯星諭↔柯呈諭, 林佳淩↔林佳凌
without per-misread hardcoding.

Keep in sync with the admission lottery sheet (主治醫師抽籤表). Doctors
here must also have a 6-digit code in `app/data/static/doctor_codes.json`
for cathlab keyin.
"""
from __future__ import annotations

from typing import Optional


CANONICAL_CV_DOCTORS: frozenset[str] = frozenset({
    "陳柏升", "劉嚴文", "詹世鴻", "許志新", "陳昭佑", "李柏增",
    "林佳凌", "陳柏偉", "鄭朝允", "陳儒逸", "劉秉彥", "陳則瑋",
    "張獻元", "黃睦翔", "廖瑀", "黃鼎鈞", "柯呈諭", "李文煌",
})


def fuzzy_canonical_match(name: str) -> Optional[str]:
    """Return the canonical CV-attending name that `name` likely refers to,
    or None if no unique match.

    Rules:
      - If `name` is empty → None.
      - If `name` is already canonical → None (no correction needed; caller
        should treat the original as-is).
      - Otherwise, look for canonical names with same length and exactly
        one character difference (Hamming distance = 1).
      - If EXACTLY ONE such neighbor exists → return it.
      - If zero or ≥2 neighbors exist → return None (ambiguous, leave alone).
    """
    if not name or name in CANONICAL_CV_DOCTORS:
        return None
    matches = []
    for canon in CANONICAL_CV_DOCTORS:
        if len(canon) != len(name):
            continue
        if sum(1 for a, b in zip(name, canon) if a != b) == 1:
            matches.append(canon)
            if len(matches) > 1:
                return None
    return matches[0] if len(matches) == 1 else None
