---
name: nckuh-emr-frameset
description: "NCKUH EMR is a frameset — chart query lives in topFrame, clinic record links in leftFrame, SOAP in mainFrame. Playwright must walk frames, not assume single-frame DOM."
metadata: 
  node_type: memory
  type: reference
  originSessionId: 202e121c-0c8f-4e62-891f-fd58ee1476b3
---

NCKUH EMR (hisweb.hosp.ncku/Emrquery) is built on classic ASP.NET frameset.
Playwright cannot reach the chart query input from `page.fill(...)` alone —
must iterate `window.top.frames`.

**Frame map (use named accessors, NOT iterate-all-frames):**
- `window.frames['topFrame']` — chart query form. Input `#txtChartNo`, submit `#BTQuery`.
- `window.frames['leftFrame']` — list of clinic visit links (`<a>` elements with text like
  `2026/04/12 詹世鴻 門診`).
- `window.frames['mainFrame']` — SOAP/note body. Text lives in `div.small` blocks.

**CRITICAL: SOAP extraction must read from `mainFrame` ONLY.** Iterating
all frames (`for (const w of [...window.top.frames])`) picks up `div.small`
blocks from `leftFrame`'s chart-summary INDEX page, which contains the
inpatient boilerplate:
```
住院資料量較大,請點選個別項目後瀏覽
全部摺疊 | 全部展開 | 切換
執行時間 : 00:00:01.656s (Complete)
```
This noise pollutes C/F/G in the sub-table and breaks downstream cathlab
detection. The fix is to use `window.frames['mainFrame'].document.querySelectorAll('div.small')`.

**Sentinel-based wait pattern** (anti-race-condition for batch fetches):
Before each chart query, stamp `leftFrame.body.innerHTML` and
`mainFrame.body.innerHTML` with a unique sentinel comment (e.g.
`<!--FETCH-23303683-1747299010000-QUERY-->`). Then poll up to 12 s, looking
for: (a) sentinel no longer present, (b) real visit anchors / SOAP content.
Without sentinels, the next chart's query can read stale content from
the previous one because the EMR app's frame reload isn't atomic with
`networkidle`.

**Boilerplate detection:** when SOAP text contains ≥ 2 of `["住院資料量較大",
"請點選個別項目", "全部摺疊", "全部展開"]`, it's the chart-summary index
page and should be treated as `has_record=False` with body =
`INPATIENT_ONLY_TEXT` ("查無門診紀錄（病人僅有住院資料 / 需手動點開個別住院記錄）").

**NAME_ALIASES** (Unicode siblings):
```
"林佳凌": ["林佳凌", "林佳淩"]   # 凌 ↔ 淩
"林佳淩": ["林佳凌", "林佳淩"]
```
EMR anchors sometimes have one variant where DOCTOR_CODES uses the other.
Always look for both when matching `doctor` in leftFrame anchors.

**Fallback doctors** (when assigned 主治醫師 has no 一年內門診紀錄):
```
FALLBACK_DOCTORS = ['劉秉彥', '趙庭興', '蔡惟全', '許志新', '陳柏升', '李貽恒']
```
Search leftFrame anchors for `text.includes('門診') && text.includes(doctorName)`.
If primary doctor has no match, iterate FALLBACK_DOCTORS. Hospitals share consult
patterns so a fallback's note is usually still relevant.

**Patient header** `#divUserSpec` may live in any frame — walk all frames to find.

**Implementation:** see `app/services/emr_service.py::fetch_raw_html`. Returns
`(soap_text, div_user_spec, visit_label)` where visit_label tells which
doctor's note was actually used (surface this to user so they don't assume
their own doctor's record was read).

**Why this matters:** previously the app used `await page.fill("input[name='chartno']", ...)`
which silently failed inside the frameset and returned empty SOAP. User reported
"無本院一年內主治醫師門診紀錄 還是都沒抓到門診紀錄" — symptom was empty F/G + empty C col after Step 3.

**How to apply:**
- Any new EMR-page Playwright code must use frame-walk pattern.
- Reference port: `daily-admission-list-public/fetch_emr.py` on GitHub (alexdodochen).
- Test by querying a chart where the assigned 主治醫師 has NO recent clinic
  visit — expect fallback doctor's note + non-empty `visit_label`.
