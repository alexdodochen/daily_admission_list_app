"""Tests for format_check_service.

Pure-function tests (parse_structure, check_issues) don't need mocks.
check()/fix() are exercised with mocked sheet_service.
"""
from __future__ import annotations

import pytest

from app.services import format_check_service as fcs


# --------------------------- parse_structure ---------------------------

def _col_a(values: list[str]) -> list[str]:
    """Pad to 500 like _read_col_a does."""
    out = list(values)
    while len(out) < 500:
        out.append("")
    return out


def test_parse_empty_sheet():
    s = fcs.parse_structure(_col_a([""]))
    assert s["main_end"] == 1
    assert s["subs"] == []


def test_parse_main_only():
    # row1 header, rows 2-4 main data
    col = _col_a(["實際住院日", "2026/04/20", "2026/04/20", "2026/04/20"])
    s = fcs.parse_structure(col)
    assert s["main_end"] == 4
    assert s["subs"] == []


def test_parse_main_plus_one_subtable():
    # row1 header, rows 2-3 main, row 4-5 gap, row 6 title, row 7 sub-header, rows 8-9 patients
    col = _col_a([
        "實際住院日",
        "2026/04/20", "2026/04/20",
        "", "",
        "柯呈諭（2人）",
        "姓名",
        "王小明", "林大美",
    ])
    s = fcs.parse_structure(col)
    assert s["main_end"] == 3
    assert len(s["subs"]) == 1
    sub = s["subs"][0]
    assert sub["doctor"] == "柯呈諭"
    assert sub["declared"] == 2
    assert sub["title_row"] == 6
    assert sub["subheader_row"] == 7
    assert sub["first_patient_row"] == 8
    assert sub["last_patient_row"] == 9
    assert sub["actual_count"] == 2
    assert sub["orphan"] is False


def test_parse_count_mismatch():
    col = _col_a([
        "實際住院日", "2026/04/20",
        "", "",
        "李文煌（3人）",
        "姓名",
        "甲", "乙",   # only 2 patients but declared 3
    ])
    s = fcs.parse_structure(col)
    assert s["subs"][0]["declared"] == 3
    assert s["subs"][0]["actual_count"] == 2


def test_parse_orphan_subtable():
    # 姓名 sub-header without a title row before it
    col = _col_a([
        "實際住院日", "2026/04/20",
        "", "",
        "姓名",       # orphan — no title
        "甲",
    ])
    s = fcs.parse_structure(col)
    assert len(s["subs"]) == 1
    assert s["subs"][0]["orphan"] is True
    assert s["subs"][0]["subheader_row"] == 5


def test_parse_two_subtables():
    col = _col_a([
        "實際住院日", "2026/04/20",
        "", "",
        "李文煌（1人）", "姓名", "甲",
        "", "",
        "柯呈諭（2人）", "姓名", "乙", "丙",
    ])
    s = fcs.parse_structure(col)
    assert len(s["subs"]) == 2
    assert s["subs"][0]["doctor"] == "李文煌"
    assert s["subs"][1]["doctor"] == "柯呈諭"
    assert s["subs"][1]["actual_count"] == 2


# --------------------------- check_issues ---------------------------

GOOD_MAIN = fcs.EXPECTED_MAIN_HEADER
GOOD_ORDER = fcs.EXPECTED_ORDER_HEADER


def test_issues_none_when_clean():
    structure = {
        "main_end": 3,
        "subs": [{
            "doctor": "李文煌", "declared": 1, "title_row": 6,
            "subheader_row": 7, "first_patient_row": 8,
            "last_patient_row": 8, "actual_count": 1, "orphan": False,
        }],
    }
    issues = fcs.check_issues(structure, GOOD_MAIN, GOOD_ORDER,
                              sub_headers={7: fcs.EXPECTED_SUB_HEADER})
    assert issues == []


def test_issues_bad_main_header():
    structure = {"main_end": 1, "subs": []}
    issues = fcs.check_issues(structure, ["wrong"] + [""] * 11, GOOD_ORDER)
    kinds = {i["type"] for i in issues}
    assert "main_header_missing" in kinds


