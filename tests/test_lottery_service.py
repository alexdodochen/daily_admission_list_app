"""Pure-logic tests for lottery_service (draw + round_robin + weighted_shuffle)."""
from __future__ import annotations

import random

from app.services import lottery_service as ls


def _pts(pairs):
    return [{"doctor": d, "name": n, "chart_no": f"C{n}"} for d, n in pairs]


# ---------------- parse_ticket_cell ----------------

def test_parse_ticket_cell_plain():
    assert ls.parse_ticket_cell("許志新") == ("許志新", 1)


def test_parse_ticket_cell_starred():
    assert ls.parse_ticket_cell("李柏增*2") == ("李柏增", 2)


def test_parse_ticket_cell_empty():
    assert ls.parse_ticket_cell("") == ("", 0)
    assert ls.parse_ticket_cell("   ") == ("", 0)


# ---------------- weighted_doctor_shuffle ----------------

def test_weighted_shuffle_dedupes():
    tickets = {"A": 2, "B": 1, "C": 1}
    out = ls.weighted_doctor_shuffle(tickets, rng=random.Random(42))
    assert sorted(out) == ["A", "B", "C"]
    assert len(out) == 3


def test_weighted_shuffle_starred_doctor_lands_earlier_on_average():
    """Over many trials, the *3 doctor should be first more often than *1."""
    tickets = {"A": 3, "B": 1}
    first_counts = {"A": 0, "B": 0}
    rng = random.Random(0)
    for _ in range(2000):
        out = ls.weighted_doctor_shuffle(tickets, rng=rng)
        first_counts[out[0]] += 1
    assert first_counts["A"] > first_counts["B"] * 2  # ~3x bias


def test_weighted_shuffle_empty():
    assert ls.weighted_doctor_shuffle({}) == []


# ---------------- draw ----------------

def test_draw_respects_ticket_count():
    patients = _pts([
        ("A", "a1"), ("A", "a2"), ("A", "a3"),
        ("B", "b1"), ("B", "b2"),
    ])
    tickets = {"A": 2, "B": 1}
    drawn = ls.draw(patients, tickets, seed=42)
    assert len(drawn["A"]) == 2
    assert len(drawn["B"]) == 1


def test_draw_deterministic_with_seed():
    patients = _pts([("A", "a1"), ("A", "a2"), ("A", "a3")])
    d1 = ls.draw(patients, {"A": 2}, seed=42)
    d2 = ls.draw(patients, {"A": 2}, seed=42)
    assert [p["name"] for p in d1["A"]] == [p["name"] for p in d2["A"]]


def test_draw_non_schedule_doctors_go_last():
    patients = _pts([("A", "a1"), ("Z", "z1"), ("Z", "z2")])
    drawn = ls.draw(patients, {"A": 1}, seed=1)
    keys = list(drawn.keys())
    assert keys.index("A") < keys.index("Z")
    assert len(drawn["Z"]) == 2  # all non-schedule kept


# ---------------- round_robin (two independent groups) ----------------

def test_round_robin_within_in_schedule_group():
    """A1 → B1 → C1 → A2 → B2 → A3 — three in-schedule doctors only."""
    drawn = {
        "A": _pts([("A", "a1"), ("A", "a2"), ("A", "a3")]),
        "B": _pts([("B", "b1"), ("B", "b2")]),
        "C": _pts([("C", "c1")]),
    }
    tickets = {"A": 3, "B": 2, "C": 1}
    out = ls.round_robin(drawn, tickets, seed=0)
    names = [p["name"] for p in out]
    # Doctor order is weighted-shuffled (seeded) but every patient must appear
    assert sorted(names) == sorted(["a1", "a2", "a3", "b1", "b2", "c1"])
    # All A's preserve internal order across the RR
    a_positions = [n for n in names if n.startswith("a")]
    assert a_positions == ["a1", "a2", "a3"]


def test_round_robin_groups_never_interleave():
    """Non-schedule (Z) appears only after every in-schedule patient (A, B)."""
    drawn = {
        "A": _pts([("A", "a1"), ("A", "a2")]),
        "B": _pts([("B", "b1"), ("B", "b2")]),
        "Z": _pts([("Z", "z1"), ("Z", "z2")]),
    }
    tickets = {"A": 2, "B": 2}  # Z non-schedule
    out = ls.round_robin(drawn, tickets, seed=0)
    names = [p["name"] for p in out]
    last_in_sched = max(i for i, n in enumerate(names) if not n.startswith("z"))
    first_z = min(i for i, n in enumerate(names) if n.startswith("z"))
    assert last_in_sched < first_z


def test_round_robin_only_non_schedule():
    drawn = {"Z": _pts([("Z", "z1"), ("Z", "z2")])}
    out = ls.round_robin(drawn, {}, seed=0)
    assert [p["name"] for p in out] == ["z1", "z2"]


def test_round_robin_empty():
    assert ls.round_robin({}, {}) == []


def test_round_robin_skips_doctors_with_no_patients():
    """Tickets mention D but D has zero patients → D doesn't show in output."""
    drawn = {"A": _pts([("A", "a1")])}
    tickets = {"A": 1, "D": 2}
    out = ls.round_robin(drawn, tickets, seed=0)
    assert [p["name"] for p in out] == ["a1"]
