"""
Step 2 — Build per-doctor sub-tables from main A-L.

This is the FIRST-TIME generator: walks main A-L in row order, groups
patients by 主治醫師 (preserving first-appearance order), and writes one
sub-table block per doctor starting `gap` rows after `main_end`.

Subsequent edits to the patient list go through Step 1 OCR's diff path
(`ocr_service._apply_diff_to_subtables`), which preserves F/G/E/H content.

This module REFUSES to overwrite an existing sub-table area — the user
must use Step 1 OCR overwrite (with diff confirmation) instead.
"""
from __future__ import annotations

from . import sheet_service, format_check_service


SUB_HEADER = ["姓名", "病歷號", "EMR", "EMR摘要", "手動設定入院序",
              "術前診斷", "預計心導管", "註記", "備註(住服)"]
_BLANK_ROW = [""] * len(SUB_HEADER)


def build_subtables_from_main(date: str, gap: int = 2) -> dict:
    """
    Read A-L main, group patients by doctor (preserve first-appearance order),
    write sub-table blocks at A{main_end + 1 + gap}:H{...}.

    Returns:
      {ok, range, doctors: [{doctor, count, patients:[{name,chart_no}]}], patients}
      where `patients` is a flat list in main-table order (used by Step 3
      EMR as default patient list when Step 2 lottery is skipped).

    Raises ValueError if the sheet doesn't exist or sub-tables already exist.
    """
    ws = sheet_service.get_worksheet(date)
    if ws is None:
        raise ValueError(f"找不到工作表 {date}，請先完成 Step 1 OCR")

    # Walk A:H to detect existing sub-tables — refuse to overwrite.
    col_a = [row[0] if row else "" for row in sheet_service.read_range(ws, "A1:A500")]
    structure = format_check_service.parse_structure(col_a)
    real_subs = [s for s in structure["subs"]
                 if s.get("doctor") and not s.get("orphan")]
    if real_subs:
        names = "、".join(s["doctor"] for s in real_subs[:5])
        more = "…" if len(real_subs) > 5 else ""
        raise ValueError(
            f"此日期已有 {len(real_subs)} 個子表格（{names}{more}）。"
            f"請改用 Step 1 OCR 覆寫，子表格會自動同步而不會丟掉已填的 F/G。"
        )

    # Read A-L; collect patients in main-table row order.
    main = sheet_service.read_range(ws, "A2:L200")
    by_doctor: dict[str, list[dict]] = {}
    doctor_order: list[str] = []
    flat: list[dict] = []
    for r in main:
        r = (r + [""] * 12)[:12]
        name  = (r[5] or "").strip()
        if not name:
            break
        doc   = (r[3] or "").strip()
        chart = (r[8] or "").strip()
        if not doc:
            # Patient with no assigned doctor — skip from sub-tables, but still
            # include in the flat list so Step 3 EMR can still query them.
            flat.append({"doctor": "", "name": name, "chart_no": chart})
            continue
        if doc not in by_doctor:
            by_doctor[doc] = []
            doctor_order.append(doc)
        by_doctor[doc].append({"name": name, "chart_no": chart})
        flat.append({"doctor": doc, "name": name, "chart_no": chart})

    if not doctor_order:
        raise ValueError("主表沒有任何已指派醫師的病人，無法產生子表格。")

    main_end = structure["main_end"]
    start_row = main_end + gap + 1
    block: list[list[str]] = []
    for i, doc in enumerate(doctor_order):
        pts = by_doctor[doc]
        block.append([f"{doc}（{len(pts)}人）"] + [""] * (len(SUB_HEADER) - 1))
        block.append(SUB_HEADER)
        for p in pts:
            row = list(_BLANK_ROW)
            row[0] = p["name"]
            row[1] = p["chart_no"]
            block.append(row)
        if i < len(doctor_order) - 1:
            block.append(list(_BLANK_ROW))
            block.append(list(_BLANK_ROW))

    end_row = start_row + len(block) - 1
    # TEXT-format the sub-table 病歷號 column before write so leading zeros
    # survive (USER_ENTERED parses unquoted digit strings as numbers).
    try:
        sheet_service.ensure_chart_text_format(ws)
    except Exception:
        pass
    sheet_service.write_range(ws, f"A{start_row}:I{end_row}", block, raw=False)
    # F/G dropdown rule (allow custom) so users can pick or self-fill in Sheets
    try:
        from . import emr_service
        f_opts, g_opts = emr_service.get_fg_options()
        sheet_service.set_fg_validation(ws, start_row, end_row + 100,
                                        f_opts, g_opts)
    except Exception:
        pass  # cosmetic — don't fail the build

    return {
        "range":   f"A{start_row}:I{end_row}",
        "doctors": [
            {"doctor": doc, "count": len(by_doctor[doc]),
             "patients": by_doctor[doc]}
            for doc in doctor_order
        ],
        "patients": flat,
    }


