"""
Format check — read-back verification + auto-fix for date sheets.

Ported from the admission-format-check skill. Minimum viable scope:

  * main A-L header is the canonical 12-col layout
  * N-V header is the canonical 9-col ordering layout
  * sub-table titles `X（N人）` have N matching actual patient count
  * gap ≥ 2 blank rows between main data & first sub-table and between subs
  * 病歷號 columns (main I / N-V S / sub B) are TEXT format so leading zeros stick

Fixable by this service:
  - gap_too_small            → insertDimension rows
  - subtable_count_mismatch  → rewrite title text
  - main_header_missing      → rewrite A1:L1
  - order_header_wrong       → rewrite N1:V1 (9-col layout)
  - chart_text_format        → repeatCell numberFormat TEXT

Not fixable here (reported for user action):
  - subtable_missing_title (need to guess doctor — leave to user)
"""
from __future__ import annotations

import re
from typing import Optional

from . import sheet_service


EXPECTED_MAIN_HEADER = [
    "實際住院日", "開刀日", "科別", "主治醫師", "主診斷(ICD)",
    "姓名", "性別", "年齡", "病歷號碼", "病床號", "入院提示", "住急",
]
EXPECTED_ORDER_HEADER = [
    "序號", "主治醫師", "病人姓名", "備註(住服)", "備註",
    "病歷號", "術前診斷", "預計心導管", "改期",
]
# Canonical SUB_HEADER row labels — aligned with daily-admission-list-public.
# Column I (備註(住服)) added 2026-05-25 so the 住服 marker has a per-patient
# home in the sub-table that mirrors to N-V Q.
EXPECTED_SUB_HEADER = [
    "姓名", "病歷號", "EMR", "EMR摘要", "手動設定入院序",
    "術前診斷", "預計心導管", "註記", "備註(住服)",
]

TITLE_RE = re.compile(r"^(.+)（(\d+)人）$")


# -------------------------------- pure parsing --------------------------------

def parse_structure(col_a: list[str]) -> dict:
    """
    Given 0-indexed list of col-A values (index 0 = row 1), return:

      {
        "main_end": <1-indexed row number of last main-data row, 1 if empty>,
        "subs": [
          {
            "doctor":            str,
            "declared":          int,
            "title_row":         int,   # 1-indexed
            "subheader_row":     int | None,
            "first_patient_row": int | None,
            "last_patient_row":  int | None,  # 1-indexed, inclusive
            "actual_count":      int,
            "orphan":            bool,  # True → sub-header without title
          }, ...
        ],
      }
    """
    n = len(col_a)
    # main_end: walk from row 2 (index 1) while value is non-empty and not a title
    main_end = 1
    i = 1
    while i < n:
        v = (col_a[i] or "").strip()
        if not v or TITLE_RE.match(v):
            break
        main_end = i + 1
        i += 1

    subs: list[dict] = []
    j = i
    while j < n:
        v = (col_a[j] or "").strip()
        m = TITLE_RE.match(v)
        if m:
            doctor = m.group(1).strip()
            declared = int(m.group(2))
            title_row = j + 1
            k = j + 1
            subheader_row: Optional[int] = None
            if k < n and (col_a[k] or "").strip() == "姓名":
                subheader_row = k + 1
                k += 1
            first_patient_row: Optional[int] = None
            while k < n:
                vv = (col_a[k] or "").strip()
                if not vv or TITLE_RE.match(vv):
                    break
                if first_patient_row is None:
                    first_patient_row = k + 1
                k += 1
            last_patient_row = k if first_patient_row is not None else None
            actual = 0 if first_patient_row is None else (last_patient_row - first_patient_row + 1)
            subs.append({
                "doctor":            doctor,
                "declared":          declared,
                "title_row":         title_row,
                "subheader_row":     subheader_row,
                "first_patient_row": first_patient_row,
                "last_patient_row":  last_patient_row,
                "actual_count":      actual,
                "orphan":            False,
            })
            j = k
        elif v == "姓名":
            subs.append({
                "doctor": None, "declared": None,
                "title_row": None, "subheader_row": j + 1,
                "first_patient_row": None, "last_patient_row": None,
                "actual_count": 0, "orphan": True,
            })
            j += 1
        else:
            j += 1

    return {"main_end": main_end, "subs": subs}


