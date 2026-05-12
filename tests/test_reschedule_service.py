"""Pure-logic tests for reschedule_service."""
from __future__ import annotations

import pytest

from app.services import reschedule_service as rs


# ---------------- parse_target_date ----------------

def test_parse_target_yyyymmdd():
    assert rs.parse_target_date("20260420") == "20260420"


def test_parse_target_slash_form():
    assert rs.parse_target_date("2026/04/20") == "20260420"


def test_parse_target_dash_form():
    assert rs.parse_target_date("2026-04-20") == "20260420"


def test_parse_target_strips_whitespace():
    assert rs.parse_target_date("  20260420 ") == "20260420"


def test_parse_target_invalid_raises():
    with pytest.raises(ValueError):
        rs.parse_target_date("not-a-date")
    with pytest.raises(ValueError):
        rs.parse_target_date("2026-13-99")  # date arithmetic not checked, but len fails for…
    with pytest.raises(ValueError):
        rs.parse_target_date("")


# ---------------- plan_v_flag (mocked) ----------------

class _FakeWS:
    pass


def _stub(returns):
    """Return a fake `read_range` that maps a1 → values."""
    def f(_ws, a1):
        return returns.get(a1, [])
    return f


def test_plan_v_flag_locates_main_and_ordering_rows(monkeypatch):
    ws = _FakeWS()
    main = [
        ["2026/04/20", "", "CV", "李文煌", "", "王", "", "", "11111111", "", "", ""],
        ["2026/04/20", "", "CV", "陳儒逸", "", "林", "", "", "22222222", "", "", ""],
    ]
    ordering = [
        ["1", "李文煌", "王", "", "", "11111111", "Dx", "C", ""],
        ["2", "陳儒逸", "林", "", "", "22222222", "Dx", "C", ""],
    ]
    monkeypatch.setattr(rs.sheet_service, "get_worksheet", lambda d: ws)
    monkeypatch.setattr(rs.sheet_service, "read_range",
                        _stub({"A2:L200": main, "N2:V200": ordering}))

    p = rs.plan_v_flag("20260420", {"11111111": "20260425", "22222222": "2026/04/26"})
    assert p["missing"] == []
    patches = {x["chart"]: x for x in p["patches"]}
    assert patches["11111111"]["target"] == "20260425"
    assert patches["11111111"]["main_row"] == 2
    assert patches["11111111"]["ordering_row"] == 2
    assert patches["22222222"]["target"] == "20260426"
    assert patches["22222222"]["main_row"] == 3
    assert patches["22222222"]["ordering_row"] == 3


def test_plan_v_flag_missing_chart_goes_to_missing(monkeypatch):
    ws = _FakeWS()
    main = [
        ["2026/04/20", "", "CV", "李", "", "王", "", "", "11111111", "", "", ""],
    ]
    monkeypatch.setattr(rs.sheet_service, "get_worksheet", lambda d: ws)
    monkeypatch.setattr(rs.sheet_service, "read_range",
                        _stub({"A2:L200": main, "N2:V200": []}))

    p = rs.plan_v_flag("20260420", {"99999999": "20260425"})
    assert p["missing"] == ["99999999"]
    assert p["patches"] == []


def test_plan_v_flag_ordering_missing_doesnt_block(monkeypatch):
    """Main row exists but ordering is empty (Step 4 not yet run)."""
    ws = _FakeWS()
    main = [
        ["2026/04/20", "", "CV", "李", "", "王", "", "", "11111111", "", "", ""],
    ]
    monkeypatch.setattr(rs.sheet_service, "get_worksheet", lambda d: ws)
    monkeypatch.setattr(rs.sheet_service, "read_range",
                        _stub({"A2:L200": main, "N2:V200": []}))

    p = rs.plan_v_flag("20260420", {"11111111": "20260425"})
    assert len(p["patches"]) == 1
    assert p["patches"][0]["ordering_row"] is None


def test_plan_v_flag_no_sheet_raises(monkeypatch):
    monkeypatch.setattr(rs.sheet_service, "get_worksheet", lambda d: None)
    with pytest.raises(ValueError, match="找不到工作表"):
        rs.plan_v_flag("20260420", {})


# ---------------- apply_v_flag ----------------

def test_apply_v_flag_writes_v_cell(monkeypatch):
    ws = _FakeWS()
    writes: list[tuple[str, list[list[str]]]] = []
    main = [["2026/04/20", "", "CV", "李", "", "王", "", "", "11111111", "", "", ""]]
    ordering = [["1", "李", "王", "", "", "11111111", "Dx", "C", ""]]
    monkeypatch.setattr(rs.sheet_service, "get_worksheet", lambda d: ws)
    monkeypatch.setattr(rs.sheet_service, "read_range",
                        _stub({"A2:L200": main, "N2:V200": ordering}))
    monkeypatch.setattr(rs.sheet_service, "write_range",
                        lambda _ws, rng, body, raw=False: writes.append((rng, body)))

    result = rs.apply_v_flag("20260420", {"11111111": "20260425"})
    assert len(result["written"]) == 1
    assert result["skipped"] == []
    assert ("V2:V2", [["20260425"]]) in writes


