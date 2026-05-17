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
                 order_header: list[str]) -> list[dict]:
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
    issues = check_issues(structure, main_header, order_header)
    return {"structure": structure, "issues": issues,
            "main_header": main_header, "order_header": order_header}


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

    final = check(date)
    return {"applied": applied,
            "remaining_issues": final["issues"],
            "structure": final["structure"]}
