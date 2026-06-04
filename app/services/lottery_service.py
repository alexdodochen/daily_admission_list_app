"""
Step 2 — Lottery + Round-Robin.

Two-group round-robin (`feedback_lottery_roundrobin.md`):
  Group 1 — 時段組: doctors that appear in 主治醫師抽籤表 for the schedule day.
  Group 2 — 非時段組: doctors with admitted patients but NOT in the lottery.

Within each group:
  - Doctor draw order is weighted by `*N` ticket count (`weighted_doctor_shuffle`).
  - Patients are round-robined A1 → B1 → C1 → A2 → ... until each doctor empty.

The two groups NEVER mix; Group 2 starts only after Group 1 fully RR'd
(per the user's repeated correction in `feedback_lottery_roundrobin.md`).

The 詹世鴻 Friday exception (rule 16) is enforced inside
`lottery_with_pins` via `FRIDAY_DROP_DOCTORS` — on 週五 his name is
popped from the tickets dict so he falls into Group 2 regardless of
whether the sheet's 週五 row lists him.
"""
from __future__ import annotations

import random
import re
from datetime import datetime
from typing import Optional

from . import sheet_service


# Rule 16 (clarified 2026-05-25): 詹世鴻 is exempt from the 時段 group ONLY
# when his patients are admitted on a Friday — even if he's listed in some
# weekday column of the lottery sheet. User rule:
#   「如果詹在星期五有病人要住院，那他在星期五的入院序算非時段組，
#    但詹的病人在星期四要住院的話當然要算時段組」
# Gate is the ADMISSION DAY's weekday (not the op-day weekday parameter
# passed for column lookup). Pre-fix: gated on weekday == 週五, which dropped
# 詹 on every Thursday admission (op day = Friday) — wrong.
FRIDAY_DROP_DOCTORS: tuple[str, ...] = ("詹世鴻",)


def _admission_is_friday(date: str) -> bool:
    """date is YYYYMMDD (the admission sheet name). True iff that date is a Friday."""
    try:
        return datetime.strptime(date, "%Y%m%d").weekday() == 4
    except Exception:
        return False


# ---------------------------- lottery readers ----------------------------

def parse_ticket_cell(raw: str) -> tuple[str, int]:
    """`'李柏增*2'` → `('李柏增', 2)`; `'許志新'` → `('許志新', 1)`; empty → `('', 0)`."""
    s = (raw or "").strip()
    if not s:
        return ("", 0)
    m = re.match(r"^(.+?)\*(\d+)$", s)
    if m:
        return (m.group(1).strip(), int(m.group(2)))
    return (s, 1)


_WEEKDAY_NORMALIZE_TABLE = str.maketrans("", "", " \t　 ：:、，,")


def _normalize_weekday_label(s: str) -> str:
    """Strip whitespace/fullwidth-space/BOM/punctuation AND fold 星期X → 週X
    so the JS-sent 『週三』 matches a sheet cell 『星期三』.

    Examples that all compare equal:
      『週三』 / 『週三 』 / 『週三:』 / 『 週三』 / 『星期三』 / 『星期 三』
    """
    out = (s or "").replace("﻿", "").translate(_WEEKDAY_NORMALIZE_TABLE).strip()
    # Fold 星期X (sheet style, per user's 2026-05-21 5/26 case) to 週X (JS style).
    if out.startswith("星期"):
        out = "週" + out[2:]
    return out