def check_issues(structure: dict,
                 main_header: list[str],
                 order_header: list[str],
                 sub_headers: dict[int, list[str]] | None = None,
                 main_patients: list[dict] | None = None,
                 sub_patients: list[dict] | None = None) -> list[dict]:
    """
    `main_patients`: list of {chart_no, name, doctor, row} from main A-L (col I).
    `sub_patients`:  list of {chart_no, name, doctor, row} from every sub-table
                     patient row (col B). Both optional — when omitted, the
                     cross-block checks (duplicate doctor block, orphan,
                     missing-from-subtable, doctor-not-in-main) are skipped.
    """
    issues: list[dict] = []

    if main_header != EXPECTED_MAIN_HEADER:
        issues.append({"type": "main_header_missing",
                       "expected": EXPECTED_MAIN_HEADER,
                       "actual":   main_header,
                       "fixable":  True})

    if order_header != EXPECTED_ORDER_HEADER:
        issues.append({"type": "order_header_wrong",
                       "expected": EXPECTED_ORDER_HEADER,
                       "actual":   order_header,
                       "fixable":  True})

    sub_headers = sub_headers or {}
    for s in structure["subs"]:
        sub_row = s.get("subheader_row")
        if not sub_row or s.get("orphan"):
            continue
        actual = sub_headers.get(sub_row, [])
        actual_padded = (actual + [""] * len(EXPECTED_SUB_HEADER))[:len(EXPECTED_SUB_HEADER)]
        if actual_padded != EXPECTED_SUB_HEADER:
            issues.append({
                "type":     "sub_header_wrong",
                "doctor":   s.get("doctor"),
                "row":      sub_row,
                "expected": EXPECTED_SUB_HEADER,
                "actual":   actual_padded,
                "fixable":  True,
            })

    main_end = structure["main_end"]
    prev_last = main_end
    for s in structure["subs"]:
        if s["orphan"]:
            issues.append({
                "type": "subtable_missing_title",
                "subheader_row": s["subheader_row"],
                "fixable": False,
            })
            continue

        if s["actual_count"] != s["declared"]:
            issues.append({
                "type":       "subtable_count_mismatch",
                "doctor":     s["doctor"],
                "declared":   s["declared"],
                "actual":     s["actual_count"],
                "title_row":  s["title_row"],
                "fixable":    True,
            })

        gap = s["title_row"] - prev_last - 1
        if gap < 2:
            issues.append({
                "type":         "gap_too_small",
                "title_row":    s["title_row"],
                "doctor":       s["doctor"],
                "gap":          gap,
                "need_insert":  2 - gap,
                "fixable":      True,
            })
        # prev_last for next iteration: use last patient or title+1 if empty
        prev_last = s["last_patient_row"] or s["subheader_row"] or s["title_row"]

    # --- Cross-block content checks (only when main / sub patient lists supplied
    # AND main is non-empty — without main data we can't decide what blocks
    # are orphans). Test fixtures often skip these so we don't false-positive. ---
    if main_patients and sub_patients is not None:
        # 1. Duplicate doctor block — same doctor title appears 2+ times.
        seen_doctors: dict[str, int] = {}
        for s in structure["subs"]:
            doc = s.get("doctor")
            if doc and not s.get("orphan"):
                seen_doctors[doc] = seen_doctors.get(doc, 0) + 1
        for doc, count in seen_doctors.items():
            if count > 1:
                rows = [s["title_row"] for s in structure["subs"]
                        if s.get("doctor") == doc and not s.get("orphan")]
                issues.append({
                    "type":    "duplicate_doctor_block",
                    "doctor":  doc,
                    "count":   count,
                    "rows":    rows,
                    "fixable": True,            # smart_rebuild merges them
                })

        # Normalize chart_no for matching (strip leading zeros).
        def norm(c: str) -> str:
            c = (c or "").strip()
            return c.lstrip("0") or c

        main_charts = {norm(p["chart_no"]) for p in main_patients
                       if p.get("chart_no")}
        sub_charts: dict[str, list[dict]] = {}
        for p in sub_patients:
            k = norm(p.get("chart_no", ""))
            if not k:
                continue
            sub_charts.setdefault(k, []).append(p)
        main_by_chart = {norm(p["chart_no"]): p for p in main_patients
                         if p.get("chart_no")}

        # 2. Orphan in sub-table: chart_no exists in sub-table but NOT in main.
        for k, rows in sub_charts.items():
            if k not in main_charts:
                for p in rows:
                    issues.append({
                        "type":      "subtable_orphan_chart",
                        "chart_no":  p["chart_no"],
                        "name":      p.get("name", ""),
                        "doctor":    p.get("doctor", ""),
                        "row":       p.get("row"),
                        "fixable":   True,      # smart_rebuild drops orphans
                    })

        # 3. Main chart missing from every sub-table.
        for k, p in main_by_chart.items():
            if k not in sub_charts:
                issues.append({
                    "type":     "main_chart_missing_from_subtable",
                    "chart_no": p["chart_no"],
                    "name":     p.get("name", ""),
                    "doctor":   p.get("doctor", ""),
                    "row":      p.get("row"),
                    "fixable":  True,           # smart_rebuild adds it back
                })

        # 4. Sub-table block for a doctor who has no main patient.
        main_doctors = {p.get("doctor", "") for p in main_patients
                        if p.get("doctor")}
        for s in structure["subs"]:
            doc = s.get("doctor")
            if doc and not s.get("orphan") and doc not in main_doctors:
                # de-dup by doctor (one issue per doctor, not per duplicate block)
                if not any(i["type"] == "subtable_doctor_not_in_main"
                           and i["doctor"] == doc for i in issues):
                    issues.append({
                        "type":     "subtable_doctor_not_in_main",
                        "doctor":   doc,
                        "title_row": s["title_row"],
                        "fixable":  True,       # smart_rebuild drops the block
                    })

        # 5. Doctor mismatch — chart's main doctor ≠ chart's sub-table doctor.
        for k, rows in sub_charts.items():
            if k not in main_by_chart:
                continue
            main_doc = (main_by_chart[k].get("doctor") or "").strip()
            for p in rows:
                sub_doc = (p.get("doctor") or "").strip()
                if main_doc and sub_doc and main_doc != sub_doc:
                    issues.append({
                        "type":      "subtable_doctor_mismatch",
                        "chart_no":  p["chart_no"],
                        "name":      p.get("name", ""),
                        "main_doctor": main_doc,
                        "sub_doctor":  sub_doc,
                        "row":       p.get("row"),
                        "fixable":   True,      # smart_rebuild re-buckets by main
                    })

    return issues


