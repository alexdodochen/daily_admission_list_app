---
name: visit-match-norm-unicode
description: "EMR visit-link match must NFC-normalize + strip all whitespace; raw substring miss caused 鄭朝允 visit to be skipped → mis-flagged 無門診紀錄"
metadata:
  type: feedback
---

User correction (2026-05-21):
> 鄭朝允 / 陳淑貞 (1555245) 5/29 這位病人明明有鄭朝允門診紀錄
> 卻顯示 無本院一年內主治醫師門診紀錄

**Root cause:** `fetch_raw_html`'s leftFrame click loop did raw
`text.includes(variant)`. NCKUH EMR anchor text uses fullwidth space
between fields (e.g. `2026/05/29　鄭朝允　門診`) and/or Unicode
compatibility-ideograph siblings — so the raw substring miss skipped
real visits, falling through to FALLBACK_DOCTORS (also miss), and the
patient was wrongly marked 無一年內門診紀錄.

**Fix:**
- JS normalizer: `s.replace(/[\s　 ]+/g,'').normalize('NFC')`
  on BOTH anchor text and every variant/fallback before `includes`.
- Diagnostic: when no match found, return the 門診 anchor texts seen
  in `visit_label` so the EMR card can show what links existed —
  fastest path to diagnose Unicode-sibling / typo cases without
  inspecting the live EMR DOM.

**How to apply:**
- Any future code that compares anchor text / OCR text against a name
  list MUST go through the same norm path. Don't add a parallel raw
  `t.includes(v)` somewhere else and reintroduce the bug.
- If 「鄭朝允」 still doesn't match after this fix → the EMR anchor
  uses a Unicode sibling not handled by NFC; add it to `NAME_ALIASES`
  AND extend the normalizer to fold the specific code-point pair.

**Don't:**
- Don't switch to fuzzy-match (Levenshtein etc.) — false-positives on
  similar doctor names (李文煌 vs 李文燁 etc.) are worse than misses.
  Normalize + alias is the right granularity.
