"""
Step 1 — Image OCR.
LLM vision reads a hospital admission-list screenshot and returns structured rows.
Output columns match the date sheet's main data layout (A-L).
"""
from __future__ import annotations

from typing import Optional

from ..llm import get_llm, extract_json
from . import sheet_service

OCR_PROMPT = """你是醫療排程助理。請把這張住院名單截圖轉成 JSON 陣列。

每一列代表一位病人，欄位必須是這 12 個（缺的填空字串）：
  "admit_date"    實際住院日 (YYYY/MM/DD 或 MM/DD)
  "op_date"       開刀日 / 手術日（沒有填空字串）
  "department"    科別（常見：心內、CV）
  "doctor"        主治醫師（中文全名，例如「李文煌」）
  "icd_diagnosis" 主診斷 ICD（例如「I25.10 Atherosclerotic heart disease」）
  "name"          病人姓名（中文全名）
  "gender"        性別（男/女）
  "age"           年齡（數字）
  "chart_no"      病歷號碼（純數字字串，保留前導 0）
  "bed"           病床號
  "hint"          入院提示
  "urgent"        住急（有/無 或 空字串）

注意：
- 病歷號一定是數字字串，不要加斜線或空白。
- 若某欄模糊不確定，寫入你的最佳猜測並在欄位值後加「?」。
- 只輸出 JSON 陣列，不要其他文字。
"""


async def ocr_image(image_bytes: bytes, mime: str = "image/png") -> list[dict]:
    """Return list of patient dicts parsed from the screenshot."""
    llm = get_llm()
    raw = await llm.vision(image_bytes, OCR_PROMPT, mime=mime)
    data = extract_json(raw)
    if not isinstance(data, list):
        raise ValueError(f"LLM 未返回陣列。原始輸出前 500 字：\n{raw[:500]}")
    # Normalize keys / coerce types
    out = []
    for row in data:
        if not isinstance(row, dict):
            continue
        out.append({
            "admit_date":    str(row.get("admit_date", "")).strip(),
            "op_date":       str(row.get("op_date", "")).strip(),
            "department":    str(row.get("department", "")).strip(),
            "doctor":        str(row.get("doctor", "")).strip(),
            "icd_diagnosis": str(row.get("icd_diagnosis", "")).strip(),
            "name":          str(row.get("name", "")).strip(),
            "gender":        str(row.get("gender", "")).strip(),
            "age":           str(row.get("age", "")).strip(),
            "chart_no":      str(row.get("chart_no", "")).strip(),
            "bed":           str(row.get("bed", "")).strip(),
            "hint":          str(row.get("hint", "")).strip(),
            "urgent":        str(row.get("urgent", "")).strip(),
        })
    return out


def _patients_to_ab_rows(patients: list[dict]) -> list[list[str]]:
    return [[
        p.get("admit_date", ""), p.get("op_date", ""),
        p.get("department", ""), p.get("doctor", ""),
        p.get("icd_diagnosis", ""), p.get("name", ""),
        p.get("gender", ""), p.get("age", ""),
        p.get("chart_no", ""), p.get("bed", ""),
        p.get("hint", ""), p.get("urgent", ""),
    ] for p in patients]


