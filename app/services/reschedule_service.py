"""
Reschedule — two modes.

Mode 1 (V-flag only): mark V column with target YYYYMMDD on source date sheet.
  - cathlab_service.read_patients already honours this via _read_v_markers
    → patient is marked skip + note adds [改期→YYYYMMDD].
  - No main A-L copy, no WEBCVIS DEL, no new cathlab ADD.

Mode 2 (full-move, when user says 「重啟改期功能」or 「改 MM/DD 住院」 with patient list):
  - V mark on source date sheet
  - Main A-L row copy to target date sheet (ensure_date_sheet first)
  - Sub-table rebuild on target (doctor block append-or-grow)
  - WEBCVIS DEL on source cathlab date (cathlab_service.del_charts)
  - cathlab ADD on target date (via standard keyin)

This module exposes pure-logic plan + the writeback for V flag. The
full-move workflow is orchestrated by `apply_full_move()` which
sequences sheet writes + cathlab DEL/ADD with explicit user confirmation
between phases (per feedback_webcvis_del_manual.md).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from . import sheet_service, cathlab_service


def parse_target_date(s: str) -> str:
    """Normalize user-given target date to YYYYMMDD.
    Accepts YYYYMMDD, YYYY/MM/DD, YYYY-MM-DD. Validates calendar date."""
    raw = (s or "").strip().replace("/", "").replace("-", "")
    if len(raw) != 8 or not raw.isdigit():
        raise ValueError(f"Invalid target date: {s!r} (expected YYYYMMDD)")
    try:
        datetime.strptime(raw, "%Y%m%d")
    except ValueError as e:
        raise ValueError(f"Invalid target date: {s!r} ({e})")
    return raw


def plan_v_flag(date: str, chart_targets: dict[str, str]) -> dict:
    """
    Validate target dates + locate each chart's row in main A-L and the
    ordering row to receive the V mark.

    Args:
      date: source date sheet (YYYYMMDD).
      chart_targets: {chart_no: target_date} (target accepted as YYYYMMDD or YYYY/MM/DD).

    Returns:
      {
        "date": "...",
        "patches": [{"chart": ..., "target": "YYYYMMDD",
                     "main_row": int | None,
                     "ordering_row": int | None}],
        "missing": [chart_no, ...],   # charts not in main A-L
      }
    """
    ws = sheet_service.get_worksheet(date)
    if ws is None:
        raise ValueError(f"找不到工作表 {date}")
    main = sheet_service.read_range(ws, "A2:L200") or []
    ordering = sheet_service.read_range(ws, "N2:V200") or []

    main_idx = {}
    for i, r in enumerate(main):
        rr = (r + [""] * 12)[:12]
        chart = rr[8].strip()
        if chart:
            main_idx[chart] = i + 2  # 1-based sheet row

    order_idx = {}
    for i, r in enumerate(ordering):
        rr = (r + [""] * 9)[:9]
        chart = rr[5].strip()
        if chart:
            order_idx[chart] = i + 2

    patches = []
    missing = []
    for chart, target in chart_targets.items():
        try:
            tgt = parse_target_date(target)
        except ValueError as e:
            raise ValueError(f"{chart}: {e}")
        if chart not in main_idx:
            missing.append(chart)
            continue
        patches.append({
            "chart": chart,
            "target": tgt,
            "main_row": main_idx.get(chart),
            "ordering_row": order_idx.get(chart),
        })
    return {"date": date, "patches": patches, "missing": missing}


def apply_v_flag(date: str, chart_targets: dict[str, str]) -> dict:
    """
    Write V (改期) cell for each chart in the ordering block.
    Charts without an ordering row are reported in `skipped` (V flag has no
    home — caller should run integrate_ordering first).
    """
    p = plan_v_flag(date, chart_targets)
    ws = sheet_service.get_worksheet(date)
    written: list[dict] = []
    skipped: list[dict] = []
    for patch in p["patches"]:
        row = patch["ordering_row"]
        if not row:
            skipped.append({**patch, "reason": "no ordering row — run Step 4 first"})
            continue
        sheet_service.write_range(ws, f"V{row}:V{row}", [[patch["target"]]], raw=False)
        written.append(patch)
    return {
        "date": date,
        "written": written,
        "skipped": skipped,
        "missing": p["missing"],
    }


def plan_full_move(date: str, chart_targets: dict[str, str]) -> dict:
    """
    Plan a full reschedule move. Produces:
      - main A-L rows to copy per target date
      - cathlab DEL list (chart + source cath_date)
      - cathlab ADD list (chart + target cath_date) — actual keyin re-uses
        the standard plan/keyin pipeline on the target date after sub-table
        rebuild is done.

    Source cath_date is derived from cathlab_service.get_cathlab_date on the
    source admit date + doctor + note (mirrors the same rule cathlab itself
    used). Caller must verify each entry before sending DELs.
    """
    p = plan_v_flag(date, chart_targets)
    ws = sheet_service.get_worksheet(date)
    main = sheet_service.read_range(ws, "A2:L200") or []

    main_by_chart: dict[str, list[str]] = {}
    for r in main:
        rr = (r + [""] * 12)[:12]
        chart = rr[8].strip()
        if chart:
            main_by_chart[chart] = rr

    move_rows: dict[str, list[list[str]]] = {}  # target_date → list of A-L rows
    del_list: list[dict] = []
    for patch in p["patches"]:
        row = main_by_chart.get(patch["chart"])
        if not row:
            continue
        move_rows.setdefault(patch["target"], []).append(row)
        doctor = row[3].strip()
        # Use note from sheet col K (入院提示, idx 10) for cath date hints
        note = row[10] if len(row) > 10 else ""
        source_cath = cathlab_service.get_cathlab_date(date, doctor, note)
        del_list.append({
            "chart": patch["chart"],
            "name": row[5].strip() if len(row) > 5 else "",
            "doctor": doctor,
            "source_cath_date": source_cath,
            "target_admit_date": patch["target"],
        })
    return {
        "date": date,
        "v_patches": p["patches"],
        "missing": p["missing"],
        "move_rows_by_target": move_rows,
        "del_list": del_list,
    }


def append_rows_to_target(target_date: str, rows: list[list[str]]) -> dict:
    """
    Append A-L rows to target date sheet's main data area (after last
    populated row). Caller is expected to have run ensure_date_sheet or
    similar to guarantee the target sheet exists with headers.
    """
    ws = sheet_service.get_worksheet(target_date)
    if ws is None:
        raise ValueError(f"找不到目標工作表 {target_date}（請先建立）")
    existing = sheet_service.read_range(ws, "A2:L500") or []
    last_filled = 1
    for i, r in enumerate(existing):
        rr = (r + [""] * 12)[:12]
        if any(c.strip() for c in rr):
            last_filled = i + 2
    start = last_filled + 1
    if not rows:
        return {"target": target_date, "appended": 0, "range": ""}
    end = start + len(rows) - 1
    sheet_service.write_range(ws, f"A{start}:L{end}", rows, raw=False)
    return {"target": target_date, "appended": len(rows), "range": f"A{start}:L{end}"}
