"""
Thin wrapper around the user's Google Sheet. Creds & sheet ID come from
app/config.py (not the hard-coded ones in the repo's gsheet_utils.py).

We implement the subset of operations the app actually uses so this module
stays small and independently testable.
"""
from __future__ import annotations

import time
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

from .. import config as appconfig

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

BLUE_HEADER = {"red": 0.741, "green": 0.843, "blue": 0.933}
BLACK = {"red": 0, "green": 0, "blue": 0}

_client = None
_sh = None
_sh_id = None


def _get_client():
    global _client
    cfg = appconfig.load()
    if _client is None:
        creds = Credentials.from_service_account_file(cfg.google_creds_path, scopes=SCOPES)
        _client = gspread.authorize(creds)
    return _client


def get_spreadsheet():
    global _sh, _sh_id
    cfg = appconfig.load()
    if _sh is None or _sh_id != cfg.sheet_id:
        _sh = _get_client().open_by_key(cfg.sheet_id)
        _sh_id = cfg.sheet_id
    return _sh


def reset_cache():
    """Drop cached client/sheet — call after settings change."""
    global _client, _sh, _sh_id, _fg_cache
    _client = None
    _sh = None
    _sh_id = None
    _fg_cache = None


# ---- F/G options from "下拉選單" worksheet (user-maintained source of truth) ----
# Cached for the lifetime of the spreadsheet object — invalidate via reset_cache().
_fg_cache: tuple[list[str], list[str]] | None = None
FG_OPTIONS_SHEET = "下拉選單"


def read_fg_options_from_sheet() -> tuple[list[str], list[str]] | None:
    """Read F (col A) + G (col D) option lists from the 下拉選單 worksheet.

    Returns (f_opts, g_opts) — deduplicated, first-appearance order, blanks
    skipped. Returns None if the worksheet doesn't exist (caller should fall
    back to hardcoded lists).

    Result is cached for the session; bust via reset_cache().
    """
    global _fg_cache
    if _fg_cache is not None:
        return _fg_cache
    ws = get_worksheet(FG_OPTIONS_SHEET)
    if ws is None:
        return None
    rows = ws.get("A2:D200") or []  # skip header row 1
    f_seen, g_seen = set(), set()
    f_opts, g_opts = [], []
    for r in rows:
        f = ((r + [""] * 4)[0] or "").strip()
        g = ((r + [""] * 4)[3] or "").strip()
        if f and f not in f_seen:
            f_seen.add(f)
            f_opts.append(f)
        if g and g not in g_seen:
            g_seen.add(g)
            g_opts.append(g)
    if not (f_opts or g_opts):
        return None
    _fg_cache = (f_opts, g_opts)
    return _fg_cache


def list_sheets() -> list[str]:
    return [ws.title for ws in get_spreadsheet().worksheets()]


def get_worksheet(name: str):
    try:
        return get_spreadsheet().worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        return None


def read_range(ws, a1: str) -> list[list[str]]:
    return ws.get(a1) or []


def write_range(ws, a1: str, data: list[list], raw: bool = True):
    ws.update(
        values=data, range_name=a1,
        value_input_option="RAW" if raw else "USER_ENTERED",
    )


def clear_range(ws, a1: str):
    ws.batch_clear([a1])


def batch_write_cells(ws, patches: list[tuple[str, str]], raw: bool = False):
    """Apply many scattered (a1, value) cell writes in one API call.

    Empty `patches` is a no-op (gspread errors on empty body).
    """
    if not patches:
        return
    ws.batch_update(
        [{"range": a1, "values": [[val]]} for a1, val in patches],
        value_input_option="RAW" if raw else "USER_ENTERED",
    )


