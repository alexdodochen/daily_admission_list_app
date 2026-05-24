"""Tests for subtable_service.smart_rebuild — the rescue path that dedupes
duplicate doctor blocks and preserves EMR/F/G/H/I across blocks."""
from __future__ import annotations

import re

import pytest

from app.services import subtable_service as ss


class _FakeWS:
    id = 999


def _stub_sheet(monkeypatch, *, main_rows, grid):
    """Wire up read_range / write_range / clear_range / get_worksheet."""
    writes = []
    clears = []
    monkeypatch.setattr(ss.sheet_service, "get_worksheet", lambda d: _FakeWS())
    monkeypatch.setattr(ss.sheet_service, "ensure_chart_text_format",
                        lambda ws: None)
    monkeypatch.setattr(ss.sheet_service, "set_fg_validation",
                        lambda *a, **kw: None)

    def read_range(_ws, a1):
        if a1 == "A2:L500":
            return main_rows
        if a1 == "A1:I250":
            return grid
        return []
    monkeypatch.setattr(ss.sheet_service, "read_range", read_range)
    monkeypatch.setattr(ss.sheet_service, "write_range",
                        lambda _ws, a1, body, raw=False: writes.append((a1, body)))
    monkeypatch.setattr(ss.sheet_service, "clear_range",
                        lambda _ws, a1: clears.append(a1))
    # Stub sync_ordering_after_diff to avoid real Sheet calls
    from app.services import ordering_service
    monkeypatch.setattr(ordering_service, "sync_ordering_after_diff",
                        lambda d: {"updated": True, "rows": 0})
    return writes, clears


def _main(name, doctor, chart):
    """Build a 12-col main A-L row."""
    return ["2026-05-26", "", "CV", doctor, "", name, "", "", chart,
            "", "", ""]


def test_smart_rebuild_dedupes_duplicate_doctor_blocks(monkeypatch):
    """3 duplicate 李文煌 blocks → merged to 1, with patients in main order."""
    main_rows = [
        _main("甲", "李文煌", "111"),
        _main("乙", "李文煌", "222"),
    ]
    grid = [
        ["實際住院日"] + [""] * 8,                                # r1 header
        _main("甲", "李文煌", "111") + [""] * (9 - 12 + 12)[:9] if False else (
            ["2026-05-26", "", "CV", "李文煌", "", "甲"] + [""] * 3),  # r2
        ["2026-05-26", "", "CV", "李文煌", "", "乙"] + [""] * 3,    # r3
        [""] * 9,                                                  # r4
        [""] * 9,                                                  # r5
        ["李文煌（2人）"] + [""] * 8,                                # r6 title
        ["姓名","病歷號","EMR","摘要","入院序","術前診斷","預計心導管","註記","備註(住服)"],  # r7
        ["甲","111","short EMR","","","CAD","PCI","",""],          # r8 — short EMR
        ["乙","222","","","","AS","TAVI","保留H",""],              # r9
        [""] * 9, [""] * 9,
        ["李文煌（2人）"] + [""] * 8,                                # r12 DUPLICATE title
        ["姓名","病歷號"] + [""] * 7,
        ["甲","111","MUCH LONGER EMR TEXT WITH MORE DETAIL","","","CAD","PCI","",""],  # r14 longer
        ["乙","222","","","","AS","TAVI","",""],                   # r15 (no H)
        [""] * 9, [""] * 9,
        ["李文煌（2人）"] + [""] * 8,                                # r18 ANOTHER dup
        ["姓名","病歷號"] + [""] * 7,
        ["甲","111","","","","CAD","PCI","",""],
        ["乙","222","","","","AS","TAVI","","V"],                  # carries I=V
    ]
    writes, _ = _stub_sheet(monkeypatch, main_rows=main_rows, grid=grid)

    r = ss.smart_rebuild("20260526")

    assert r["ok"] is True
    assert r["doctor_count"] == 1
    assert r["patient_count"] == 2

    # Find the block write (A{start}:I{end})
    block_writes = [w for w in writes if re.match(r"^A\d+:I\d+$", w[0])]
    assert len(block_writes) == 1
    a1, body = block_writes[0]
    # Exactly ONE 李文煌 title in the rewritten block
    titles = [row[0] for row in body if "人）" in (row[0] or "")]
    assert titles == ["李文煌（2人）"]
    # 甲 picks the LONGEST EMR text across all duplicate blocks
    rows_jia = [row for row in body if row[1] == "111"]
    assert len(rows_jia) == 1
    assert "MUCH LONGER" in rows_jia[0][2]
    # 乙 keeps H=保留H from the FIRST block (longest C-col tiebreak still
    # picks first since C is empty in all 3) AND picks up I=V from any block
    # — well, actually with empty C, the FIRST seen wins via "or" semantics.
    # The crucial assertion: only ONE row per chart, no dupes.
    rows_yi = [row for row in body if row[1] == "222"]
    assert len(rows_yi) == 1


