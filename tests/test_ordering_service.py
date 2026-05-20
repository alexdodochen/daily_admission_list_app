"""Pure-logic tests for ordering_service parse + sort + integrate."""
from __future__ import annotations

from app.services import ordering_service as os_


def _pad(cells, width=8):
    return cells + [""] * (width - len(cells))


# ---------------- parse_subtables_grid ----------------

def test_parse_single_doctor_table():
    grid = [
        _pad(["實際住院日"]),
        _pad([]), _pad([]), _pad([]),
        _pad(["柯呈諭（2人）"]),
        _pad(["姓名", "病歷", "EMR", "摘要", "手動", "術前診斷", "預計心導管", "註記"]),
        _pad(["王小明", "12345678", "y", "", "", "CAD", "Left heart cath.", ""]),
        _pad(["李大華", "87654321", "y", "", "", "pAf", "RF ablation", "浩"]),
        _pad([]),
    ]
    tables = os_.parse_subtables_grid(grid)
    assert list(tables.keys()) == ["柯呈諭"]
    pts = tables["柯呈諭"]
    assert len(pts) == 2
    assert pts[0]["name"] == "王小明"
    assert pts[0]["chart_no"] == "12345678"
    assert pts[0]["diagnosis"] == "CAD"
    assert pts[0]["cathlab"] == "Left heart cath."
    assert pts[0]["row"] == 7
    assert pts[1]["note"] == "浩"
    # D-col placeholder captured but unused
    assert "summary" in pts[0]


def test_parse_multi_doctor_tables():
    grid = [
        _pad(["柯呈諭（1人）"]), _pad(["姓名", "病歷"]),
        _pad(["A", "1"]), _pad([]),
        _pad(["陳儒逸（1人）"]), _pad(["姓名", "病歷"]),
        _pad(["B", "2"]), _pad([]),
    ]
    tables = os_.parse_subtables_grid(grid)
    assert set(tables.keys()) == {"柯呈諭", "陳儒逸"}


def test_parse_stops_on_blank_row():
    grid = [
        _pad(["柯呈諭（3人）"]),
        _pad(["姓名", "病歷"]),
        _pad(["A", "1"]),
        _pad([]),
        _pad(["B", "2"]),
    ]
    tables = os_.parse_subtables_grid(grid)
    assert len(tables["柯呈諭"]) == 1


def test_parse_empty_grid():
    assert os_.parse_subtables_grid([]) == {}


def test_parse_grid_without_any_titles():
    grid = [_pad(["實際住院日"]), _pad(["patient data"])]
    assert os_.parse_subtables_grid(grid) == {}


# ---------------- sort_by_manual_e ----------------

def test_sort_by_manual_e_all_filled():
    pts = [
        {"name": "A", "manual": "3", "chart_no": "1"},
        {"name": "B", "manual": "1", "chart_no": "2"},
        {"name": "C", "manual": "2", "chart_no": "3"},
    ]
    sorted_ = os_.sort_by_manual_e(pts)
    assert [p["name"] for p in sorted_] == ["B", "C", "A"]


def test_sort_by_manual_e_partial_fill_preserves_order():
    pts = [
        {"name": "A", "manual": "1", "chart_no": "1"},
        {"name": "B", "manual": "",  "chart_no": "2"},
    ]
    sorted_ = os_.sort_by_manual_e(pts)
    assert [p["name"] for p in sorted_] == ["A", "B"]


def test_sort_by_manual_e_single_patient_unchanged():
    pts = [{"name": "A", "manual": "", "chart_no": "1"}]
    assert os_.sort_by_manual_e(pts) == pts


def test_sort_by_manual_e_empty():
    assert os_.sort_by_manual_e([]) == []


# ---------------- ordering_headers ----------------

def test_ordering_headers_9_cols():
    assert os_.ORDERING_HEADERS == [
        "序號", "主治醫師", "病人姓名", "備註(住服)", "備註",
        "病歷號", "術前診斷", "預計心導管", "改期",
    ]