# -------------------------------- I/O layer ----------------------------------

def _read_col_a(ws) -> list[str]:
    """Return col-A values as 0-indexed list padded to 500 rows."""
    rows = sheet_service.read_range(ws, "A1:A500")
    out = [(r[0] if r else "") for r in rows]
    while len(out) < 500:
        out.append("")
    return out


def ensure_fg_validation(date: str) -> dict:
    """Idempotently (re-)assert the native F/G dropdown on a date sheet's
    sub-table area.

    Self-heal path: a sheet whose sub-tables were built while the Google
    service-account credential was broken got its `set_fg_validation()`
    batch_update swallowed by the `except: pass  # cosmetic` guards, so the
    sheet ended up with no native F/G dropdown. Loading an existing sheet never
    re-applied it, so the dropdown stayed missing even after creds were fixed.
    The `/api/step4/subtables` read (hit by the 載入既有 sheet flow) calls this
    so the dropdown re-appears on the next load once creds work.

    Returns {"applied": bool, "rows": (start, end) | None}.
    """
    ws = sheet_service.get_worksheet(date)
    if ws is None:
        return {"applied": False, "rows": None}
    subs = parse_structure(_read_col_a(ws)).get("subs") or []
    starts = [s["subheader_row"] + 1 for s in subs if s.get("subheader_row")]
    ends = [s["last_patient_row"] for s in subs if s.get("last_patient_row")]
    if not starts or not ends:
        return {"applied": False, "rows": None}
    start, end = min(starts), max(ends)
    from . import emr_service  # lazy: emr_service imports sheet_service
    f_opts, g_opts = emr_service.get_fg_options()
    sheet_service.set_fg_validation(ws, start, end + 100, f_opts, g_opts)
    return {"applied": True, "rows": (start, end)}