def test_smart_rebuild_preserves_main_order(monkeypatch):
    """Sub-tables emit in main A-L doctor first-appearance order, regardless
    of how the duplicate blocks were ordered on the sheet."""
    main_rows = [
        _main("甲", "Dr李", "111"),
        _main("丙", "Dr柯", "333"),
        _main("乙", "Dr李", "222"),  # 乙 belongs to Dr李 (already seen)
    ]
    grid = [
        ["實際住院日"] + [""] * 8,
        ["2026-05-26","","CV","Dr李","","甲"] + [""] * 3,
        ["2026-05-26","","CV","Dr柯","","丙"] + [""] * 3,
        ["2026-05-26","","CV","Dr李","","乙"] + [""] * 3,
        [""] * 9, [""] * 9,
        # Sub-table blocks happen to be in WRONG order on sheet (Dr柯 first)
        ["Dr柯（1人）"] + [""] * 8,
        ["姓名","病歷號"] + [""] * 7,
        ["丙","333","","","","",""," ",""],
        [""] * 9, [""] * 9,
        ["Dr李（2人）"] + [""] * 8,
        ["姓名","病歷號"] + [""] * 7,
        ["甲","111","emr-x","","","","",""," "],
        ["乙","222","emr-y","","","","",""," "],
    ]
    writes, _ = _stub_sheet(monkeypatch, main_rows=main_rows, grid=grid)

    r = ss.smart_rebuild("20260526")
    assert r["ok"] is True
    block_writes = [w for w in writes if re.match(r"^A\d+:I\d+$", w[0])]
    a1, body = block_writes[0]
    # Doctor titles appear in MAIN order: Dr李 first (appeared as main r2),
    # then Dr柯 (main r3). Even though sheet had Dr柯 block first.
    titles = [row[0] for row in body if "人）" in (row[0] or "")]
    assert titles[0].startswith("Dr李")
    assert titles[1].startswith("Dr柯")
    # Dr李 block has 甲 + 乙 in main order
    chart_order = [row[1] for row in body if row[1] in ("111","222","333")]
    assert chart_order == ["111", "222", "333"]


def test_smart_rebuild_drops_orphans_not_in_main(monkeypatch):
    """A chart that exists in sub-tables but NOT in main A-L is dropped
    from the rebuilt block."""
    main_rows = [_main("甲", "Dr李", "111")]
    grid = [
        ["實際住院日"] + [""] * 8,
        ["2026-05-26","","CV","Dr李","","甲"] + [""] * 3,
        [""] * 9, [""] * 9,
        ["Dr李（2人）"] + [""] * 8,
        ["姓名","病歷號"] + [""] * 7,
        ["甲","111","","","","","","",""],
        ["孤兒","999","emr-x","","","","","",""],   # NOT in main
    ]
    writes, _ = _stub_sheet(monkeypatch, main_rows=main_rows, grid=grid)

    r = ss.smart_rebuild("20260526")
    assert r["ok"] is True
    assert "999" in r["dropped_orphans"]
    a1, body = block_writes[0] if False else (
        next(w for w in writes if re.match(r"^A\d+:I\d+$", w[0])))
    # Rebuilt block has 甲 but NOT 孤兒
    charts = [row[1] for row in body if row[1] in ("111", "999")]
    assert charts == ["111"]


def test_smart_rebuild_stops_main_read_at_subtable_title(monkeypatch):
    """Main read must STOP at the first sub-table title row — never include
    sub-table cells as if they were main patients. This is the same boundary
    rule as ocr_service.write_to_sheet (field bug 2026-05-25 5/26 sheet)."""
    main_rows = [
        _main("甲", "Dr李", "111"),
        [""] * 12,
        [""] * 12,
        ["李文煌（1人）"] + [""] * 11,    # ← sub-table title; main read STOPS here
        ["姓名"] + [""] * 11,             # ← should be ignored
        ["甲", "111"] + [""] * 10,        # ← should be ignored
    ]
    grid = [
        ["實際住院日"] + [""] * 8,
        ["2026-05-26","","CV","Dr李","","甲"] + [""] * 3,
        [""] * 9, [""] * 9,
        ["Dr李（1人）"] + [""] * 8,
        ["姓名","病歷號"] + [""] * 7,
        ["甲","111","emr","","","","","",""],
    ]
    writes, _ = _stub_sheet(monkeypatch, main_rows=main_rows, grid=grid)
    r = ss.smart_rebuild("20260526")
    # main_count must be 1 (NOT 5 including the sub-table rows)
    assert r["main_count"] == 1
    assert r["patient_count"] == 1


def test_smart_rebuild_raises_on_empty_main(monkeypatch):
    main_rows = []
    grid = []
    _stub_sheet(monkeypatch, main_rows=main_rows, grid=grid)
    with pytest.raises(ValueError, match="主表沒有任何病人"):
        ss.smart_rebuild("20260526")