# ---------------------------- smart rebuild ----------------------------

import re as _re

_TITLE_RE = _re.compile(r"^(.+)（(\d+)人）\s*$")

# Doctor names matching a known main-table COLUMN HEADER label are ghost blocks
# (from a prior bug where OCR returned the header row as a patient → reconcile
# created a block titled e.g. 「主治醫師（0人）」). Smart_rebuild drops them.
_HEADER_GHOST_NAMES = {
    "主治醫師", "姓名", "病歷號", "病歷號碼", "性別", "年齡",
    "科別", "主診斷", "病床號", "入院提示", "住急", "實際住院日", "開刀日",
}


def smart_rebuild(date: str, gap: int = 2) -> dict:
    """Rebuild sub-tables in place, preserving every patient's EMR/F/G/H/I
    across duplicate doctor blocks. Idempotent self-heal for sheets that got
    duplicated blocks or stray rows from earlier re-upload bugs.

    Behaviour:
      1. Read main A-L → ordered list of (doctor, chart_no, name) per patient.
         Main-boundary detection stops at first blank row or sub-table title
         (same rule as ocr_service.write_to_sheet so we don't read sub-table
         rows as main).
      2. Read entire A1:I500 grid. Walk all sub-table blocks (even duplicates).
         For each chart_no, take the row with the LONGEST C col text — that's
         the version with EMR data. Merges F/G/H/I from the chosen row.
      3. Group preserved patients by main A-L doctor first-appearance order
         (orphans whose chart isn't in main are dropped — they shouldn't be
         in sub-tables to begin with).
      4. Write ONE block per doctor at start_row = main_end + gap + 1,
         9-col layout. Clear everything between main_end+1 and start_row-1
         (the gap area) and everything past new_end down to row 250.
      5. Call sync_ordering_after_diff so N-V stays consistent.

    Returns {ok, main_count, doctor_count, patient_count, range,
             preserved, dropped_orphans, n_v_result}.

    Distinct from build_subtables_from_main: that one refuses to run when
    sub-tables already exist (first-time builder). This one is the rescue
    path — never refuses, always overwrites the sub-table area.
    """
    ws = sheet_service.get_worksheet(date)
    if ws is None:
        raise ValueError(f"找不到工作表 {date}")

    # 1) Read main A-L with boundary detection (stops at blank / title row).
    all_main = sheet_service.read_range(ws, "A2:L500")
    main_rows: list[list[str]] = []
    for row in all_main:
        padded = (list(row) + [""] * 12)[:12]
        cell_a = (padded[0] or "").strip()
        if _TITLE_RE.match(cell_a):
            break
        if not any((c or "").strip() for c in padded):
            break
        main_rows.append(padded)

    if not main_rows:
        raise ValueError("主表沒有任何病人，無法重建子表格。請先完成 ① 匯入名單。")

    # Ordered list of (doctor, chart_no, name) for main
    doctor_order: list[str] = []
    by_doctor: dict[str, list[dict]] = {}
    for r in main_rows:
        name  = (r[5] or "").strip()
        doc   = (r[3] or "").strip()
        chart = (r[8] or "").strip()
        if not name or not doc:
            continue
        if doc not in by_doctor:
            by_doctor[doc] = []
            doctor_order.append(doc)
        by_doctor[doc].append({"name": name, "chart_no": chart})

    if not doctor_order:
        raise ValueError("主表沒有任何已指派醫師的病人，無法重建子表格。")

    main_end = 1 + len(main_rows)  # 1-indexed sheet row

    # 2) Walk entire grid; per chart_no keep the row with longest C col.
    grid = sheet_service.read_range(ws, "A1:I250")
    preserved: dict[str, list[str]] = {}     # normalized chart_no → row
    current_doctor: str | None = None
    i = 0
    while i < len(grid):
        cell_a = (grid[i][0] if grid[i] else "").strip()
        if _TITLE_RE.match(cell_a):
            doc_name = cell_a.split("（")[0].strip()
            # Reject ghost blocks (header-row-shaped doctor name).
            current_doctor = doc_name if doc_name not in _HEADER_GHOST_NAMES else None
            i += 1
            continue
        if cell_a == "姓名":
            i += 1
            continue
        if current_doctor:
            row = ((grid[i] or []) + [""] * 9)[:9]
            chart_raw = (row[1] or "").strip()
            if chart_raw:
                key = chart_raw.lstrip("0") or chart_raw
                prev = preserved.get(key)
                if prev is None or len(row[2] or "") > len(prev[2] or ""):
                    preserved[key] = row
        i += 1

    # 3) Build fresh blocks in main doctor order. For each main patient,
    # look up preserved row by chart_no. If not found (sub-table never had
    # them), seed a blank row.
    block: list[list[str]] = []
    start_row = main_end + gap + 1
    width = len(SUB_HEADER)

    for di, doc in enumerate(doctor_order):
        pts = by_doctor[doc]
        block.append([f"{doc}（{len(pts)}人）"] + [""] * (width - 1))
        block.append(list(SUB_HEADER))
        for p in pts:
            chart_full = p["chart_no"]
            key = chart_full.lstrip("0") or chart_full
            row = preserved.get(key)
            if row is None:
                row = [p["name"], chart_full] + [""] * (width - 2)
            else:
                row = list(row)
                row[0] = p["name"]       # main is authoritative for 姓名
                row[1] = chart_full      # and 病歷號 (preserve leading zeros)
            block.append((row + [""] * width)[:width])
        if di < len(doctor_order) - 1:
            block.append([""] * width)
            block.append([""] * width)

    new_end = start_row + len(block) - 1

    # 4) Clear gap rows + write fresh block + clear residual below.
    try:
        sheet_service.ensure_chart_text_format(ws)
    except Exception:
        pass
    if start_row > main_end + 1:
        sheet_service.clear_range(ws, f"A{main_end + 1}:L{start_row - 1}")
    sheet_service.write_range(ws, f"A{start_row}:I{new_end}", block, raw=False)
    sheet_service.clear_range(ws, f"A{new_end + 1}:I250")
    # F/G dropdown
    try:
        from . import emr_service
        f_opts, g_opts = emr_service.get_fg_options()
        sheet_service.set_fg_validation(ws, start_row, new_end + 100,
                                        f_opts, g_opts)
    except Exception:
        pass

    # 5) Re-sync N-V so 序號 + Q/R/T/U match the rebuilt sub-tables.
    n_v: dict = {"updated": False}
    try:
        from . import ordering_service
        n_v = ordering_service.sync_ordering_after_diff(date)
    except Exception as e:
        n_v = {"updated": False, "error": str(e)}

    # Count main charts that ended up with preserved EMR vs blank.
    main_charts = {(p["chart_no"].lstrip("0") or p["chart_no"])
                   for pts in by_doctor.values() for p in pts}
    preserved_with_data = sum(1 for k in main_charts if (preserved.get(k, ["", "", ""])[2] or "").strip())
    dropped_orphans = [k for k in preserved if k not in main_charts]

    return {
        "ok": True,
        "main_count":            len(main_rows),
        "doctor_count":          len(doctor_order),
        "patient_count":         sum(len(v) for v in by_doctor.values()),
        "range":                 f"A{start_row}:I{new_end}",
        "preserved_with_data":   preserved_with_data,
        "dropped_orphans":       dropped_orphans,
        "ordering_update":       n_v,
    }
