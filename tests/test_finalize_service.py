"""Tests for finalize_service — 定案 readiness checklist.

Mocks sheet_service + format_check_service so nothing hits Google.
"""
from __future__ import annotations

from app.services import finalize_service as fs
from app.services import format_check_service as fcs


class FakeWS:
    id = 7


def _patch_get_ws(monkeypatch, ws=FakeWS()):
    monkeypatch.setattr(fs.sheet_service, "get_worksheet", lambda d: ws)


def _patch_format(monkeypatch, issues=None, structure=None, error=None):
    def fake_check(date):
        if error:
            return {"error": error, "issues": [], "structure": {"main_end": 1, "subs": []}}
        return {
            "issues": issues or [],
            "structure": structure or {"main_end": 1, "subs": []},
            "main_header": fcs.EXPECTED_MAIN_HEADER,
            "order_header": fcs.EXPECTED_ORDER_HEADER,
        }
    monkeypatch.setattr(fs.format_check_service, "check", fake_check)


def _stub_read(responses: dict):
    """Build a read_range stub that returns per-range canned values."""
    def read(ws, a1):
        if a1 in responses:
            return responses[a1]
        return []
    return read


# --------------------------- check_ready() ---------------------------

def test_missing_worksheet(monkeypatch):
    monkeypatch.setattr(fs.sheet_service, "get_worksheet", lambda d: None)
    r = fs.check_ready("20260420")
    assert r["ready"] is False
    assert "error" in r


def test_format_error_propagates(monkeypatch):
    _patch_get_ws(monkeypatch)
    _patch_format(monkeypatch, error="fake format error")
    r = fs.check_ready("20260420")
    assert r["ready"] is False
    assert r["error"] == "fake format error"


def test_all_green(monkeypatch):
    _patch_get_ws(monkeypatch)
    _patch_format(monkeypatch, structure={
        "main_end": 3,
        "subs": [{"doctor": "李文煌", "declared": 2, "title_row": 6,
                  "subheader_row": 7, "first_patient_row": 8,
                  "last_patient_row": 9, "actual_count": 2, "orphan": False}],
    })
    # A2:L3 = 2 patients, all fields present
    # F8:G9 = all filled
    # N2:V200 = 2 ordering rows, V=改期 empty
    ordering_empty_v = ["1", "李文煌", "王", "", "", "123", "Dx", "C", ""]
    monkeypatch.setattr(fs.sheet_service, "read_range", _stub_read({
        "A2:L3": [
            ["2026/04/20", "", "CV", "李文煌", "I25", "王", "男", "65", "111", "A", "", ""],
            ["2026/04/20", "", "CV", "李文煌", "I25", "林", "女", "70", "222", "B", "", ""],
        ],
        "F8:G9": [["CAD", "LHC"], ["CAD", "LHC"]],
        "N2:V200": [ordering_empty_v, ordering_empty_v],
    }))
    r = fs.check_ready("20260420")
    assert r["ready"] is True
    by_id = {c["id"]: c for c in r["checks"]}
    assert by_id["format"]["ok"] is True
    assert by_id["main_data"]["ok"] is True
    assert by_id["sub_fg"]["ok"] is True
    assert by_id["ordering"]["ok"] is True
    assert by_id["reschedule"]["ok"] is True


def test_format_issue_blocks_readiness(monkeypatch):
    _patch_get_ws(monkeypatch)
    _patch_format(monkeypatch,
                  issues=[{"type": "main_header_missing"}],
                  structure={"main_end": 1, "subs": []})
    monkeypatch.setattr(fs.sheet_service, "read_range", _stub_read({}))
    r = fs.check_ready("20260420")
    assert r["ready"] is False
    fmt = [c for c in r["checks"] if c["id"] == "format"][0]
    assert fmt["ok"] is False
    assert "1" in fmt["detail"]


def test_main_data_empty_fails(monkeypatch):
    _patch_get_ws(monkeypatch)
    _patch_format(monkeypatch, structure={"main_end": 1, "subs": []})
    monkeypatch.setattr(fs.sheet_service, "read_range", _stub_read({}))
    r = fs.check_ready("20260420")
    main = [c for c in r["checks"] if c["id"] == "main_data"][0]
    assert main["ok"] is False
    assert "空" in main["detail"]


def test_main_data_missing_fields(monkeypatch):
    _patch_get_ws(monkeypatch)
    _patch_format(monkeypatch, structure={"main_end": 3, "subs": []})
    monkeypatch.setattr(fs.sheet_service, "read_range", _stub_read({
        "A2:L3": [
            ["", "", "", "", "", "王", "", "", "111", "", "", ""],  # no doctor
            ["", "", "", "李", "", "", "", "", "", "", "", ""],       # no name, no chart
        ],
        "N2:V200": [],
    }))
    r = fs.check_ready("20260420")
    main = [c for c in r["checks"] if c["id"] == "main_data"][0]
    assert main["ok"] is False
    assert "第 2 列" in main["detail"]
    assert "第 3 列" in main["detail"]


