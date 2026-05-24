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


# ---------------- rule 16: 詹世鴻 Friday exception ----------------

def _stub_friday_env(monkeypatch, tickets, subtables):
    """Stub out the I/O surfaces so lottery_with_pins runs against fixed data."""
    from app.services import ordering_service

    monkeypatch.setattr(ls, "read_lottery_tickets", lambda wd: dict(tickets))
    monkeypatch.setattr(ordering_service, "read_doctor_subtables",
                        lambda d: {doc: list(pts) for doc, pts in subtables.items()})
    monkeypatch.setattr(ordering_service, "sort_by_manual_e", lambda lst: lst)

    class _WS:
        def update_cell(self, *a, **kw): pass

    ws = _WS()
    monkeypatch.setattr(ls.sheet_service, "get_worksheet", lambda d: ws)
    monkeypatch.setattr(ls.sheet_service, "read_range", lambda *a, **kw: [])
    monkeypatch.setattr(ls.sheet_service, "write_range", lambda *a, **kw: None)
    monkeypatch.setattr(ls.sheet_service, "clear_range", lambda *a, **kw: None)
    monkeypatch.setattr(ls.sheet_service, "ensure_chart_text_format", lambda ws: None)


def test_zhan_friday_dropped_to_group2(monkeypatch):
    """週五: 詹世鴻 in lottery sheet → forced into Group 2 (after 時段組)."""
    tickets = {"詹世鴻": 1, "李柏增": 1}
    subs = {
        "詹世鴻": [{"name": "p1", "chart_no": "C1"}],
        "李柏增": [{"name": "p2", "chart_no": "C2"}],
    }
    _stub_friday_env(monkeypatch, tickets, subs)
    result = ls.lottery_with_pins("20260522", weekday="週五", seed=0)
    order = result["doctor_order"]
    assert order.index("李柏增") < order.index("詹世鴻"), \
        f"詹世鴻 must come after 李柏增 on 週五, got {order}"
    # tickets reported back should NOT include 詹世鴻 (already dropped)
    assert "詹世鴻" not in result["ticket_doctors"]
    assert "李柏增" in result["ticket_doctors"]


def test_zhan_thursday_stays_in_group1(monkeypatch):
    """週四: 詹世鴻 stays in 時段組 — rule 16 is Friday-only."""
    tickets = {"詹世鴻": 1}
    subs = {
        "詹世鴻": [{"name": "p1", "chart_no": "C1"}],
        "非時段醫師": [{"name": "p2", "chart_no": "C2"}],
    }
    _stub_friday_env(monkeypatch, tickets, subs)
    result = ls.lottery_with_pins("20260521", weekday="週四", seed=0)
    order = result["doctor_order"]
    assert order.index("詹世鴻") < order.index("非時段醫師"), \
        f"詹世鴻 should be Group 1 on 週四, got {order}"
    assert "詹世鴻" in result["ticket_doctors"]


def test_friday_drop_constant_is_a_collection():
    """Sanity: FRIDAY_DROP_DOCTORS is iterable and contains 詹世鴻."""
    assert "詹世鴻" in ls.FRIDAY_DROP_DOCTORS


# ---------------- weekday normalization (5/26 root cause) ----------------

def test_normalize_weekday_idempotent():
    assert ls._normalize_weekday_label("週三") == "週三"


def test_normalize_weekday_strips_whitespace():
    assert ls._normalize_weekday_label("週三 ") == "週三"
    assert ls._normalize_weekday_label(" 週三") == "週三"
    assert ls._normalize_weekday_label("週三\t") == "週三"
    assert ls._normalize_weekday_label("週三　") == "週三"  # fullwidth space


def test_normalize_weekday_strips_punctuation():
    assert ls._normalize_weekday_label("週三：") == "週三"
    assert ls._normalize_weekday_label("週三、") == "週三"
    assert ls._normalize_weekday_label("週三,") == "週三"


def test_normalize_weekday_folds_xingqi_to_zhou():
    """User's 5/26 sheet uses 『星期三』 but JS sends 『週三』 — these must match."""
    assert ls._normalize_weekday_label("星期三") == "週三"
    assert ls._normalize_weekday_label("星期 三") == "週三"
    assert ls._normalize_weekday_label("星期日") == "週日"