def check(date: str) -> dict:
    ws = sheet_service.get_worksheet(date)
    if ws is None:
        return {"error": f"找不到工作表 {date}",
                "structure": None, "issues": []}

    col_a = _read_col_a(ws)
    main_row = sheet_service.read_range(ws, "A1:L1")
    main_header = main_row[0] if main_row else []
    # Pad to length 12 so comparisons are stable
    main_header = (main_header + [""] * 12)[:12]

    order_row = sheet_service.read_range(ws, "N1:V1")
    order_header = order_row[0] if order_row else []
    order_header = (order_header + [""] * 9)[:9]

    structure = parse_structure(col_a)

    # Read each sub-table's subheader row (A:I) for SUB_HEADER validation.
    sub_headers: dict[int, list[str]] = {}
    for s in structure["subs"]:
        row = s.get("subheader_row")
        if not row or s.get("orphan"):
            continue
        got = sheet_service.read_range(ws, f"A{row}:I{row}")
        sub_headers[row] = (got[0] if got else [])

    # Read main patients (chart_no in col I = idx 8, doctor in col D = idx 3,
    # name in col F = idx 5) up to main_end.
    main_patients: list[dict] = []
    main_end = structure.get("main_end", 1)
    if main_end >= 2:
        body = sheet_service.read_range(ws, f"A2:L{main_end}")
        for i, r in enumerate(body, start=2):
            r = (list(r) + [""] * 12)[:12]
            chart = (r[8] or "").strip()
            if not chart:
                continue
            main_patients.append({
                "row":      i,
                "chart_no": chart,
                "name":     (r[5] or "").strip(),
                "doctor":   (r[3] or "").strip(),
            })

    # Read sub-table patient rows (col A = name, col B = chart_no) for every
    # sub-table block, tagged with their block's doctor.
    sub_patients: list[dict] = []
    for s in structure["subs"]:
        if s.get("orphan") or not s.get("first_patient_row"):
            continue
        doc = s.get("doctor", "")
        rng = f"A{s['first_patient_row']}:B{s['last_patient_row']}"
        body = sheet_service.read_range(ws, rng)
        for i, r in enumerate(body):
            r = (list(r) + ["", ""])[:2]
            chart = (r[1] or "").strip()
            if not chart:
                continue
            sub_patients.append({
                "row":      s["first_patient_row"] + i,
                "chart_no": chart,
                "name":     (r[0] or "").strip(),
                "doctor":   doc,
            })

    issues = check_issues(structure, main_header, order_header, sub_headers,
                          main_patients=main_patients,
                          sub_patients=sub_patients)
    return {"structure": structure, "issues": issues,
            "main_header": main_header, "order_header": order_header,
            "sub_headers": sub_headers}


def _text_fmt_req(sheet_id: int, start_col: int, end_col: int,
                  start_row: int = 0, end_row: int = 500) -> dict:
    """Build a repeatCell request that forces TEXT numberFormat."""
    return {
        "repeatCell": {
            "range": {"sheetId": sheet_id,
                      "startRowIndex": start_row, "endRowIndex": end_row,
                      "startColumnIndex": start_col, "endColumnIndex": end_col},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "TEXT"}}},
            "fields": "userEnteredFormat.numberFormat",
        }
    }