def format_header(ws, row: int, ncols: int, start_col: int = 1):
    sh = get_spreadsheet()
    sh.batch_update({"requests": [{
        "repeatCell": {
            "range": {"sheetId": ws.id,
                      "startRowIndex": row - 1, "endRowIndex": row,
                      "startColumnIndex": start_col - 1,
                      "endColumnIndex": start_col + ncols - 1},
            "cell": {"userEnteredFormat": {
                "backgroundColor": BLUE_HEADER,
                "textFormat": {"bold": True, "fontSize": 11},
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE",
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)",
        }
    }]})


def ensure_chart_text_format(ws) -> None:
    """Force TEXT numberFormat on every column that holds a 病歷號 so leading
    zeros survive a USER_ENTERED write. Idempotent — safe to call before
    every write to those columns.

    Ranges (zero-indexed, exclusive-end):
      * Main I (col index 8)         rows 2..500 — A-L block
      * Ordering S (col index 18)    rows 2..500 — N-V block
      * Sub-table B (col index 1)    rows 2..500 — everywhere a sub-table can land

    Sub-tables live below main data; we format col B from row 2 onwards so any
    future block automatically inherits TEXT formatting on its 病歷號 column.
    """
    sh = get_spreadsheet()

    def _req(start_col: int, end_col: int) -> dict:
        return {"repeatCell": {
            "range": {"sheetId": ws.id,
                      "startRowIndex": 1, "endRowIndex": 500,
                      "startColumnIndex": start_col, "endColumnIndex": end_col},
            "cell": {"userEnteredFormat": {"numberFormat": {"type": "TEXT"}}},
            "fields": "userEnteredFormat.numberFormat",
        }}

    sh.batch_update({"requests": [
        _req(8, 9),    # main I
        _req(18, 19),  # ordering S
        _req(1, 2),    # sub-table B
    ]})


def set_fg_validation(ws, start_row: int, end_row: int,
                      f_opts: list[str], g_opts: list[str]) -> None:
    """Apply Sheets data validation on F (col 6) + G (col 7) of the sub-table
    area, allowing custom values (strict=False / WARNING).

    Sub-tables live below A-L main; F/G in main are 姓名/性別 and must NOT get
    this validation. Caller must pass `start_row` ≥ first sub-table row.

    Idempotent: re-applying replaces the previous rule.
    """
    if start_row < 2 or end_row < start_row or not (f_opts or g_opts):
        return
    sh = get_spreadsheet()

    def _rule(col_idx: int, opts: list[str]) -> dict:
        return {"setDataValidation": {
            "range": {"sheetId": ws.id,
                      "startRowIndex": start_row - 1, "endRowIndex": end_row,
                      "startColumnIndex": col_idx, "endColumnIndex": col_idx + 1},
            "rule": {
                "condition": {"type": "ONE_OF_LIST",
                              "values": [{"userEnteredValue": v} for v in opts]},
                "showCustomUi": True,
                "strict": False,  # allow user to type values not in the list
            },
        }}

    requests = []
    if f_opts:
        requests.append(_rule(5, f_opts))   # F = 0-indexed col 5
    if g_opts:
        requests.append(_rule(6, g_opts))   # G = 0-indexed col 6
    if requests:
        sh.batch_update({"requests": requests})


def ensure_date_sheet(date: str):
    """Return worksheet for a date like '20260420'; create if missing."""
    sh = get_spreadsheet()
    ws = get_worksheet(date)
    if ws is None:
        ws = sh.add_worksheet(title=date, rows=200, cols=26)
        time.sleep(0.5)
        # Header row (A-L for main, N-W for ordering)
        header_main = ["實際住院日", "開刀日", "科別", "主治醫師", "主診斷(ICD)",
                       "姓名", "性別", "年齡", "病歷號碼", "病床號",
                       "入院提示", "住急"]
        header_order = ["序號", "主治醫師", "病人姓名", "備註(住服)", "備註",
                        "病歷號", "術前診斷", "預計心導管", "每日續等清單", "改期"]
        write_range(ws, "A1:L1", [header_main])
        write_range(ws, "N1:W1", [header_order])
        format_header(ws, 1, 12, 1)
        format_header(ws, 1, 10, 14)
        # Force TEXT format on chart-no columns BEFORE any data lands —
        # otherwise USER_ENTERED parses "01937569" → 1937569 (lost zero).
        ensure_chart_text_format(ws)
    return ws


def connection_check() -> tuple[bool, str]:
    """Try to open the spreadsheet. Returns (ok, message)."""
    try:
        sh = get_spreadsheet()
        titles = [ws.title for ws in sh.worksheets()][:5]
        return True, f"連線成功。前幾個分頁：{', '.join(titles)}"
    except FileNotFoundError as e:
        return False, f"找不到 service-account 檔：{e}"
    except Exception as e:
        return False, f"連線失敗：{e}"
