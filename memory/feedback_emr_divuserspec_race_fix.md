---
name: emr-divuserspec-race-fix
description: "fetch_raw_html must sentinel-stamp #divUserSpec before BTQuery and poll for sentinel-gone, mirroring _verify_query_and_read. Without it, off-by-one name corruption."
metadata:
  type: feedback
---

User correction (2026-05-21):
> 詹世鴻 / 石文明 (00385733) 這個病人根據EMR應該是 周素珍 卻一直抓石文明

**Root cause:** `fetch_raw_html` in `emr_service.py` was stamping
`leftFrame` + `mainFrame` body innerHTML before BTQuery and polling for
the new visit tree, but `#divUserSpec` (the patient header in a DIFFERENT
frame) was read WITHOUT a sentinel — so it returned the PREVIOUS chart's
data when divUserSpec hadn't yet refreshed after BTQuery click.

This is the EXACT bug that was fixed in `_verify_query_and_read` on 5/12
(commit b3815f9) for the verify_main_emr path — but the main Step 3 EMR
batch loop never got the same fix. The race only manifests on certain
chart_nos in certain batch positions (~once per batch), making it
intermittent in testing but consistent for the affected patient.

**How to apply:**
1. Stamp `#divUserSpec` (across every frame) with the same `sentinel_q`
   used for leftFrame / mainFrame BEFORE calling BTQuery.
2. Poll for BOTH leftFrame readiness AND `#divUserSpec` having a
   non-sentinel value with the `姓名` marker (24 × 0.5s = 12s budget).
3. Add a 400ms settling delay (matches `_verify_query_and_read` pattern).
4. When reading divUserSpec at the end, reject sentinel-echo and require
   `姓名` marker presence — never return a stale stamped value.

**Don't:**
- Don't merge the divUserSpec read INTO the visit-tree poll loop without
  the sentinel — even with `姓名` check, if the stamp is missing the
  previous chart's `姓名` is still in place.
- Don't skip the 400ms settling delay — it's what `_verify_query_and_read`
  found necessary; under load, fast network races even after sentinel-gone.
- Don't try to fix this with `await page.wait_for_function` against
  `#divUserSpec` — the element is in a sibling frame, not the page top.

**Companion fix:** see [[emr-preserve-existing]]. If a prior wrong fetch
already wrote 石文明 to sub-table A, the new preserve-existing rule blocks
C/F/G overwrite — but A is now also patched on EMR canonical-name
difference so the wrong name is automatically corrected on the next run.
