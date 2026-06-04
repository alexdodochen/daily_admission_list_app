"""
Pre-finalization (定案) readiness checklist for a date sheet.

Before running Step 5 (cathlab keyin) or Step 6 (LINE push), we want a
one-look summary of whether the sheet is actually ready:

  1. Layout: format-check must be clean (headers / subtable counts / gaps).
  2. Main data: every patient row has 主治醫師 / 姓名 / 病歷號.
  3. Sub-tables: every patient has F (術前診斷) + G (預計心導管) filled.
  4. Ordering: N-row count matches main-data row count.

This module READS only — no writes. It's a gate, not a fixer.
"""
from __future__ import annotations

from . import sheet_service, format_check_service


def _check_main_data(ws, main_end: int) -> dict:
    """Main-data D/F/I (醫師/姓名/病歷號) non-empty."""
    if main_end <= 1:
        return {"id": "main_data",
                "label": "主資料 D/F/I 欄（醫師/姓名/病歷號）不空",
                "ok": False, "detail": "主資料為空（A2 起沒有病人）"}
    rows = sheet_service.read_range(ws, f"A2:L{main_end}") or []
    missing: list[str] = []
    for i, r in enumerate(rows):
        p = (r + [""] * 12)[:12]
        lack = []
        if not p[3].strip(): lack.append("醫師")
        if not p[5].strip(): lack.append("姓名")
        if not p[8].strip(): lack.append("病歷號")
        if lack:
            missing.append(f"第 {i + 2} 列缺 {'/'.join(lack)}")
    return {"id": "main_data",
            "label": "主資料 D/F/I 欄（醫師/姓名/病歷號）不空",
            "ok": not missing,
            "detail": "; ".join(missing[:5])}


def _check_subtable_fg(ws, subs: list[dict]) -> dict:
    """Every sub-table patient must have F (診斷) and G (預計心導管) filled."""
    missing: list[str] = []
    for s in subs:
        if s["orphan"] or not s["first_patient_row"]:
            continue
        first, last = s["first_patient_row"], s["last_patient_row"]
        fg = sheet_service.read_range(ws, f"F{first}:G{last}") or []
        for i, row in enumerate(fg):
            p = (row + ["", ""])[:2]
            lack = []
            if not p[0].strip(): lack.append("F")
            if not p[1].strip(): lack.append("G")
            if lack:
                missing.append(f"{s['doctor']} 第 {first + i} 列缺 {'/'.join(lack)}")
    return {"id": "sub_fg",
            "label": "子表格 F/G 欄（術前診斷/預計心導管）已填",
            "ok": not missing,
            "detail": "; ".join(missing[:5])}


def _check_ordering(ws, main_end: int) -> dict:
    """N-row patient count must match main-data count."""
    rows = sheet_service.read_range(ws, "N2:U200") or []
    while rows and not any((c or "").strip() for c in rows[-1]):
        rows.pop()
    order_count = len(rows)
    main_count = max(0, main_end - 1)

    if main_count == 0:
        return {"id": "ordering",
                "label": "入院序人數與主資料一致",
                "ok": False, "detail": "主資料為空，無法判斷"}
    if order_count == 0:
        return {"id": "ordering",
                "label": "入院序人數與主資料一致",
                "ok": False,
                "detail": f"N-U 未寫入（主資料 {main_count} 位）"}
    if order_count != main_count:
        return {"id": "ordering",
                "label": "入院序人數與主資料一致",
                "ok": False,
                "detail": f"入院序 {order_count} 位 ≠ 主資料 {main_count} 位"}
    return {"id": "ordering",
            "label": "入院序人數與主資料一致",
            "ok": True, "detail": ""}


def check_ready(date: str) -> dict:
    """Return {ready: bool, checks: [{id,label,ok,detail}]} for the date sheet."""
    ws = sheet_service.get_worksheet(date)
    if ws is None:
        return {"error": f"找不到工作表 {date}", "ready": False, "checks": []}

    fc = format_check_service.check(date)
    if "error" in fc:
        return {"error": fc["error"], "ready": False, "checks": []}

    checks: list[dict] = []
    format_ok = not fc["issues"]
    checks.append({
        "id": "format",
        "label": "格式檢查（表頭/子表格/空白行）",
        "ok": format_ok,
        "detail": "" if format_ok else f"{len(fc['issues'])} 項格式問題（請先跑檢查格式）",
    })

    structure = fc["structure"]
    main_end = structure["main_end"]

    checks.append(_check_main_data(ws, main_end))
    checks.append(_check_subtable_fg(ws, structure["subs"]))
    checks.append(_check_ordering(ws, main_end))

    return {"ready": all(c["ok"] for c in checks), "checks": checks}