def diff_main_data(existing_rows: list[list[str]],
                   new_patients: list[dict]) -> dict:
    """
    Compare A-L main-data rows (existing) against freshly OCR'd patient list.
    Pure function — no Sheet access.

    Match key = chart_no (I 欄 in existing = index 8).
    Patients in either side without chart_no are reported as "unmatched".

    Returns:
      {
        "existing_count": int,
        "new_count":      int,
        "added":    [{chart_no, name, doctor}],       # new∖existing
        "removed":  [{chart_no, name, doctor}],       # existing∖new
        "kept":     [{chart_no, name, doctor_new, doctor_old}],
        "doctor_changed": [{chart_no, name, old, new}],
        "unmatched_existing": [row-index in existing (0-based, 1=sheet row 2)],
        "unmatched_new":      [index in new_patients],
      }
    """
    def existing_chart(r):
        return (r + [""] * 9)[8].strip() if r else ""

    ex_by_chart = {}
    unmatched_existing = []
    for i, r in enumerate(existing_rows):
        ch = existing_chart(r)
        if not ch:
            # skip fully-blank rows silently
            if any((c or "").strip() for c in (r or [])):
                unmatched_existing.append(i)
            continue
        ex_by_chart[ch] = {
            "chart_no": ch,
            "name":    (r + [""] * 6)[5].strip(),
            "doctor":  (r + [""] * 4)[3].strip(),
            "row":     i,
        }

    new_by_chart = {}
    unmatched_new = []
    for i, p in enumerate(new_patients):
        ch = (p.get("chart_no") or "").strip()
        if not ch:
            unmatched_new.append(i)
            continue
        new_by_chart[ch] = {
            "chart_no": ch,
            "name":    (p.get("name") or "").strip(),
            "doctor":  (p.get("doctor") or "").strip(),
        }

    ex_set = set(ex_by_chart)
    new_set = set(new_by_chart)

    added    = [new_by_chart[c] for c in new_set - ex_set]
    removed  = [ex_by_chart[c] for c in ex_set - new_set]
    kept = []
    doctor_changed = []
    for c in ex_set & new_set:
        old = ex_by_chart[c]
        nw  = new_by_chart[c]
        kept.append({
            "chart_no":   c,
            "name":       nw["name"] or old["name"],
            "doctor_old": old["doctor"],
            "doctor_new": nw["doctor"],
        })
        if nw["doctor"] and old["doctor"] and nw["doctor"] != old["doctor"]:
            doctor_changed.append({
                "chart_no": c, "name": nw["name"] or old["name"],
                "old": old["doctor"], "new": nw["doctor"],
            })

    return {
        "existing_count": len(ex_by_chart),
        "new_count":      len(new_by_chart),
        "added":          added,
        "removed":        removed,
        "kept":           kept,
        "doctor_changed": doctor_changed,
        "unmatched_existing": unmatched_existing,
        "unmatched_new":      unmatched_new,
    }


def plan_write(date: str, patients: list[dict]) -> dict:
    """
    Read current A-L of the date sheet and compute a diff against the
    new OCR'd list. Does NOT write.

    Returns the diff plus `sheet_has_data: bool` so the UI can decide
    whether to require a confirm before applying.
    """
    ws = sheet_service.get_worksheet(date)
    if ws is None:
        # Sheet doesn't exist yet → no diff possible, first-time write
        return {
            "sheet_has_data": False,
            "existing_count": 0,
            "new_count":      len([p for p in patients
                                   if (p.get("chart_no") or "").strip()]),
            "added":          [],
            "removed":        [],
            "kept":           [],
            "doctor_changed": [],
            "unmatched_existing": [],
            "unmatched_new":      [],
        }
    existing = sheet_service.read_range(ws, "A2:L200")
    # Trim trailing blank rows
    while existing and not any((c or "").strip() for c in existing[-1]):
        existing.pop()
    diff = diff_main_data(existing, patients)
    diff["sheet_has_data"] = bool(existing)
    return diff


def write_to_sheet(date: str, patients: list[dict],
                   allow_overwrite: bool = False) -> dict:
    """
    Write main data A2:L{n+1} with reviewed patient rows.

    If the sheet already has data AND `allow_overwrite` is False, we refuse
    and return the diff — caller must re-submit with allow_overwrite=True
    after the user confirms the add/remove list.

    Note: this MVP only rewrites A-L. Sub-tables (below main data) and N-V
    ordering are NOT auto-rebuilt — caller should rerun Steps 2-4 after
    significant adds/removes. Cancelled patients still linger in sub-tables
    until cleaned up manually or in a later phase.
    """
    ws = sheet_service.ensure_date_sheet(date)
    if not patients:
        return {"rows": 0, "sheet": date}

    if not allow_overwrite:
        existing = sheet_service.read_range(ws, "A2:L200")
        while existing and not any((c or "").strip() for c in existing[-1]):
            existing.pop()
        if existing:
            diff = diff_main_data(existing, patients)
            diff["sheet_has_data"] = True
            diff["needs_confirm"]  = True
            diff["sheet"]          = date
            return diff

    body = _patients_to_ab_rows(patients)
    end_row = 1 + len(body)
    sheet_service.write_range(ws, f"A2:L{end_row}", body, raw=False)
    return {"rows": len(body), "sheet": date,
            "range": f"A2:L{end_row}", "needs_confirm": False}