def read_lottery_tickets(schedule_day: str) -> dict[str, int]:
    """
    Read 主治醫師抽籤表. Layout: first ROW is the weekday header
    (星期一/星期二/星期三/星期四/星期五), and each weekday occupies one COLUMN
    underneath. Doctor names in that column carry an optional `*N` ticket suffix.
    Repeats in the same column accumulate (sheet legend: 「同名重複列 → 按列數累加」).
    Returns {doctor: ticket_count}.

    Weekday matching is whitespace-/punctuation-insensitive and folds
    『星期X』 ↔ 『週X』 so JS-sent 『週三』 matches sheet cell 『星期三』.
    """
    ws = sheet_service.get_worksheet("主治醫師抽籤表")
    if ws is None:
        return {}
    rows = sheet_service.read_range(ws, "A1:Z50")
    if not rows:
        return {}
    target = _normalize_weekday_label(schedule_day)
    header = rows[0]
    col_idx = -1
    for i, cell in enumerate(header):
        if _normalize_weekday_label(cell) == target:
            col_idx = i
            break
    if col_idx < 0:
        return {}
    tickets: dict[str, int] = {}
    for r in rows[1:]:
        if col_idx >= len(r):
            continue
        name, count = parse_ticket_cell(r[col_idx])
        if name and count > 0:
            tickets[name] = tickets.get(name, 0) + count
    return tickets


# ---------------------------- weighted shuffle ----------------------------

def weighted_doctor_shuffle(tickets: dict[str, int], rng: Optional[random.Random] = None) -> list[str]:
    """
    Pool = each doctor × ticket_count, shuffle, dedup keeping first occurrence.
    `*2` doctor lands earlier on average but still occupies one RR slot.
    """
    rng = rng or random.Random()
    pool: list[str] = []
    for name, count in tickets.items():
        if count > 0:
            pool.extend([name] * count)
    rng.shuffle(pool)
    seen: set[str] = set()
    out: list[str] = []
    for n in pool:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


# ---------------------------- pin-aware lottery + N-V writer ----------------------------

