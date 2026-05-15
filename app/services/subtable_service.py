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


SUB_HEADER = ["姓名", "病歷號", "EMR", "summary", "入院序",
              "術前診斷", "預計心導管", "註記"]


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
        block.append([f"{doc}（{len(pts)}人）", "", "", "", "", "", "", ""])
        block.append(SUB_HEADER)
        for p in pts:
            block.append([p["name"], p["chart_no"], "", "", "", "", "", ""])
        if i < len(doctor_order) - 1:
            block.append([""] * 8)
            block.append([""] * 8)

    end_row = start_row + len(block) - 1
    # TEXT-format the sub-table 病歷號 column before write so leading zeros
    # survive (USER_ENTERED parses unquoted digit strings as numbers).
    try:
        sheet_service.ensure_chart_text_format(ws)
    except Exception:
        pass
    sheet_service.write_range(ws, f"A{start_row}:H{end_row}", block, raw=False)
    # F/G dropdown rule (allow custom) so users can pick or self-fill in Sheets
    try:
        from . import emr_service
        f_opts, g_opts = emr_service.get_fg_options()
        sheet_service.set_fg_validation(ws, start_row, end_row + 100,
                                        f_opts, g_opts)
    except Exception:
        pass  # cosmetic — don't fail the build

    return {
        "range":   f"A{start_row}:H{end_row}",
        "doctors": [
            {"doctor": doc, "count": len(by_doctor[doc]),
             "patients": by_doctor[doc]}
            for doc in doctor_order
        ],
        "patients": flat,
    }