# ---------------- integrate_ordering (mocked) ----------------

class _FakeWS:
    def __init__(self):
        self.writes: list[tuple[str, list[list[str]]]] = []


def test_integrate_renumbers_and_patches_fg(monkeypatch):
    # Existing N2:V200 — two patients of doc Z, with old T/U + Q/V we must preserve
    existing = [
        ["1", "Z", "王小明", "員工眷屬", "急", "12345678", "old_diag", "old_cath", ""],
        ["2", "Z", "李大華", "",         "",   "87654321", "old_diag", "old_cath", "20260420"],
    ]
    # Fresh sub-table values (T/U should come from these)
    sub_grid = [
        _pad(["Z（2人）"]),
        _pad(["姓名", "病歷", "EMR", "", "", "術前診斷", "預計心導管", "註記"]),
        _pad(["王小明", "12345678", "", "", "", "CAD", "Left heart cath.", ""]),
        _pad(["李大華", "87654321", "", "", "", "pAf", "RF ablation", ""]),
        _pad([]),
    ]
    ws = _FakeWS()
    monkeypatch.setattr(os_.sheet_service, "get_worksheet", lambda d: ws)

    def fake_read_range(_ws, rng):
        return existing if rng.startswith("N") else sub_grid

    def fake_write_range(_ws, rng, body, raw=False):
        ws.writes.append((rng, body))

    monkeypatch.setattr(os_.sheet_service, "read_range", fake_read_range)
    monkeypatch.setattr(os_.sheet_service, "write_range", fake_write_range)

    result = os_.integrate_ordering("20260420")
    assert result["rows"] == 2
    assert result["range"] == "N2:V3"

    # Body write
    body_write = next(w for w in ws.writes if w[0] == "N2:V3")
    body = body_write[1]
    assert body[0][0] == "1"
    assert body[0][3] == "員工眷屬"  # Q preserved
    assert body[0][6] == "CAD"        # T patched from sub-table
    assert body[0][7] == "Left heart cath."
    assert body[0][8] == ""           # V preserved (empty)
    assert body[1][8] == "20260420"   # V preserved (改期 marker)
    assert body[1][6] == "pAf"


def test_integrate_resorts_by_subtable_e(monkeypatch):
    # Doctor Z has 3 patients in existing N-V order P1, P2, P3.
    # Sub-table E says order should be P2, P3, P1.
    existing = [
        ["1", "Z", "P1", "", "", "C1", "", "", ""],
        ["2", "Z", "P2", "", "", "C2", "", "", ""],
        ["3", "Z", "P3", "", "", "C3", "", "", ""],
    ]
    sub_grid = [
        _pad(["Z（3人）"]),
        _pad(["姓名", "病歷", "EMR", "", "", "術前診斷", "預計心導管", "註記"]),
        _pad(["P1", "C1", "", "", "3", "d1", "c1", ""]),
        _pad(["P2", "C2", "", "", "1", "d2", "c2", ""]),
        _pad(["P3", "C3", "", "", "2", "d3", "c3", ""]),
        _pad([]),
    ]
    ws = _FakeWS()
    monkeypatch.setattr(os_.sheet_service, "get_worksheet", lambda d: ws)

    def fake_read_range(_ws, rng):
        return existing if rng.startswith("N") else sub_grid

    def fake_write_range(_ws, rng, body, raw=False):
        ws.writes.append((rng, body))

    monkeypatch.setattr(os_.sheet_service, "read_range", fake_read_range)
    monkeypatch.setattr(os_.sheet_service, "write_range", fake_write_range)

    os_.integrate_ordering("20260420")
    body = next(w for w in ws.writes if w[0].startswith("N2:V"))[1]
    names = [row[2] for row in body]
    assert names == ["P2", "P3", "P1"]
    # Renumbered
    assert [row[0] for row in body] == ["1", "2", "3"]


# ---------------- sync_ordering_after_diff (Item 2 / 2026-05-15) ----------------

