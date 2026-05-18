"""Card 1 (排班) — Google Sheets I/O for the duty schedule.

Distinct from sheet_service (card 3 admission sheet). Uses the same
service-account credentials but a different spreadsheet ID
(cfg.schedule_sheet_id).

Ported from CV-Schedulling-APP/gsheet_io.py with the SHEET_ID + creds
plumbing moved into app.config.
"""
from __future__ import annotations

import calendar
from datetime import date
from typing import Callable

import gspread
from google.oauth2.service_account import Credentials

from .. import config as appconfig
from .cv_solver import TAIWAN_HOLIDAYS, is_taiwan_holiday, make_stat_type_fn

__all__ = [
    "TAIWAN_HOLIDAYS", "is_taiwan_holiday", "make_stat_type_fn",
    "get_sheet", "reset_cache", "connection_check",
    "write_calendar_sheet", "write_monthly_stats",
    "load_cumulative_stats", "update_cumulative_stats",
    "previous_year_month", "read_calendar_tail",
    "DEFAULT_MONTHLY_HEADERS", "CUMULATIVE_TAB",
]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

YELLOW = {"red": 1.0, "green": 235 / 255, "blue": 156 / 255}
CUMULATIVE_TAB = "值班總數統計"
DEFAULT_MONTHLY_HEADERS = ["姓名", "平日班", "週五班", "假日班", "週六班", "週日班"]

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


def get_sheet():
    global _sh, _sh_id
    cfg = appconfig.load()
    if not cfg.schedule_sheet_id:
        raise RuntimeError("尚未設定 schedule_sheet_id — 請到「設定」頁填入排班用的 Google Sheet ID")
    if _sh is None or _sh_id != cfg.schedule_sheet_id:
        _sh = _get_client().open_by_key(cfg.schedule_sheet_id)
        _sh_id = cfg.schedule_sheet_id
    return _sh


def reset_cache():
    global _client, _sh, _sh_id
    _client = None
    _sh = None
    _sh_id = None


def connection_check() -> tuple[bool, str]:
    try:
        sh = get_sheet()
        titles = [ws.title for ws in sh.worksheets()][:5]
        return True, f"排班表連線成功。前幾個分頁：{', '.join(titles)}"
    except Exception as e:
        return False, f"排班表連線失敗：{e}"


def _ensure_worksheet(sheet, title: str, rows: int, cols: int):
    try:
        ws = sheet.worksheet(title)
        ws.clear()
        ws.resize(rows=rows, cols=cols)
    except gspread.exceptions.WorksheetNotFound:
        ws = sheet.add_worksheet(title=title, rows=rows, cols=cols)
    return ws


def previous_year_month(year: int, month: int) -> tuple[int, int]:
    """(year, month) of the calendar month immediately before (year, month)."""
    return (year - 1, 12) if month == 1 else (year, month - 1)


def read_calendar_tail(sheet, year: int, month: int, n: int = 2) -> dict:
    """Read the last `n` filled days from the {YYYYMM} calendar tab.

    Returns {date: doctor_name}. Empty dict if the tab doesn't exist (e.g.
    the previous month was never written through this app). Used by the
    solver for cross-month rules (不連兩天 / QOD across the month boundary).

    Ported verbatim from CV-Schedulling-APP/gsheet_io.read_calendar_tail —
    the calendar layout written by `write_calendar_sheet` is identical
    (header row 0, then per week: date_row at 2*r+1, name_row at 2*r+2).
    """
    sheet_name = f"{year}{month:02d}"
    try:
        ws = sheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        return {}
    all_values = ws.get_all_values()
    if not all_values or len(all_values) < 2:
        return {}

    month_cal = calendar.monthcalendar(year, month)
    result: dict = {}
    for r_idx, week in enumerate(month_cal):
        name_row_idx = r_idx * 2 + 2  # header row 0; date 2r+1; name 2r+2
        if name_row_idx >= len(all_values):
            break
        name_row = all_values[name_row_idx]
        for c_idx, day in enumerate(week):
            if day == 0 or c_idx >= len(name_row):
                continue
            name = (name_row[c_idx] or "").strip()
            if name:
                result[date(year, month, day)] = name

    sorted_dates = sorted(result.keys(), reverse=True)
    return {d: result[d] for d in sorted_dates[:n]}