def test_issues_bad_order_header():
    structure = {"main_end": 1, "subs": []}
    issues = fcs.check_issues(structure, GOOD_MAIN, ["bad"] + [""] * 9)
    assert any(i["type"] == "order_header_wrong" for i in issues)


def test_issues_count_mismatch():
    structure = {
        "main_end": 3,
        "subs": [{
            "doctor": "李文煌", "declared": 3, "title_row": 6,
            "subheader_row": 7, "first_patient_row": 8,
            "last_patient_row": 8, "actual_count": 1, "orphan": False,
        }],
    }
    issues = fcs.check_issues(structure, GOOD_MAIN, GOOD_ORDER)
    mm = [i for i in issues if i["type"] == "subtable_count_mismatch"]
    assert len(mm) == 1
    assert mm[0]["declared"] == 3
    assert mm[0]["actual"] == 1
    assert mm[0]["fixable"] is True


def test_issues_gap_too_small():
    # main_end=5, first sub title at row 6 → gap=0 (need 2)
    structure = {
        "main_end": 5,
        "subs": [{
            "doctor": "李文煌", "declared": 1, "title_row": 6,
            "subheader_row": 7, "first_patient_row": 8,
            "last_patient_row": 8, "actual_count": 1, "orphan": False,
        }],
    }
    issues = fcs.check_issues(structure, GOOD_MAIN, GOOD_ORDER)
    gaps = [i for i in issues if i["type"] == "gap_too_small"]
    assert len(gaps) == 1
    assert gaps[0]["gap"] == 0
    assert gaps[0]["need_insert"] == 2


def test_issues_gap_ok_with_exactly_two():
    structure = {
        "main_end": 5,
        "subs": [{
            "doctor": "李文煌", "declared": 1, "title_row": 8,  # gap = 8-5-1 = 2
            "subheader_row": 9, "first_patient_row": 10,
            "last_patient_row": 10, "actual_count": 1, "orphan": False,
        }],
    }
    issues = fcs.check_issues(structure, GOOD_MAIN, GOOD_ORDER)
    assert [i for i in issues if i["type"] == "gap_too_small"] == []


def test_issues_sub_header_wrong_detected():
    """Legacy SUB_HEADER labels (summary / 入院序) → sub_header_wrong issue."""
    structure = {
        "main_end": 3,
        "subs": [{
            "doctor": "李文煌", "declared": 1, "title_row": 6,
            "subheader_row": 7, "first_patient_row": 8,
            "last_patient_row": 8, "actual_count": 1, "orphan": False,
        }],
    }
    legacy = ["姓名", "病歷號", "EMR", "summary", "入院序",
              "術前診斷", "預計心導管", "註記"]
    issues = fcs.check_issues(structure, GOOD_MAIN, GOOD_ORDER,
                              sub_headers={7: legacy})
    sub_issues = [i for i in issues if i["type"] == "sub_header_wrong"]
    assert len(sub_issues) == 1
    assert sub_issues[0]["row"] == 7
    assert sub_issues[0]["doctor"] == "李文煌"
    assert sub_issues[0]["fixable"] is True


def test_issues_orphan_not_fixable():
    structure = {
        "main_end": 3,
        "subs": [{
            "doctor": None, "declared": None, "title_row": None,
            "subheader_row": 6, "first_patient_row": None,
            "last_patient_row": None, "actual_count": 0, "orphan": True,
        }],
    }
    issues = fcs.check_issues(structure, GOOD_MAIN, GOOD_ORDER)
    orph = [i for i in issues if i["type"] == "subtable_missing_title"]
    assert len(orph) == 1
    assert orph[0]["fixable"] is False


# --------------------------- check() with mocked sheet ---------------------------

class FakeWS:
    id = 42