def lottery_with_pins(date: str,
                      weekday: str = "",
                      patient_pins: Optional[dict] = None,
                      doctor_pins: Optional[dict] = None,
                      seed: Optional[int] = None) -> dict:
    """
    First-time N-V writer that respects 3 separate pin layers:

      * Sub-table E col (per-doctor): if any of a doctor's patients has a
        numeric E, the doctor's patients sort by E (within-doctor order).
        Empty E preserves the sub-table's natural order.
      * `patient_pins` {chart_no → seq}: forces a specific patient into
        global 序號 = seq, overriding RR. Validates uniqueness + range.
      * `doctor_pins` {doctor → rank}: forces a specific doctor to be the
        rank-th in the round-robin doctor order. Other doctors fill the
        remaining slots in weighted-shuffle order.

    Returns counts so the UI can report "pin N 病人 / M 醫師".
    """
    from . import ordering_service  # local import to avoid cycle

    patient_pins = {k: int(v) for k, v in (patient_pins or {}).items() if v}
    doctor_pins  = {k: int(v) for k, v in (doctor_pins  or {}).items() if v}

    tickets = read_lottery_tickets(weekday) if weekday else {}
    # Rule 16: drop 詹世鴻 from tickets when ADMISSION day is Friday — his
    # Friday admissions count as 非時段. Other days he uses the sheet column
    # as-is. (Pre-fix gated on op-day=週五 which wrongly fired on every
    # Thursday admission. Field bug 2026-05-25 #5/28.)
    if _admission_is_friday(date):
        for _drop in FRIDAY_DROP_DOCTORS:
            tickets.pop(_drop, None)
    # Diagnostic: if user passed a weekday but no tickets were read, the
    # 「主治醫師抽籤表」 worksheet is missing / malformed / has no row for that
    # weekday. Without tickets, ALL doctors fall into 非時段組 → random shuffle.
    # Surface this as a warning so the user can fix the sheet instead of
    # silently getting a wrong order. See feedback_lottery_empty_tickets_warning.
    tickets_warning = ""
    if weekday and not tickets:
        tickets_warning = (
            f"讀不到「主治醫師抽籤表」工作表中【{weekday}】這一列。"
            f"所有醫師都會被當成非時段組（隨機分配）。"
            f"請確認 Sheet 是否有名為「主治醫師抽籤表」的工作表，"
            f"且第 1 列星期文字（如「{weekday}」或「星期{weekday[-1]}」）寫法正確（無多餘空白／符號）。"
        )
    tables = ordering_service.read_doctor_subtables(date)
    if not tables:
        raise ValueError("沒讀到任何子表格，請先跑 Step 2 生成 subtable")

    # --- Build per-doctor patient lists, applying E-sort within doctor ---
    by_doctor: dict[str, list[dict]] = {}
    all_patients: list[dict] = []
    for doctor, pts in tables.items():
        if not doctor:
            continue
        flat = []
        for p in pts:
            flat.append({
                "doctor":    doctor,
                "name":      p.get("name", ""),
                "chart_no":  p.get("chart_no", ""),
                "diagnosis": p.get("diagnosis", ""),
                "cathlab":   p.get("cathlab", ""),
                "note":      (p.get("note")  or "").strip(),
                "house":     (p.get("house") or "").strip(),
                "manual":    (p.get("manual") or "").strip(),
            })
        by_doctor[doctor] = ordering_service.sort_by_manual_e(flat)
        all_patients.extend(by_doctor[doctor])

    total = len(all_patients)
    if total == 0:
        raise ValueError("子表格無病人，無法抽籤")

    chart_index: dict[str, dict] = {p["chart_no"]: p for p in all_patients if p["chart_no"]}

    # --- Validate patient_pins ---
    pin_seqs = list(patient_pins.values())
    if len(set(pin_seqs)) != len(pin_seqs):
        dupes = sorted({s for s in pin_seqs if pin_seqs.count(s) > 1})
        raise ValueError(f"病人 pin 有重複序號：{dupes}")
    if pin_seqs and max(pin_seqs) > total:
        raise ValueError(f"病人 pin 最大序號 {max(pin_seqs)} > 病人總數 {total}")
    pinned_patients: dict[int, dict] = {}
    for chart, seq in patient_pins.items():
        if chart not in chart_index:
            raise ValueError(f"病人 pin 找不到病歷號 {chart}")
        pinned_patients[seq] = chart_index[chart]

    # --- Build doctor RR order (doctor_pins + weighted shuffle) ---
    rng = random.Random(seed)
    doctors_with_patients = [d for d in by_doctor if by_doctor[d]]
    n_doc = len(doctors_with_patients)

    doc_rank_seqs = list(doctor_pins.values())
    if len(set(doc_rank_seqs)) != len(doc_rank_seqs):
        dupes = sorted({s for s in doc_rank_seqs if doc_rank_seqs.count(s) > 1})
        raise ValueError(f"醫師 pin 有重複順位：{dupes}")
    if doc_rank_seqs and max(doc_rank_seqs) > n_doc:
        raise ValueError(f"醫師 pin 順位 {max(doc_rank_seqs)} > 醫師數 {n_doc}")
    for d in doctor_pins:
        if d not in doctors_with_patients:
            raise ValueError(f"醫師 pin '{d}' 找不到對應子表格 / 該醫師無病人")

    doctor_order: list[Optional[str]] = [None] * n_doc
    for d, rank in doctor_pins.items():
        doctor_order[rank - 1] = d
    unpinned_docs = [d for d in doctors_with_patients if d not in doctor_pins]
    # In-schedule unpinned doctors keep their ticket weights; out-of-schedule
    # ones come after (group 2 plain shuffle).
    in_sched = {d: tickets[d] for d in unpinned_docs if d in tickets}
    out_sched = [d for d in unpinned_docs if d not in tickets]
    rng.shuffle(out_sched)
    weighted = weighted_doctor_shuffle(in_sched, rng=rng)
    fill_order = weighted + out_sched
    ui = 0
    for i in range(n_doc):
        if doctor_order[i] is None:
            doctor_order[i] = fill_order[ui]
            ui += 1

    # --- Round-robin patients across doctor_order, then apply patient pins ---
    # HARD RULE (feedback_lottery_roundrobin.md): 非時段組 must come ENTIRELY
    # after 時段組 — never interleave. Run two independent RRs and concat.
    # (Field bug 2026-05-24: lottery on 5/25 mixed 非時段 patients into the
    # middle of 時段 patients because a single RR loop iterated all doctors
    # together.)  See reference impl `two_group_round_robin` in
    # 每日入院名單 Claude/lottery_utils.py.
    group1_docs = [d for d in doctor_order if d and d in tickets]
    group2_docs = [d for d in doctor_order if d and d not in tickets]

    def _rr(group: list[str]) -> list[dict]:
        queues = {d: list(by_doctor[d]) for d in group}
        out: list[dict] = []
        while any(queues[d] for d in group):
            for d in group:
                if queues[d]:
                    out.append(queues[d].pop(0))
        return out

    rr_sequence: list[dict] = _rr(group1_docs) + _rr(group2_docs)

    # Remove pinned patients from the RR sequence — they're assigned to fixed slots
    pinned_charts = {p["chart_no"] for p in pinned_patients.values()}
    remaining = [p for p in rr_sequence if p["chart_no"] not in pinned_charts]

    final_seq: list[dict] = []
    ri = 0
    for seq in range(1, total + 1):
        if seq in pinned_patients:
            final_seq.append(pinned_patients[seq])
        else:
            if ri >= len(remaining):
                raise ValueError(f"序號 {seq} 無病人可填（remaining {len(remaining)} 不足）")
            final_seq.append(remaining[ri])
            ri += 1

    ws = sheet_service.get_worksheet(date)
    # Read current N-U length BEFORE writing so we can clear any trailing rows
    # if the new lottery is shorter than the previous one (re-running lottery
    # after removing a patient should fully overwrite, not leave a phantom row).
    existing = sheet_service.read_range(ws, "N2:U200")
    old_rows = 0
    for r in existing:
        r = (r + [""] * 8)[:8]
        if any((c or "").strip() for c in r):
            old_rows += 1
        else:
            break

    body = []
    for i, p in enumerate(final_seq, start=1):
        body.append([
            str(i),
            p["doctor"],
            p["name"],
            p.get("house", ""),     # Q 備註(住服) ← 子表格 I (2026-05-25 mirror)
            p.get("note", ""),      # R 備註 ← 子表格 H 註記 (field bug 2026-05-21 #2)
            p["chart_no"],
            p["diagnosis"],
            p["cathlab"],
        ])
    end_row = 1 + len(body)
    # TEXT format on chart-no col before write so leading zeros survive
    try:
        sheet_service.ensure_chart_text_format(ws)
    except Exception:
        pass
    sheet_service.write_range(ws, "N1:U1", [ordering_service.ORDERING_HEADERS], raw=False)
    sheet_service.write_range(ws, f"N2:U{end_row}", body, raw=False)
    # Clear leftover rows from the previous (longer) N-U block.
    old_end = 1 + old_rows
    if old_end > end_row:
        sheet_service.clear_range(ws, f"N{end_row + 1}:U{old_end}")
    # Build doctor_groups so the UI can show which doctors landed in 時段組 vs
    # 非時段組. This helps the user spot mis-grouping (e.g. 劉嚴文 wrongly in
    # 時段組 because the wrong weekday was sent).
    doctor_groups = {
        d: ("時段組" if d in tickets else "非時段組")
        for d in doctor_order if d
    }
    return {
        "rows":             len(body),
        "range":            f"N2:U{end_row}",
        "pinned_patients":  len(pinned_patients),
        "pinned_doctors":   len(doctor_pins),
        "doctor_order":     list(doctor_order),
        "doctor_groups":    doctor_groups,
        "ticket_doctors":   list(tickets.keys()),
        "weekday":          weekday,
        "cleared_trailing": max(0, old_end - end_row),
        "warning":          tickets_warning,
    }


