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

import re

from . import sheet_service


# OCR uncertainty marks ("張三?") leak from Step 1 into sub-table 姓名. Strip the
# trailing mark so 入院序結果 / lottery / cathlab all show the clean name (same
# rule as cathlab_service.read_patients). Field bug 2026-05-21 #2.
_NAME_UNCERTAIN_RE = re.compile(r"[?？�⁇‽]+\s*$")


def clean_name(name: str) -> str:
    """Strip a trailing OCR uncertainty mark from a patient name."""
    return _NAME_UNCERTAIN_RE.sub("", (name or "").strip()).strip()


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
                    "name":      clean_name(r[0]),
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
        if not r[2].strip() and not r[5].strip():
            break
        rows.append(r)

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

    # Append sub-table patients that never made it into the N-V block.
    # integrate previously ONLY patched existing rows, so a patient added to a
    # sub-table after the last lottery silently vanished from 入院序結果.
    # (Field bug 2026-05-21 #4/#5.) Append them in doctor × within-doctor order.
    existing_charts = {(r[5] or "").strip()
                       for r in reordered if (r[5] or "").strip()}
    appended: list[dict] = []
    for doc, charts in doctor_chart_order.items():
        for ch in charts:
            if ch in existing_charts:
                continue
            info = lookup.get(ch, {})
            reordered.append([
                "", doc, info.get("name", ""), "", "",
                ch, info.get("diagnosis", ""), info.get("cathlab", ""), "",
            ])
            existing_charts.add(ch)
            appended.append({"chart_no": ch, "doctor": doc,
                             "name": info.get("name", "")})

    if not reordered:
        return {"rows": 0, "appended": []}

    # Renumber 序號 + patch T/U + R from sub-tables; preserve Q (住服) + V (改期)
    # R (備註) <- sub-table H (註記) when H non-empty; else preserve existing R.
    # Mirrors daily-admission-list-public mapping H → R (feedback_subtable_H_to_R_ordering).
    out: list[list[str]] = []
    for seq, r in enumerate(reordered, start=1):
        chart = r[5].strip()
        info = lookup.get(chart, {})
        sub_note = (info.get("note") or "").strip()
        # P 姓名 ← sub-table (EMR-corrected + OCR-"?"-stripped) when available;
        # the existing N-V name can be stale (field bug 2026-05-21 #2).
        sub_name = (info.get("name") or "").strip()
        out.append([
            str(seq),                                # N 序號
            r[1],                                    # O 主治醫師
            sub_name if sub_name else r[2],          # P 姓名 ← 子表格
            r[3],                                    # Q 備註(住服) — preserve
            sub_note if sub_note else r[4],          # R 備註 ← 子表格 H 註記
            r[5],                                    # S 病歷號
            info.get("diagnosis", r[6]),             # T 術前診斷
            info.get("cathlab",   r[7]),             # U 預計心導管
            r[8],                                    # V 改期 — preserve
        ])

    # Ensure header is correct
    sheet_service.write_range(ws, "N1:V1", [ORDERING_HEADERS], raw=False)
    end_row = 1 + len(out)
    sheet_service.write_range(ws, f"N2:V{end_row}", out, raw=False)
    return {"rows": len(out), "range": f"N2:V{end_row}", "appended": appended}


# ---------------------------- sync after OCR diff ----------------------------

def sync_ordering_after_diff(date: str) -> dict:
    """
    Reconcile the N-V block with current sub-tables after a Step 1 OCR diff
    has added/removed/moved patients.

    Behaviour (least-surprise rebuild — never re-randomises existing order):
      * For every chart already in N-V whose sub-table row is still present:
        keep the row, but refresh O (主治醫師) + T (術前診斷) + U (預計心導管)
        from the (possibly new) sub-table. Q / R / V manual markers preserved.
      * Charts no longer in any sub-table → row dropped.
      * Charts present in sub-tables but never in N-V → appended at the end,
        in main-table doctor-first-appearance order × within-doctor sub-table
        order, with empty Q / R / V.
      * 序號 (N col) renumbered 1..n at the end.

    Returns {updated, rows, range, added, removed, doctor_changed} so the UI
    can report what happened.
    """
    ws = sheet_service.get_worksheet(date)
    if ws is None:
        return {"updated": False, "reason": "sheet missing"}

    tables = read_doctor_subtables(date)
    # chart_no → {doctor, name, diagnosis, cathlab, note}
    chart_info: dict[str, dict] = {}
    # ordered list of (doctor, chart_no) tuples for stable append order
    fresh_order: list[tuple[str, str]] = []
    for doc, pts in tables.items():
        if not doc:
            continue
        for p in pts:
            ch = (p.get("chart_no") or "").strip()
            if not ch:
                continue
            chart_info[ch] = {
                "doctor":    doc,
                "name":      p.get("name", ""),
                "diagnosis": p.get("diagnosis", ""),
                "cathlab":   p.get("cathlab", ""),
                "note":      p.get("note", ""),
            }
            fresh_order.append((doc, ch))

    existing = sheet_service.read_range(ws, "N2:V200")
    kept: list[list[str]] = []
    removed: list[str] = []
    seen_charts: set[str] = set()
    doctor_changed: list[dict] = []
    for r in existing:
        r = (r + [""] * 9)[:9]
        if not (r[2] or "").strip() and not (r[5] or "").strip():
            break
        chart = (r[5] or "").strip()
        if not chart:
            continue
        info = chart_info.get(chart)
        if info is None:
            removed.append(chart)
            continue
        seen_charts.add(chart)
        old_doc = (r[1] or "").strip()
        new_doc = info["doctor"]
        if old_doc and new_doc and old_doc != new_doc:
            doctor_changed.append({"chart_no": chart, "old": old_doc, "new": new_doc})
        sub_note = (info.get("note") or "").strip()
        kept.append([
            "",                # N — renumbered below
            new_doc,           # O
            info["name"] or (r[2] or "").strip(),
            r[3],              # Q preserve
            sub_note if sub_note else r[4],  # R ← 子表格 H 註記; fallback preserve
            chart,             # S
            info["diagnosis"], # T refresh
            info["cathlab"],   # U refresh
            r[8],              # V preserve
        ])

    added: list[dict] = []
    for doc, chart in fresh_order:
        if chart in seen_charts:
            continue
        info = chart_info[chart]
        kept.append([
            "", doc, info["name"], "", info.get("note", ""), chart,
            info["diagnosis"], info["cathlab"], "",
        ])
        added.append({"chart_no": chart, "doctor": doc, "name": info["name"]})

    # Renumber 序號
    for i, row in enumerate(kept, start=1):
        row[0] = str(i)

    sheet_service.write_range(ws, "N1:V1", [ORDERING_HEADERS], raw=False)
    if kept:
        end_row = 1 + len(kept)
        sheet_service.write_range(ws, f"N2:V{end_row}", kept, raw=False)
    else:
        end_row = 1

    # Clear any leftover rows below the new end (existing block may have been longer)
    old_end = 1 + sum(1 for r in existing
                      if any((c or "").strip() for c in (r + [""] * 9)[:9]))
    if old_end > end_row:
        sheet_service.clear_range(ws, f"N{end_row + 1}:V{old_end}")

    return {
        "updated":        True,
        "rows":           len(kept),
        "range":          f"N2:V{end_row}",
        "added":          added,
        "removed":        removed,
        "doctor_changed": doctor_changed,
    }