def _fake_read_range(col_a_values, main_header=None, order_header=None,
                     sub_header=None):
    """Build a read_range stub that returns values based on A1 notation."""
    main_header = main_header if main_header is not None else GOOD_MAIN
    order_header = order_header if order_header is not None else GOOD_ORDER
    sub_header = sub_header if sub_header is not None else fcs.EXPECTED_SUB_HEADER

    def read_range(ws, a1):
        if a1 == "A1:A500":
            return [[v] for v in col_a_values]
        if a1 == "A1:L1":
            return [main_header]
        if a1 == "N1:V1":
            return [order_header]
        # SUB_HEADER row read: "A{n}:H{n}"
        import re as _re
        m = _re.match(r"^A(\d+):H\1$", a1)
        if m:
            return [sub_header]
        return []
    return read_range


def test_check_returns_error_when_sheet_missing(monkeypatch):
    monkeypatch.setattr(fcs.sheet_service, "get_worksheet", lambda d: None)
    r = fcs.check("20260420")
    assert "error" in r
    assert r["issues"] == []


def test_check_clean_sheet(monkeypatch):
    monkeypatch.setattr(fcs.sheet_service, "get_worksheet", lambda d: FakeWS())
    col_a = [
        "實際住院日", "2026/04/20", "2026/04/20",
        "", "",
        "李文煌（1人）", "姓名", "甲",
    ]
    monkeypatch.setattr(fcs.sheet_service, "read_range",
                        _fake_read_range(col_a))
    r = fcs.check("20260420")
    assert r["issues"] == []
    assert r["structure"]["main_end"] == 3
    assert len(r["structure"]["subs"]) == 1


def test_check_reports_count_mismatch(monkeypatch):
    monkeypatch.setattr(fcs.sheet_service, "get_worksheet", lambda d: FakeWS())
    col_a = [
        "實際住院日", "2026/04/20",
        "", "",
        "李文煌（5人）", "姓名", "甲",   # declared 5, actual 1
    ]
    monkeypatch.setattr(fcs.sheet_service, "read_range",
                        _fake_read_range(col_a))
    r = fcs.check("20260420")
    kinds = [i["type"] for i in r["issues"]]
    assert "subtable_count_mismatch" in kinds


# --------------------------- fix() — count + header fixes ---------------------------

def test_fix_applies_count_rewrite(monkeypatch):
    monkeypatch.setattr(fcs.sheet_service, "get_worksheet", lambda d: FakeWS())

    writes = []
    monkeypatch.setattr(fcs.sheet_service, "write_range",
                        lambda ws, a1, body, raw=False: writes.append((a1, body)))

    class FakeSh:
        def batch_update(self, req):
            writes.append(("batch", req))
    monkeypatch.setattr(fcs.sheet_service, "get_spreadsheet", lambda: FakeSh())

    # After first check → count mismatch. Second check (final) → same col_a
    # (the rewrite of the title cell doesn't actually happen in this stub).
    # That means remaining_issues will still show the mismatch — which is fine;
    # we're asserting that fix() called write_range with the new title.
    col_a = [
        "實際住院日", "2026/04/20",
        "", "",
        "李文煌（5人）", "姓名", "甲",
    ]
    monkeypatch.setattr(fcs.sheet_service, "read_range",
                        _fake_read_range(col_a))

    result = fcs.fix("20260420", types=["subtable_count_mismatch"])
    # Should have written the corrected title to A5
    title_writes = [w for w in writes if w[0] == "A5"]
    assert len(title_writes) == 1
    assert title_writes[0][1] == [["李文煌（1人）"]]
    # applied should include the count_mismatch
    applied_kinds = [a["type"] for a in result["applied"]]
    assert "subtable_count_mismatch" in applied_kinds


