"""Regression: get_worksheet must refresh stale tab metadata + retry.

Field bug: 20260601 was created by another running instance; this
process held a memoised gspread Spreadsheet whose cached worksheet list
predated that tab, so get_worksheet("20260601") raised WorksheetNotFound
and the 重新載入 panel showed "找不到分頁 20260601".
"""
from __future__ import annotations

import gspread

from app.services import sheet_service


class _FakeWS:
    def __init__(self, title):
        self.title = title


class _FakeSpreadsheet:
    """Knows tab '20260601' only AFTER fetch_sheet_metadata() is called —
    mimics a stale cache that a metadata refresh repairs."""
    def __init__(self):
        self._known = {"20260501"}
        self.fetched = 0

    def fetch_sheet_metadata(self):
        self.fetched += 1
        self._known.add("20260601")

    def worksheet(self, name):
        if name in self._known:
            return _FakeWS(name)
        raise gspread.exceptions.WorksheetNotFound(name)

    def worksheets(self):
        return [_FakeWS(t) for t in sorted(self._known)]


def test_get_worksheet_refreshes_and_retries(monkeypatch):
    sp = _FakeSpreadsheet()
    monkeypatch.setattr(sheet_service, "get_spreadsheet", lambda: sp)
    # First lookup misses (stale cache) → refresh → retry succeeds.
    ws = sheet_service.get_worksheet("20260601")
    assert ws is not None and ws.title == "20260601"
    assert sp.fetched == 1


def test_get_worksheet_truly_missing_returns_none(monkeypatch):
    sp = _FakeSpreadsheet()
    monkeypatch.setattr(sheet_service, "get_spreadsheet", lambda: sp)
    assert sheet_service.get_worksheet("29991231") is None
    assert sp.fetched == 1  # refreshed once, still absent → None


def test_list_sheets_refreshes_before_listing(monkeypatch):
    sp = _FakeSpreadsheet()
    monkeypatch.setattr(sheet_service, "get_spreadsheet", lambda: sp)
    titles = sheet_service.list_sheets()
    assert "20260601" in titles  # visible only after the forced refresh
