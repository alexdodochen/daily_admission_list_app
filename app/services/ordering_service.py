"""
Step 4 — Ordering.

After the user confirms F (術前診斷) and G (預計心導管) in each doctor
sub-table, we rebuild the N–V ordered list (9 columns):

  N=序號 | O=主治醫師 | P=病人姓名 | Q=備註(住服) | R=備註
  S=病歷號 | T=術前診斷 | U=預計心導管 | V=改期

Hard rules (CLAUDE.md 1, 17, 18 + feedback memories):
  - Q (備註(住服)) never auto-defaults to "V" — preserved verbatim from the
    existing N-V block; user marks it manually.
  - V (改期) is a manual YYYYMMDD marker — preserved across re-runs.
  - Sub-table E (手動設定入院序) — for multi-patient doctor, if every E
    cell is filled, sort patients by E (no re-asking the user).
  - Sub-tables must be re-read fresh from the Sheet immediately before
    writing (E/F/G/H may have been edited since lottery).

Sub-table layout (8 cols, D = placeholder since EMR summary retired 5/10):
  A=姓名 | B=病歷號 | C=EMR | D=EMR摘要(placeholder) | E=手動設定入院序
  F=術前診斷 | G=預計心導管 | H=註記
"""
from __future__ import annotations

from . import sheet_service


ORDERING_HEADERS = [
    "序號", "主治醫師", "病人姓名", "備註(住服)", "備註",
    "病歷號", "術前診斷", "預計心導管", "改期",
]


# ---------------------------- sub-table parser ----------------------------

def parse_subtables_grid(grid: list[list[str]]) -> dict[str, list[dict]]:
    """
    Pure helper: take an A1:H{n} grid and extract doctor sub-tables.
    D column is the retired-summary placeholder — captured into `summary`
    field but never used by ordering.
    """
    tables: dict[str, list[dict]] = {}
    i = 0
    while i < len(grid):
        row = grid[i]
        if row and row[0] and "人）" in row[0]:
            doctor = row[0].split("（")[0].strip()
            i += 2  # skip title + sub-header
            patients = []
            while i < len(grid):
                r = (grid[i] + [""] * 8)[:8]
                if not any(c.strip() for c in r):
                    break
                if "人）" in r[0]:
                    break
                patients.append({
                    "row":       i + 1,
                    "name":      r[0].strip(),
                    "chart_no":  r[1].strip(),
                    "emr":       r[2].strip(),
                    "summary":   r[3].strip(),  # D — placeholder, ignored
                    "manual":    r[4].strip(),  # E — 手動設定入院序
                    "diagnosis": r[5].strip(),  # F
                    "cathlab":   r[6].strip(),  # G
                    "note":      r[7].strip(),  # H
                })
                i += 1
            tables[doctor] = patients
            continue
        i += 1
    return tables


def read_doctor_subtables(date: str) -> dict[str, list[dict]]:
    """Re-read fresh from the Sheet (rule 18: never cache E/F/G/H)."""
    ws = sheet_service.get_worksheet(date)
    if ws is None:
        raise ValueError(f"找不到工作表 {date}")
    grid = sheet_service.read_range(ws, "A1:H500")
    return parse_subtables_grid(grid)


# ---------------------------- E-column manual sort ----------------------------

def sort_by_manual_e(patients: list[dict]) -> list[dict]:
    """
    Rule 18: when EVERY patient in a doctor's table has a numeric E value,
    sort by E (ascending). Otherwise preserve order.
    """
    if len(patients) <= 1:
        return patients
    try:
        keys = [int(p["manual"]) for p in patients]
    except (ValueError, KeyError):
        return patients
    paired = list(zip(keys, patients))
    paired.sort(key=lambda x: x[0])
    return [p for _, p in paired]


# ---------------------------- integrate ----------------------------

def integrate_ordering(date: str) -> dict:
    """
    Rebuild N2:V{n} from current sub-tables + preserve Q/V manual markers.

    Existing N-V block provides ordered (序號, 主治醫師, 姓名, Q, R, 病歷號)
    rows. We re-fetch sub-table E/F/G/H by chart no and rewrite T/U; Q (住服)
    and V (改期) are preserved verbatim from existing rows.

    For multi-patient doctors with fully-filled sub-table E, the **doctor's
    rows** in the N-V block are reordered to match E (other doctors' rows
    are left alone). This implements feedback_subtable_E_must_read_fresh +
    feedback_subtable_H_to_R_ordering.
    """
    ws = sheet_service.get_worksheet(date)
    if ws is None:
        raise ValueError(f"找不到工作表 {date}")

    existing = sheet_service.read_range(ws, "N2:V200")
    tables = read_doctor_subtables(date)

    # chart_no → sub-table fields
    lookup: dict[str, dict] = {}
    # doctor → ordered chart list (after E-sort)
    doctor_chart_order: dict[str, list[str]] = {}
    for doc, pts in tables.items():
        sorted_pts = sort_by_manual_e(pts)
        doctor_chart_order[doc] = [p["chart_no"] for p in sorted_pts if p["chart_no"]]
        for p in pts:
            if p["chart_no"]:
                lookup[p["chart_no"]] = p

    # Materialize existing rows
    rows: list[list[str]] = []
    for r in existing:
        r = (r + [""] * 9)[:9]
        if not r[2].strip():
            break
        rows.append(r)
    if not rows:
        return {"rows": 0}

    # Apply per-doctor E-sort by reordering rows that match each doctor's chart list
    by_doctor_positions: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        doc = r[1].strip()
        by_doctor_positions.setdefault(doc, []).append(i)

    reordered = list(rows)
    for doc, positions in by_doctor_positions.items():
        order = doctor_chart_order.get(doc, [])
        if not order or len(positions) <= 1:
            continue
        # Match each position's chart to E-order; fall back to original order
        pos_rows = [rows[p] for p in positions]
        chart_to_row = {r[5].strip(): r for r in pos_rows}
        new_rows = [chart_to_row[c] for c in order if c in chart_to_row]
        # Append any rows whose chart wasn't in sub-table (shouldn't happen)
        appended_charts = {c for c in order if c in chart_to_row}
        for r in pos_rows:
            if r[5].strip() not in appended_charts:
                new_rows.append(r)
        for slot_idx, p in enumerate(positions):
            reordered[p] = new_rows[slot_idx]

    # Renumber 序號 + patch T/U from sub-tables; preserve Q (住服) + V (改期)
    out: list[list[str]] = []
    for seq, r in enumerate(reordered, start=1):
        chart = r[5].strip()
        info = lookup.get(chart, {})
        out.append([
            str(seq),                                # N 序號
            r[1],                                    # O 主治醫師
            r[2],                                    # P 姓名
            r[3],                                    # Q 備註(住服) — preserve
            r[4],                                    # R 備註 — preserve
            r[5],                                    # S 病歷號
            info.get("diagnosis", r[6]),             # T 術前診斷
            info.get("cathlab",   r[7]),             # U 預計心導管
            r[8],                                    # V 改期 — preserve
        ])

    # Ensure header is correct
    sheet_service.write_range(ws, "N1:V1", [ORDERING_HEADERS], raw=False)
    end_row = 1 + len(out)
    sheet_service.write_range(ws, f"N2:V{end_row}", out, raw=False)
    return {"rows": len(out), "range": f"N2:V{end_row}"}