def test_sub_fg_missing(monkeypatch):
    _patch_get_ws(monkeypatch)
    _patch_format(monkeypatch, structure={
        "main_end": 2,
        "subs": [{"doctor": "柯呈諭", "declared": 2, "title_row": 5,
                  "subheader_row": 6, "first_patient_row": 7,
                  "last_patient_row": 8, "actual_count": 2, "orphan": False}],
    })
    monkeypatch.setattr(fs.sheet_service, "read_range", _stub_read({
        "A2:L2": [["2026/04/20", "", "", "柯", "", "A", "", "", "1", "", "", ""]],
        "F7:G8": [["", "LHC"], ["CAD", ""]],  # both rows missing something
        "N2:V200": [],
    }))
    r = fs.check_ready("20260420")
    fg = [c for c in r["checks"] if c["id"] == "sub_fg"][0]
    assert fg["ok"] is False
    assert "柯呈諭" in fg["detail"]
    assert "第 7 列" in fg["detail"] and "第 8 列" in fg["detail"]


def test_sub_fg_skips_orphan(monkeypatch):
    """Orphan sub-tables (no title) have no patient rows to check — skip."""
    _patch_get_ws(monkeypatch)
    _patch_format(monkeypatch, structure={
        "main_end": 2,
        "subs": [{"doctor": None, "declared": None, "title_row": None,
                  "subheader_row": 5, "first_patient_row": None,
                  "last_patient_row": None, "actual_count": 0, "orphan": True}],
    })
    monkeypatch.setattr(fs.sheet_service, "read_range", _stub_read({
        "A2:L2": [["2026/04/20", "", "", "柯", "", "A", "", "", "1", "", "", ""]],
        "N2:V200": [],
    }))
    r = fs.check_ready("20260420")
    fg = [c for c in r["checks"] if c["id"] == "sub_fg"][0]
    assert fg["ok"] is True  # no patients to check


def test_ordering_count_mismatch(monkeypatch):
    _patch_get_ws(monkeypatch)
    _patch_format(monkeypatch, structure={"main_end": 4, "subs": []})
    monkeypatch.setattr(fs.sheet_service, "read_range", _stub_read({
        "A2:L4": [
            ["", "", "", "D", "", "N", "", "", "1", "", "", ""],
            ["", "", "", "D", "", "N", "", "", "2", "", "", ""],
            ["", "", "", "D", "", "N", "", "", "3", "", "", ""],
        ],
        "N2:V200": [
            ["1", "D", "N", "", "", "1", "Dx", "C", "", ""],
        ],
    }))
    r = fs.check_ready("20260420")
    ord_c = [c for c in r["checks"] if c["id"] == "ordering"][0]
    assert ord_c["ok"] is False
    assert "1" in ord_c["detail"] and "3" in ord_c["detail"]


def test_ordering_missing(monkeypatch):
    _patch_get_ws(monkeypatch)
    _patch_format(monkeypatch, structure={"main_end": 2, "subs": []})
    monkeypatch.setattr(fs.sheet_service, "read_range", _stub_read({
        "A2:L2": [["", "", "", "D", "", "N", "", "", "1", "", "", ""]],
        "N2:V200": [],
    }))
    r = fs.check_ready("20260420")
    ord_c = [c for c in r["checks"] if c["id"] == "ordering"][0]
    assert ord_c["ok"] is False
    assert "未寫入" in ord_c["detail"]


def test_reschedule_bad_format(monkeypatch):
    _patch_get_ws(monkeypatch)
    _patch_format(monkeypatch, structure={"main_end": 2, "subs": []})
    # 改期 is index 8 in EXPECTED_ORDER_HEADER (the 9th col, V)
    monkeypatch.setattr(fs.sheet_service, "read_range", _stub_read({
        "A2:L2": [["", "", "", "D", "", "N", "", "", "1", "", "", ""]],
        "N2:V200": [
            ["1", "D", "N", "", "", "1", "Dx", "C", "2026-04-21"],  # bad: has hyphens
        ],
    }))
    r = fs.check_ready("20260420")
    rs = [c for c in r["checks"] if c["id"] == "reschedule"][0]
    assert rs["ok"] is False
    assert "2026-04-21" in rs["detail"]


def test_reschedule_valid_yyyymmdd(monkeypatch):
    _patch_get_ws(monkeypatch)
    _patch_format(monkeypatch, structure={"main_end": 2, "subs": []})
    monkeypatch.setattr(fs.sheet_service, "read_range", _stub_read({
        "A2:L2": [["", "", "", "D", "", "N", "", "", "1", "", "", ""]],
        "N2:V200": [
            ["1", "D", "N", "", "", "1", "Dx", "C", "20260421"],  # good
        ],
    }))
    r = fs.check_ready("20260420")
    rs = [c for c in r["checks"] if c["id"] == "reschedule"][0]
    assert rs["ok"] is True


def test_reschedule_empty_is_ok(monkeypatch):
    _patch_get_ws(monkeypatch)
    _patch_format(monkeypatch, structure={"main_end": 2, "subs": []})
    monkeypatch.setattr(fs.sheet_service, "read_range", _stub_read({
        "A2:L2": [["", "", "", "D", "", "N", "", "", "1", "", "", ""]],
        "N2:V200": [
            ["1", "D", "N", "", "", "1", "Dx", "C", ""],  # empty V (改期)
        ],
    }))
    r = fs.check_ready("20260420")
    rs = [c for c in r["checks"] if c["id"] == "reschedule"][0]
    assert rs["ok"] is True