def fix(date: str, types: Optional[list[str]] = None) -> dict:
    """
    Apply auto-fixes. If `types` is None → apply every fixable type we know.
    Otherwise only apply the named types.

    Execution order:
      1. gap_too_small — insertDimension (bottom-up so row indices stay valid)
      2. re-read structure (gaps shifted row numbers)
      3. subtable_count_mismatch — rewrite title text
      4. main_header_missing / order_header_wrong — rewrite row 1
      5. chart_text_format — repeatCell TEXT on cols I / S / B (B only
         below main data)
    """
    ws = sheet_service.get_worksheet(date)
    if ws is None:
        return {"error": f"找不到工作表 {date}", "applied": [], "remaining_issues": []}

    sh = sheet_service.get_spreadsheet()
    snapshot = check(date)
    issues = snapshot["issues"]
    applied: list[dict] = []

    def want(t: str) -> bool:
        return types is None or t in types

    # 1. gap fixes — insert rows bottom-up
    gap_issues = [i for i in issues if i["type"] == "gap_too_small" and want("gap_too_small")]
    if gap_issues:
        requests = []
        for issue in sorted(gap_issues, key=lambda x: -x["title_row"]):
            requests.append({
                "insertDimension": {
                    "range": {"sheetId": ws.id, "dimension": "ROWS",
                              "startIndex": issue["title_row"] - 1,
                              "endIndex": issue["title_row"] - 1 + issue["need_insert"]},
                    "inheritFromBefore": False,
                }
            })
            applied.append(issue)
        sh.batch_update({"requests": requests})

    # 2. header rewrites
    header_requests = []
    if any(i["type"] == "main_header_missing" for i in issues) and want("main_header_missing"):
        sheet_service.write_range(ws, "A1:L1", [EXPECTED_MAIN_HEADER], raw=False)
        applied.append({"type": "main_header_missing"})
    if any(i["type"] == "order_header_wrong" for i in issues) and want("order_header_wrong"):
        sheet_service.write_range(ws, "N1:V1", [EXPECTED_ORDER_HEADER], raw=False)
        applied.append({"type": "order_header_wrong"})
    if want("sub_header_wrong"):
        for issue in [i for i in issues if i["type"] == "sub_header_wrong"]:
            sheet_service.write_range(ws, f"A{issue['row']}:I{issue['row']}",
                                      [EXPECTED_SUB_HEADER], raw=False)
            applied.append(issue)

    # 3. re-read structure (gap inserts / title moves) before count fix
    if gap_issues:
        snapshot = check(date)

    # 4. count rewrites
    count_issues = [i for i in snapshot["issues"]
                    if i["type"] == "subtable_count_mismatch"
                    and want("subtable_count_mismatch")]
    for issue in count_issues:
        new_title = f"{issue['doctor']}（{issue['actual']}人）"
        sheet_service.write_range(ws, f"A{issue['title_row']}",
                                  [[new_title]], raw=False)
        applied.append(issue)

    # 5. chart-number text format
    if want("chart_text_format"):
        main_end = snapshot["structure"]["main_end"]
        sh.batch_update({"requests": [
            # Main I (col index 8) rows 2..500
            _text_fmt_req(ws.id, 8, 9, 1, 500),
            # N-V S (col index 18) rows 2..500
            _text_fmt_req(ws.id, 18, 19, 1, 500),
            # Sub-tables B (col index 1) below main data
            _text_fmt_req(ws.id, 1, 2, main_end, 500),
        ]})
        applied.append({"type": "chart_text_format"})

    # 6. Cross-block content issues (duplicate doctor block, orphan, missing,
    # doctor not in main, doctor mismatch). All resolved by smart_rebuild —
    # one call rebuilds the whole sub-table area dedup'd against main A-L.
    # smart_rebuild preserves EMR/F/G/H/I per chart, so this is safe to chain.
    REBUILD_TYPES = {
        "duplicate_doctor_block", "subtable_orphan_chart",
        "main_chart_missing_from_subtable",
        "subtable_doctor_not_in_main", "subtable_doctor_mismatch",
    }
    rebuild_issues = [i for i in snapshot["issues"]
                      if i["type"] in REBUILD_TYPES and want(i["type"])]
    if rebuild_issues:
        try:
            from . import subtable_service
            rb = subtable_service.smart_rebuild(date)
            for i in rebuild_issues:
                applied.append({**i, "rebuild": rb})
        except Exception as e:
            for i in rebuild_issues:
                applied.append({**i, "rebuild_error": str(e)})

    final = check(date)
    return {"applied": applied,
            "remaining_issues": final["issues"],
            "structure": final["structure"]}
