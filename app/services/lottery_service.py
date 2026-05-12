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