def test_lottery_carries_subtable_note_to_R(monkeypatch):
    """子表格 H 註記 → 首次抽籤寫入 N-V R 欄 (field bug 2026-05-21 #2)."""
    from app.services import ordering_service

    subs = {
        "Z": [{"name": "甲", "chart_no": "111", "diagnosis": "CAD",
               "cathlab": "PCI", "note": "不排導管", "manual": ""}],
    }
    monkeypatch.setattr(ls, "read_lottery_tickets", lambda wd: {})
    monkeypatch.setattr(ordering_service, "read_doctor_subtables",
                        lambda d: {doc: list(pts) for doc, pts in subs.items()})

    writes: list = []

    class _WS:
        def update_cell(self, *a, **kw): pass

    monkeypatch.setattr(ls.sheet_service, "get_worksheet", lambda d: _WS())
    monkeypatch.setattr(ls.sheet_service, "read_range", lambda *a, **kw: [])
    monkeypatch.setattr(ls.sheet_service, "write_range",
                        lambda _ws, rng, body, raw=False: writes.append((rng, body)))
    monkeypatch.setattr(ls.sheet_service, "clear_range", lambda *a, **kw: None)
    monkeypatch.setattr(ls.sheet_service, "ensure_chart_text_format", lambda ws: None)

    ls.lottery_with_pins("20260524", weekday="", seed=0)
    body = next(w for w in writes if w[0].startswith("N2:V"))[1]
    assert body[0][4] == "不排導管"   # R ← 子表格 H 註記
    assert body[0][3] == ""           # Q (備註住服) stays empty


def test_lottery_with_pins_groups_never_interleave(monkeypatch):
    """lottery_with_pins must run 時段組 RR to completion BEFORE 非時段組
    starts — even when both have multiple patients.

    Field bug 2026-05-24 (5/25 sheet): the inner RR loop iterated all
    doctors in one queue, so a 時段 doctor's 2nd patient appeared AFTER a
    非時段 doctor's 1st patient. Per feedback_lottery_roundrobin.md and the
    reference `two_group_round_robin`, the groups must NEVER interleave.
    """
    from app.services import ordering_service

    tickets = {"S1": 1, "S2": 1}  # 時段組 (in lottery sheet)
    subs = {
        "S1": [{"name": "s1a", "chart_no": "C1A"},
               {"name": "s1b", "chart_no": "C1B"}],
        "S2": [{"name": "s2a", "chart_no": "C2A"},
               {"name": "s2b", "chart_no": "C2B"}],
        "N1": [{"name": "n1a", "chart_no": "N1A"},
               {"name": "n1b", "chart_no": "N1B"}],  # 非時段組 (no ticket)
    }
    _stub_friday_env(monkeypatch, tickets, subs)
    writes: list = []
    monkeypatch.setattr(ls.sheet_service, "write_range",
                        lambda _ws, rng, body, raw=False: writes.append((rng, body)))

    ls.lottery_with_pins("20260525", weekday="週日", seed=0)
    body = next(w for w in writes if w[0].startswith("N2:V"))[1]
    names = [r[2] for r in body]  # P col = 病人姓名

    last_sched = max(i for i, n in enumerate(names) if not n.startswith("n"))
    first_non  = min(i for i, n in enumerate(names) if n.startswith("n"))
    assert last_sched < first_non, (
        f"非時段組 must come ENTIRELY after 時段組. Got order: {names}"
    )
    # And both 時段 doctors should each have both patients in the 時段 block
    sched_block = names[:last_sched + 1]
    assert sched_block.count("s1a") == 1 and sched_block.count("s1b") == 1
    assert sched_block.count("s2a") == 1 and sched_block.count("s2b") == 1


def test_read_lottery_tickets_matches_xingqi_row(monkeypatch):
    """The 5/26 actual failure mode: sheet cell says 『星期三』, JS sends 『週三』.
    Before this fix tickets came back empty → 劉嚴文 randomly排到第一位.
    """
    fake_grid = [
        ["星期三", "詹世鴻*2", "", "林佳凌", "陳儒逸",
         "張獻元*2", "黃睦翔", "廖瑀"],
    ]

    class _WS:
        pass

    monkeypatch.setattr(ls.sheet_service, "get_worksheet", lambda name: _WS())
    monkeypatch.setattr(ls.sheet_service, "read_range", lambda ws, rng: fake_grid)
    tickets = ls.read_lottery_tickets("週三")
    assert tickets == {
        "詹世鴻": 2, "林佳凌": 1, "陳儒逸": 1,
        "張獻元": 2, "黃睦翔": 1, "廖瑀": 1,
    }