def _setup_sync(monkeypatch, existing_nv, sub_grid, ws_cls=_FakeWS):
    ws = ws_cls()
    monkeypatch.setattr(os_.sheet_service, "get_worksheet", lambda d: ws)
    monkeypatch.setattr(
        os_.sheet_service, "read_range",
        lambda _ws, rng: existing_nv if rng.startswith("N") else sub_grid,
    )
    monkeypatch.setattr(
        os_.sheet_service, "write_range",
        lambda _ws, rng, body, raw=False: ws.writes.append((rng, body)),
    )
    cleared = []
    monkeypatch.setattr(
        os_.sheet_service, "clear_range",
        lambda _ws, rng: cleared.append(rng),
    )
    return ws, cleared


def test_sync_drops_removed_patient(monkeypatch):
    """Chart no longer in sub-tables → row dropped, seq renumbered."""
    existing = [
        ["1", "Z", "甲", "", "", "111", "CAD", "PCI", ""],
        ["2", "Z", "乙", "", "", "222", "AS",  "TAVI", ""],
    ]
    sub_grid = [
        _pad(["Z（1人）"]),
        _pad(["姓名","病歷","EMR","","","術前診斷","預計心導管","註記"]),
        _pad(["甲","111","","","","CAD","PCI",""]),
        _pad([]),
    ]
    ws, _ = _setup_sync(monkeypatch, existing, sub_grid)
    r = os_.sync_ordering_after_diff("20260501")
    assert r["updated"] is True
    assert r["rows"] == 1
    assert r["removed"] == ["222"]
    body = next(w for w in ws.writes if w[0].startswith("N2:V"))[1]
    assert [row[5] for row in body] == ["111"]
    assert body[0][0] == "1"


def test_sync_appends_new_patient(monkeypatch):
    """Chart in sub-tables but not in N-V → appended at end."""
    existing = [
        ["1", "Z", "甲", "員工", "急", "111", "CAD", "PCI", "20260420"],
    ]
    sub_grid = [
        _pad(["Z（2人）"]),
        _pad(["姓名","病歷","EMR","","","術前診斷","預計心導管","註記"]),
        _pad(["甲","111","","","","CAD","PCI",""]),
        _pad(["乙","222","","","","AS","TAVI",""]),
        _pad([]),
    ]
    ws, _ = _setup_sync(monkeypatch, existing, sub_grid)
    r = os_.sync_ordering_after_diff("20260501")
    assert r["rows"] == 2
    assert [a["chart_no"] for a in r["added"]] == ["222"]
    body = next(w for w in ws.writes if w[0].startswith("N2:V"))[1]
    # Old row preserves Q/V manual markers
    assert body[0][3] == "員工"
    assert body[0][8] == "20260420"
    # New row appended with empty Q/V
    assert body[1][5] == "222"
    assert body[1][3] == ""
    assert body[1][8] == ""


def test_sync_reflects_doctor_change(monkeypatch):
    """doctor_changed in sub-tables → O column refreshed in N-V row."""
    existing = [
        ["1", "李文煌", "甲", "", "", "111", "CAD", "PCI", ""],
    ]
    sub_grid = [
        _pad(["新醫師（1人）"]),
        _pad(["姓名","病歷","EMR","","","術前診斷","預計心導管","註記"]),
        _pad(["甲","111","","","","CAD","PCI",""]),
        _pad([]),
    ]
    ws, _ = _setup_sync(monkeypatch, existing, sub_grid)
    r = os_.sync_ordering_after_diff("20260501")
    assert r["doctor_changed"] == [
        {"chart_no": "111", "old": "李文煌", "new": "新醫師"}
    ]
    body = next(w for w in ws.writes if w[0].startswith("N2:V"))[1]
    assert body[0][1] == "新醫師"