def test_apply_v_flag_no_ordering_row_skips(monkeypatch):
    ws = _FakeWS()
    writes: list = []
    main = [["2026/04/20", "", "CV", "李", "", "王", "", "", "11111111", "", "", ""]]
    monkeypatch.setattr(rs.sheet_service, "get_worksheet", lambda d: ws)
    monkeypatch.setattr(rs.sheet_service, "read_range",
                        _stub({"A2:L200": main, "N2:V200": []}))
    monkeypatch.setattr(rs.sheet_service, "write_range",
                        lambda _ws, rng, body, raw=False: writes.append((rng, body)))

    result = rs.apply_v_flag("20260420", {"11111111": "20260425"})
    assert result["written"] == []
    assert len(result["skipped"]) == 1
    assert "no ordering row" in result["skipped"][0]["reason"]
    assert writes == []


# ---------------- plan_full_move ----------------

def test_plan_full_move_groups_by_target(monkeypatch):
    ws = _FakeWS()
    main = [
        ["2026/04/20", "", "CV", "詹世鴻", "", "王", "", "", "11111111", "", "", ""],
        ["2026/04/20", "", "CV", "陳儒逸", "", "林", "", "", "22222222", "", "", ""],
    ]
    monkeypatch.setattr(rs.sheet_service, "get_worksheet", lambda d: ws)
    monkeypatch.setattr(rs.sheet_service, "read_range",
                        _stub({"A2:L200": main, "N2:V200": []}))

    p = rs.plan_full_move("20260420", {
        "11111111": "20260425",
        "22222222": "20260425",  # both to same target
    })
    assert sorted(p["move_rows_by_target"].keys()) == ["20260425"]
    assert len(p["move_rows_by_target"]["20260425"]) == 2
    del_charts = sorted(d["chart"] for d in p["del_list"])
    assert del_charts == ["11111111", "22222222"]


def test_plan_full_move_computes_source_cath_date(monkeypatch):
    """2026/04/20 is Monday → 詹世鴻 cath = Tue 2026/04/21."""
    ws = _FakeWS()
    main = [
        ["2026/04/20", "", "CV", "詹世鴻", "", "王", "", "", "11111111", "", "", ""],
    ]
    monkeypatch.setattr(rs.sheet_service, "get_worksheet", lambda d: ws)
    monkeypatch.setattr(rs.sheet_service, "read_range",
                        _stub({"A2:L200": main, "N2:V200": []}))

    p = rs.plan_full_move("20260420", {"11111111": "20260427"})
    assert p["del_list"][0]["source_cath_date"] == "2026/04/21"
    assert p["del_list"][0]["doctor"] == "詹世鴻"
    assert p["del_list"][0]["target_admit_date"] == "20260427"


# ---------------- append_rows_to_target ----------------

def test_append_rows_writes_after_last_filled(monkeypatch):
    ws = _FakeWS()
    writes: list = []
    monkeypatch.setattr(rs.sheet_service, "get_worksheet", lambda d: ws)
    monkeypatch.setattr(rs.sheet_service, "read_range",
                        _stub({"A2:L500": [
                            ["x"], [""], ["", "", "", "y"],  # rows 2, 3, 4 — last filled = 4
                        ]}))
    monkeypatch.setattr(rs.sheet_service, "write_range",
                        lambda _ws, rng, body, raw=False: writes.append((rng, body)))

    new_rows = [
        ["2026/04/25", "", "CV", "李", "", "王", "", "", "11111111", "", "", ""],
    ]
    result = rs.append_rows_to_target("20260425", new_rows)
    assert result["appended"] == 1
    assert result["range"] == "A5:L5"
    assert writes[0][0] == "A5:L5"


def test_append_empty_rows_noop(monkeypatch):
    ws = _FakeWS()
    monkeypatch.setattr(rs.sheet_service, "get_worksheet", lambda d: ws)
    monkeypatch.setattr(rs.sheet_service, "read_range",
                        _stub({"A2:L500": []}))
    monkeypatch.setattr(rs.sheet_service, "write_range",
                        lambda *a, **k: pytest.fail("should not write"))

    result = rs.append_rows_to_target("20260425", [])
    assert result["appended"] == 0


def test_append_no_target_sheet_raises(monkeypatch):
    monkeypatch.setattr(rs.sheet_service, "get_worksheet", lambda d: None)
    with pytest.raises(ValueError, match="目標工作表"):
        rs.append_rows_to_target("20260425", [["x"]])