def test_fix_rewrites_main_header(monkeypatch):
    monkeypatch.setattr(fcs.sheet_service, "get_worksheet", lambda d: FakeWS())
    writes = []
    monkeypatch.setattr(fcs.sheet_service, "write_range",
                        lambda ws, a1, body, raw=False: writes.append((a1, body)))
    class FakeSh:
        def batch_update(self, req): pass
    monkeypatch.setattr(fcs.sheet_service, "get_spreadsheet", lambda: FakeSh())

    col_a = ["BAD HEADER"]
    monkeypatch.setattr(
        fcs.sheet_service, "read_range",
        _fake_read_range(col_a, main_header=["bad"] + [""] * 11),
    )
    result = fcs.fix("20260420", types=["main_header_missing"])
    header_writes = [w for w in writes if w[0] == "A1:L1"]
    assert len(header_writes) == 1
    assert header_writes[0][1] == [fcs.EXPECTED_MAIN_HEADER]
    assert any(a["type"] == "main_header_missing" for a in result["applied"])


def test_fix_respects_types_filter(monkeypatch):
    """If types=['main_header_missing'], count mismatch should NOT be touched."""
    monkeypatch.setattr(fcs.sheet_service, "get_worksheet", lambda d: FakeWS())
    writes = []
    monkeypatch.setattr(fcs.sheet_service, "write_range",
                        lambda ws, a1, body, raw=False: writes.append((a1, body)))
    class FakeSh:
        def batch_update(self, req): pass
    monkeypatch.setattr(fcs.sheet_service, "get_spreadsheet", lambda: FakeSh())

    col_a = [
        "實際住院日", "2026/04/20",
        "", "",
        "李文煌（5人）", "姓名", "甲",
    ]
    monkeypatch.setattr(
        fcs.sheet_service, "read_range",
        _fake_read_range(col_a, main_header=["bad"] + [""] * 11),
    )
    result = fcs.fix("20260420", types=["main_header_missing"])
    # Main header rewritten …
    assert any(w[0] == "A1:L1" for w in writes)
    # … but no title rewrite
    assert not any(w[0] == "A5" for w in writes)
    applied_kinds = [a["type"] for a in result["applied"]]
    assert "main_header_missing" in applied_kinds
    assert "subtable_count_mismatch" not in applied_kinds


# --------------------------- ensure_fg_validation ---------------------------

def test_ensure_fg_validation_no_sheet(monkeypatch):
    monkeypatch.setattr(fcs.sheet_service, "get_worksheet", lambda d: None)
    assert fcs.ensure_fg_validation("20260420") == {"applied": False, "rows": None}


def test_ensure_fg_validation_no_subtables(monkeypatch):
    monkeypatch.setattr(fcs.sheet_service, "get_worksheet", lambda d: FakeWS())
    monkeypatch.setattr(fcs.sheet_service, "read_range",
                        _fake_read_range(["實際住院日", "2026/04/20"]))
    called = []
    monkeypatch.setattr(fcs.sheet_service, "set_fg_validation",
                        lambda *a, **k: called.append(a))
    assert fcs.ensure_fg_validation("20260420") == {"applied": False, "rows": None}
    assert called == []  # nothing to attach a dropdown to


def test_ensure_fg_validation_applies_over_subtable(monkeypatch):
    col_a = [
        "實際住院日",
        "2026/04/20", "2026/04/20",
        "", "",
        "柯呈諭（2人）",
        "姓名",
        "王小明", "林大美",
    ]
    monkeypatch.setattr(fcs.sheet_service, "get_worksheet", lambda d: FakeWS())
    monkeypatch.setattr(fcs.sheet_service, "read_range", _fake_read_range(col_a))
    from app.services import emr_service
    monkeypatch.setattr(emr_service, "get_fg_options",
                        lambda: (["STEMI", "Stable"], ["LHC", "RHC"]))
    captured = {}

    def fake_set(ws, start, end, f_opts, g_opts):
        captured.update(ws=ws, start=start, end=end, f=f_opts, g=g_opts)

    monkeypatch.setattr(fcs.sheet_service, "set_fg_validation", fake_set)
    r = fcs.ensure_fg_validation("20260420")
    # subheader_row=7 → start 8; last_patient_row=9 → end 9
    assert r == {"applied": True, "rows": (8, 9)}
    assert captured["start"] == 8
    assert captured["end"] == 9 + 100  # +100 buffer for later-added rows
    assert captured["f"] == ["STEMI", "Stable"]
    assert captured["g"] == ["LHC", "RHC"]