def test_integrate_syncs_subtable_note_to_R(monkeypatch):
    """子表格 H 註記 非空 → R 備註 取代 existing R (align with reference repo H→R)."""
    existing = [
        ["1", "Z", "甲", "員工", "舊備註", "111", "old", "old", ""],
    ]
    sub_grid = [
        _pad(["Z（1人）"]),
        _pad(["姓名","病歷","EMR","","","術前診斷","預計心導管","註記"]),
        _pad(["甲","111","","","","CAD","PCI","不排導管"]),
        _pad([]),
    ]
    ws = _FakeWS()
    monkeypatch.setattr(os_.sheet_service, "get_worksheet", lambda d: ws)
    monkeypatch.setattr(os_.sheet_service, "read_range",
                        lambda _ws, rng: existing if rng.startswith("N") else sub_grid)
    monkeypatch.setattr(os_.sheet_service, "write_range",
                        lambda _ws, rng, body, raw=False: ws.writes.append((rng, body)))
    os_.integrate_ordering("20260501")
    body = next(w for w in ws.writes if w[0].startswith("N2:V"))[1]
    assert body[0][3] == "員工"        # Q (住服) preserved
    assert body[0][4] == "不排導管"    # R ← 子表格 H 註記
    assert body[0][8] == ""            # V preserved


def test_integrate_preserves_R_when_subtable_note_empty(monkeypatch):
    """子表格 H 註記 空 → R 保留 (preserve user-typed value)."""
    existing = [
        ["1", "Z", "甲", "", "用戶手填備註", "111", "", "", ""],
    ]
    sub_grid = [
        _pad(["Z（1人）"]),
        _pad(["姓名","病歷","EMR","","","術前診斷","預計心導管","註記"]),
        _pad(["甲","111","","","","CAD","PCI",""]),
        _pad([]),
    ]
    ws = _FakeWS()
    monkeypatch.setattr(os_.sheet_service, "get_worksheet", lambda d: ws)
    monkeypatch.setattr(os_.sheet_service, "read_range",
                        lambda _ws, rng: existing if rng.startswith("N") else sub_grid)
    monkeypatch.setattr(os_.sheet_service, "write_range",
                        lambda _ws, rng, body, raw=False: ws.writes.append((rng, body)))
    os_.integrate_ordering("20260501")
    body = next(w for w in ws.writes if w[0].startswith("N2:V"))[1]
    assert body[0][4] == "用戶手填備註"


def test_sync_appends_new_patient_carries_note(monkeypatch):
    """新增的子表格患者，註記 H → 新 N-V row 的 R 欄."""
    existing = [
        ["1", "Z", "甲", "", "", "111", "CAD", "PCI", ""],
    ]
    sub_grid = [
        _pad(["Z（2人）"]),
        _pad(["姓名","病歷","EMR","","","術前診斷","預計心導管","註記"]),
        _pad(["甲","111","","","","CAD","PCI",""]),
        _pad(["乙","222","","","","AS","TAVI","待會診"]),
        _pad([]),
    ]
    ws, _ = _setup_sync(monkeypatch, existing, sub_grid)
    os_.sync_ordering_after_diff("20260501")
    body = next(w for w in ws.writes if w[0].startswith("N2:V"))[1]
    assert body[1][5] == "222"
    assert body[1][4] == "待會診"


def test_sync_clears_trailing_rows_when_shorter(monkeypatch):
    """If new block is shorter than old, leftover N-V rows should be cleared."""
    existing = [
        ["1", "Z", "甲", "", "", "111", "", "", ""],
        ["2", "Z", "乙", "", "", "222", "", "", ""],
        ["3", "Z", "丙", "", "", "333", "", "", ""],
    ]
    sub_grid = [
        _pad(["Z（1人）"]),
        _pad(["姓名","病歷","EMR","","","術前診斷","預計心導管","註記"]),
        _pad(["甲","111","","","","CAD","PCI",""]),
        _pad([]),
    ]
    ws, cleared = _setup_sync(monkeypatch, existing, sub_grid)
    r = os_.sync_ordering_after_diff("20260501")
    assert r["rows"] == 1
    # End is N2:V2, so cleared should hit N3:V4
    assert any("N3:V" in c for c in cleared)