def write_calendar_sheet(
    sheet, sheet_name: str, year: int, month: int,
    result: dict, is_holiday_fn: Callable[[date], bool],
):
    """Write the Mon-Sun calendar grid, yellow-highlight holidays.

    result: {date: doctor_name}
    """
    month_cal = calendar.monthcalendar(year, month)
    rows = 1 + len(month_cal) * 2
    cols = 7

    header = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    grid: list[list] = [header]
    holiday_cells = []
    for r_idx, week in enumerate(month_cal):
        date_row: list = [""] * 7
        name_row: list = [""] * 7
        for c_idx, day in enumerate(week):
            if day == 0:
                continue
            d_obj = date(year, month, day)
            date_row[c_idx] = day
            name_row[c_idx] = result.get(d_obj, "")
            if is_holiday_fn(d_obj):
                holiday_cells.append((r_idx * 2 + 1, c_idx))
                holiday_cells.append((r_idx * 2 + 2, c_idx))
        grid.append(date_row)
        grid.append(name_row)

    ws = _ensure_worksheet(sheet, sheet_name, rows=rows, cols=cols)
    ws.update(range_name="A1", values=grid, value_input_option="USER_ENTERED")

    requests = [{
        "repeatCell": {
            "range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": 0, "endColumnIndex": 7},
            "cell": {"userEnteredFormat": {
                "textFormat": {"bold": True},
                "horizontalAlignment": "CENTER",
            }},
            "fields": "userEnteredFormat.textFormat.bold,userEnteredFormat.horizontalAlignment",
        }
    }]
    for (r, c) in holiday_cells:
        requests.append({
            "repeatCell": {
                "range": {"sheetId": ws.id, "startRowIndex": r, "endRowIndex": r + 1,
                          "startColumnIndex": c, "endColumnIndex": c + 1},
                "cell": {"userEnteredFormat": {"backgroundColor": YELLOW}},
                "fields": "userEnteredFormat.backgroundColor",
            }
        })
    requests.append({
        "updateDimensionProperties": {
            "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                      "startIndex": 0, "endIndex": 7},
            "properties": {"pixelSize": 110},
            "fields": "pixelSize",
        }
    })
    sheet.batch_update({"requests": requests})


def write_monthly_stats(sheet, sheet_name: str, stats_rows: list[dict],
                        headers: list[str] | None = None):
    if headers is None:
        headers = DEFAULT_MONTHLY_HEADERS
    grid: list[list] = [list(headers)]
    for r in stats_rows:
        grid.append([r[h] for h in headers])
    ws = _ensure_worksheet(sheet, sheet_name, rows=len(grid), cols=len(headers))
    ws.update(range_name="A1", values=grid, value_input_option="USER_ENTERED")


def _find_cum_cols(header: list[str]) -> dict:
    def find(*predicates, required=True):
        for pred in predicates:
            for i, h in enumerate(header):
                if pred(h):
                    return i
        if required:
            raise RuntimeError(f"Unexpected {CUMULATIVE_TAB} header: {header}")
        return None

    return {
        "name":    find(lambda h: h == "姓名"),
        "weekday": find(lambda h: h.startswith("平日班")),
        "fri":     find(lambda h: h in ("週五班", "周五班")),
        "sat":     find(lambda h: h in ("週六班", "周六班")),
        "sun":     find(lambda h: h in ("週日班", "周日班")),
        "holiday": find(lambda h: h.startswith("假日班")),
        "total":   find(lambda h: h == "總班數", required=False),
    }


def load_cumulative_stats(sheet) -> dict:
    """Read 值班總數統計 → baseline dict for cv_solver."""
    ws = sheet.worksheet(CUMULATIVE_TAB)
    all_values = ws.get_all_values()
    if not all_values:
        return {}
    cols = _find_cum_cols(all_values[0])

    def as_int(row, idx):
        if idx >= len(row):
            return 0
        v = row[idx].strip() if isinstance(row[idx], str) else row[idx]
        return int(v) if v not in (None, "") else 0

    result: dict = {}
    for row in all_values[1:]:
        if not row or not row[cols["name"]]:
            continue
        result[row[cols["name"]]] = {
            "平日": as_int(row, cols["weekday"]),
            "週五": as_int(row, cols["fri"]),
            "週六": as_int(row, cols["sat"]),
            "週日": as_int(row, cols["sun"]),
            "假日": as_int(row, cols["holiday"]),
        }
    return result


