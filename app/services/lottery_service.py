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

The 詹世鴻 Friday exception (rule 16) is handled upstream: callers
should drop 詹世鴻 from `tickets` on Friday so he falls into Group 2.
"""
from __future__ import annotations

import random
import re
from typing import Optional

from . import sheet_service


# ---------------------------- main / lottery readers ----------------------------

def read_main_patients(date: str) -> list[dict]:
    ws = sheet_service.get_worksheet(date)
    if ws is None:
        raise ValueError(f"找不到工作表 {date}，請先完成 Step 1")
    rows = sheet_service.read_range(ws, "A2:L200")
    out = []
    for i, r in enumerate(rows):
        r = (r + [""] * 12)[:12]
        if not r[5].strip():
            break
        out.append({
            "row": i + 2,
            "doctor": r[3].strip(),
            "name": r[5].strip(),
            "chart_no": r[8].strip(),
        })
    return out


def parse_ticket_cell(raw: str) -> tuple[str, int]:
    """`'李柏增*2'` → `('李柏增', 2)`; `'許志新'` → `('許志新', 1)`; empty → `('', 0)`."""
    s = (raw or "").strip()
    if not s:
        return ("", 0)
    m = re.match(r"^(.+?)\*(\d+)$", s)
    if m:
        return (m.group(1).strip(), int(m.group(2)))
    return (s, 1)


def read_lottery_tickets(schedule_day: str) -> dict[str, int]:
    """
    Read 主治醫師抽籤表. Layout: first column = weekday label
    (週一/週二/...), subsequent columns = doctor names with `*N` ticket suffix.
    Returns {doctor: ticket_count}.
    """
    ws = sheet_service.get_worksheet("主治醫師抽籤表")
    if ws is None:
        return {}
    rows = sheet_service.read_range(ws, "A1:Z50")
    tickets: dict[str, int] = {}
    for r in rows:
        if not r:
            continue
        if r[0].strip() == schedule_day:
            for cell in r[1:]:
                name, count = parse_ticket_cell(cell)
                if name and count > 0:
                    tickets[name] = tickets.get(name, 0) + count
            break
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


# ---------------------------- draw + RR (two groups) ----------------------------

def draw(patients: list[dict],
         tickets: dict[str, int],
         seed: Optional[int] = None) -> dict[str, list[dict]]:
    """
    Pick patients per doctor up to their ticket count (in-schedule) or all
    of them (non-schedule). Returns {doctor: [patient, ...]} with in-schedule
    doctors first (insertion order = `tickets` order), non-schedule last.

    Patient order within each doctor is randomized (used for the per-doctor
    internal order before RR).
    """
    rng = random.Random(seed)
    by_doctor: dict[str, list[dict]] = {}
    for p in patients:
        by_doctor.setdefault(p["doctor"], []).append(p)

    result: dict[str, list[dict]] = {}
    for doc in tickets:
        pool = list(by_doctor.get(doc, []))
        rng.shuffle(pool)
        result[doc] = pool[: tickets.get(doc, len(pool))]
    for doc, pool in by_doctor.items():
        if doc and doc not in tickets:
            shuffled = list(pool)
            rng.shuffle(shuffled)
            result[doc] = shuffled
    return result


def _rr_within_group(draws: dict[str, list[dict]], order: list[str]) -> list[dict]:
    queues = {d: list(draws.get(d, [])) for d in order}
    out: list[dict] = []
    while any(queues[d] for d in order):
        for d in order:
            if queues[d]:
                out.append({**queues[d].pop(0), "doctor": d})
    return out


def round_robin(draws: dict[str, list[dict]],
                tickets: dict[str, int],
                seed: Optional[int] = None) -> list[dict]:
    """
    Two-group RR:
      Group 1 (時段組): doctors in `tickets` AND with patients in `draws`.
                       Doctor order = `weighted_doctor_shuffle(tickets ∩ draws)`.
      Group 2 (非時段組): doctors with patients but not in `tickets`.
                          Doctor order = plain shuffle (no tickets to weight by).
    """
    rng = random.Random(seed)

    # Group 1
    in_sched_tix = {d: c for d, c in tickets.items() if d in draws and draws[d]}
    group1_order = weighted_doctor_shuffle(in_sched_tix, rng=rng)

    # Group 2 (preserve dict iteration order, then shuffle)
    group2_order = [d for d in draws if d and d not in tickets and draws[d]]
    rng.shuffle(group2_order)

    return _rr_within_group(draws, group1_order) + _rr_within_group(draws, group2_order)


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
    queues = {d: list(by_doctor[d]) for d in doctor_order}
    rr_sequence: list[dict] = []
    while any(queues[d] for d in doctor_order):
        for d in doctor_order:
            if queues[d]:
                rr_sequence.append(queues[d].pop(0))

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
    # Read current N-V length BEFORE writing so we can clear any trailing rows
    # if the new lottery is shorter than the previous one (re-running lottery
    # after removing a patient should fully overwrite, not leave a phantom row).
    existing = sheet_service.read_range(ws, "N2:V200")
    old_rows = 0
    for r in existing:
        r = (r + [""] * 9)[:9]
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
            "",                     # Q 備註(住服)
            "",                     # R 備註
            p["chart_no"],
            p["diagnosis"],
            p["cathlab"],
            "",                     # V 改期
        ])
    end_row = 1 + len(body)
    # TEXT format on chart-no col before write so leading zeros survive
    try:
        sheet_service.ensure_chart_text_format(ws)
    except Exception:
        pass
    sheet_service.write_range(ws, "N1:V1", [ordering_service.ORDERING_HEADERS], raw=False)
    sheet_service.write_range(ws, f"N2:V{end_row}", body, raw=False)
    # Clear leftover rows from the previous (longer) N-V block.
    old_end = 1 + old_rows
    if old_end > end_row:
        sheet_service.clear_range(ws, f"N{end_row + 1}:V{old_end}")
    return {
        "rows":             len(body),
        "range":            f"N2:V{end_row}",
        "pinned_patients":  len(pinned_patients),
        "pinned_doctors":   len(doctor_pins),
        "doctor_order":     list(doctor_order),
        "ticket_doctors":   list(tickets.keys()),
        "weekday":          weekday,
        "cleared_trailing": max(0, old_end - end_row),
    }


# ---------------------------- writer ----------------------------

def write_to_sheet(date: str, ordered: list[dict]) -> dict:
    """Write 序號 / 主治醫師 / 病人姓名 / 備註(住服) / 備註 / 病歷號 to N2:S{n+1}.
    Q (備註(住服)) and R (備註) default to empty — user marks them manually.
    """
    ws = sheet_service.get_worksheet(date)
    body = []
    for i, p in enumerate(ordered, start=1):
        body.append([str(i), p["doctor"], p["name"], "", "", p.get("chart_no", "")])
    end_row = 1 + len(body)
    sheet_service.write_range(ws, f"N2:S{end_row}", body, raw=False)
    return {"rows": len(body), "range": f"N2:S{end_row}"}