def read_monthly_stats(sheet, sheet_name: str) -> dict:
    """Read a `{YYYYMM} 班數統計` tab back into {name: {col: int}}.

    Used by the writer to recover the previous monthly contribution when
    rewriting the same month — so the cumulative tab can subtract prev +
    add new instead of double-counting. Returns {} if tab doesn't exist.
    """
    import gspread
    try:
        ws = sheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        return {}
    all_values = ws.get_all_values()
    if not all_values:
        return {}
    header = all_values[0]

    def find_col(name):
        for i, h in enumerate(header):
            if h == name:
                return i
        return None

    cols = {key: find_col(key) for key in
            ("姓名", "平日班", "週五班", "週六班", "週日班", "假日班")}
    if cols["姓名"] is None:
        return {}

    def as_int(row, idx):
        if idx is None or idx >= len(row):
            return 0
        v = row[idx].strip() if isinstance(row[idx], str) else row[idx]
        try:
            return int(v) if v not in (None, "") else 0
        except (ValueError, TypeError):
            return 0

    result: dict = {}
    for row in all_values[1:]:
        if not row or cols["姓名"] >= len(row) or not row[cols["姓名"]]:
            continue
        name = row[cols["姓名"]]
        result[name] = {
            "平日班": as_int(row, cols["平日班"]),
            "週五班": as_int(row, cols["週五班"]),
            "週六班": as_int(row, cols["週六班"]),
            "週日班": as_int(row, cols["週日班"]),
            "假日班": as_int(row, cols["假日班"]),
        }
    return result


def update_cumulative_stats(sheet, baseline: dict, monthly_stats: dict,
                            previous_monthly: dict | None = None):
    """Overwrite 值班總數統計 = baseline + this month's stats.

    `previous_monthly`: optional same shape as monthly_stats. When supplied,
    baseline is treated as already including this previous month's
    contribution → subtract prev before adding new. Lets the caller safely
    re-write a month that was written before without double-counting.
    """
    if previous_monthly:
        zero = {"平日班": 0, "週五班": 0, "週六班": 0, "週日班": 0, "假日班": 0}
        adjusted = {}
        for name, base in baseline.items():
            prev = previous_monthly.get(name, zero)
            adjusted[name] = {
                "平日": base["平日"] - prev["平日班"],
                "週五": base["週五"] - prev["週五班"],
                "週六": base["週六"] - prev["週六班"],
                "週日": base["週日"] - prev["週日班"],
                "假日": base["假日"] - prev["假日班"],
            }
        baseline = adjusted

    ws = sheet.worksheet(CUMULATIVE_TAB)
    all_values = ws.get_all_values()
    if not all_values:
        return
    cols = _find_cum_cols(all_values[0])

    header = list(all_values[0])
    if cols["total"] is None:
        header.append("總班數")
        ws.update(range_name="A1", values=[header], value_input_option="USER_ENTERED")
        cols["total"] = len(header) - 1

    header_len = len(header)

    updated_rows: list[list] = []
    for row in all_values[1:]:
        name = row[cols["name"]]
        base = baseline.get(name)
        month = monthly_stats.get(name, {"平日班": 0, "週五班": 0, "週六班": 0, "週日班": 0, "假日班": 0})
        if base is None:
            updated_rows.append(row)
            continue
        new_row = list(row) + [""] * (header_len - len(row))
        new_weekday = base["平日"] + month["平日班"]
        new_fri = base["週五"] + month["週五班"]
        new_sat = base["週六"] + month["週六班"]
        new_sun = base["週日"] + month["週日班"]
        new_hol = base["假日"] + month["假日班"]
        new_row[cols["weekday"]] = new_weekday
        new_row[cols["fri"]] = new_fri
        new_row[cols["sat"]] = new_sat
        new_row[cols["sun"]] = new_sun
        new_row[cols["holiday"]] = new_hol
        new_row[cols["total"]] = new_weekday + new_fri + new_hol
        updated_rows.append(new_row)

    ws.update(range_name="A2", values=updated_rows, value_input_option="USER_ENTERED")
