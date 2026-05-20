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

    On overwrite, also auto-updates existing per-doctor sub-tables to reflect
    added / removed / doctor-changed patients (preserves F/G/E/H for kept
    patients; new patients start blank — run Step 3 EMR to fill F/G).
    Patients whose doctor has no existing sub-table trigger creation of a
    new sub-table block at the end (preserves 2-row gap convention).
    N-V 入院序 is then re-synced via ordering_service.sync_ordering_after_diff
    so 序號 / O column / T-U stay consistent (Q/V manual markers preserved).
    """
    from . import format_check_service  # local import to avoid cycle
    ws = sheet_service.ensure_date_sheet(date)
    if not patients:
        return {"rows": 0, "sheet": date}

    # Defensively re-apply TEXT format on chart-no columns BEFORE we write
    # any 病歷號. ensure_date_sheet covers brand-new sheets; this covers
    # existing sheets that pre-date the TEXT-format fix.
    try:
        sheet_service.ensure_chart_text_format(ws)
    except Exception:
        pass  # best-effort — don't block the OCR write on a format API hiccup

    existing = sheet_service.read_range(ws, "A2:L200")
    while existing and not any((c or "").strip() for c in existing[-1]):
        existing.pop()

    if existing and not allow_overwrite:
        diff = diff_main_data(existing, patients)
        diff["sheet_has_data"] = True
        diff["needs_confirm"]  = True
        diff["sheet"]          = date
        return diff

    # ---- First-ever write (sheet empty): write the full OCR list. ----
    if not existing:
        body = _patients_to_ab_rows(patients)
        end_row = 1 + len(body)
        sheet_service.write_range(ws, f"A2:L{end_row}", body, raw=False)
        return {
            "rows": len(body), "sheet": date,
            "range": f"A2:L{end_row}", "needs_confirm": False,
            "subtable_update": {"updated": False},
            "ordering_update": {"updated": False},
        }

    # ---- Re-upload of a screenshot for a sheet that already has data. ----
    # User rule (2026-05-19): the new screenshot is consulted ONLY for
    # MEMBERSHIP — has anyone been added or removed?
    #   * No add / no remove  → 照舊: touch NOTHING (every already-keyed
    #     A-L cell + sub-table stays exactly as the user left it).
    #   * Add / remove present → keep every kept patient's A-L row VERBATIM
    #     (never re-write keyed cells from OCR), only DROP removed-chart
    #     rows and APPEND new-chart rows; then reconcile sub-tables + N-V.
    pre_grid = sheet_service.read_range(ws, "A1:H500")
    diff = diff_main_data(existing, patients)

    if not diff["added"] and not diff["removed"]:
        return {
            "rows": len(existing), "sheet": date,
            "range": f"A2:L{1 + len(existing)}", "needs_confirm": False,
            "unchanged": True,
            "diff": {"added": [], "removed": [],
                     "doctor_changed": diff["doctor_changed"]},
            "subtable_update": {"updated": False},
            "ordering_update": {"updated": False},
        }

    def _chart_of(row):
        return (list(row) + [""] * 9)[8].strip()

    removed_charts = {r["chart_no"] for r in diff["removed"]}
    added_charts   = {a["chart_no"] for a in diff["added"]}

    # Kept rows: existing A-L verbatim, minus removed, original order.
    kept_rows = [
        (list(row) + [""] * 12)[:12]
        for row in existing
        if _chart_of(row) not in removed_charts
    ]
    # Appended rows: OCR values only for the genuinely-new charts.
    added_rows = _patients_to_ab_rows([
        p for p in patients
        if (p.get("chart_no") or "").strip() in added_charts
    ])
    merged = kept_rows + added_rows
    end_row = 1 + len(merged)
    sheet_service.write_range(ws, f"A2:L{end_row}", merged, raw=False)
    old_main_end = 1 + len(existing)
    if old_main_end > end_row:
        sheet_service.clear_range(ws, f"A{end_row + 1}:L{old_main_end}")

    sub_result: dict = {"updated": False}
    ordering_result: dict = {"updated": False}
    if diff["added"] or diff["removed"] or diff["doctor_changed"]:
        sub_result = _apply_diff_to_subtables(
            ws, pre_grid, diff, patients, format_check_service,
        )
        if sub_result.get("updated"):
            # Re-sync N-V so seq numbers, doctor column, T/U stay consistent
            # with the new sub-table contents (Q/V preserved per chart_no).
            try:
                from . import ordering_service  # local import to avoid cycle
                ordering_result = ordering_service.sync_ordering_after_diff(date)
            except Exception as e:
                ordering_result = {"updated": False, "error": str(e)}

    return {
        "rows": len(merged), "sheet": date,
        "range": f"A2:L{end_row}", "needs_confirm": False,
        "diff": {"added": diff["added"], "removed": diff["removed"],
                 "doctor_changed": diff["doctor_changed"]},
        "subtable_update":   sub_result,
        "ordering_update":   ordering_result,
    }


# ----------------------- sub-table sync (Phase 9) -----------------------

def _apply_diff_to_subtables(ws, grid, diff, new_patients, fmt_svc) -> dict:
    """
    Re-render the sub-table area (below main data) so that:
      - patients in `diff.removed` are dropped from whichever sub-table
        currently holds them
      - patients in `diff.added` are appended to their A-L doctor's
        sub-table (if that doctor has an existing sub-table)

    `diff.doctor_changed` is INTENTIONALLY IGNORED per user rule
    (2026-05-20): re-uploading a same-day screenshot must NEVER touch rows
    that share an existing chart_no, even if the new screenshot shows a
    different 主治醫師 for that chart. Same chart = same row, full stop.
    Doctor moves remain a manual edit; the UI surfaces `doctor_changed` for
    information only.

    Preserves existing C/D/E/F/G/H cells for kept patients. New rows start
    blank apart from name + chart_no. If an add targets a doctor without
    an existing sub-table, the patient is reported in `unattached_added`
    and left for the user.
    """
    col_a = [(row[0] if row else "") for row in grid]
    structure = fmt_svc.parse_structure(col_a)
    real_subs = [s for s in structure["subs"]
                 if s.get("doctor") and not s.get("orphan")]
    if not real_subs:
        return {"updated": False, "reason": "no existing sub-tables"}

    SUB_HEADER = ["姓名", "病歷號", "EMR", "summary", "入院序",
                  "術前診斷", "預計心導管", "註記"]

    # Build current per-doctor patient lists (preserve original order on sheet)
    subs_by_doctor: dict[str, list[list[str]]] = {}
    doctor_order: list[str] = []
    for s in real_subs:
        doc = s["doctor"]
        doctor_order.append(doc)
        rows = []
        if s["first_patient_row"] and s["last_patient_row"]:
            for r in range(s["first_patient_row"], s["last_patient_row"] + 1):
                raw = grid[r - 1] if r - 1 < len(grid) else []
                rows.append(((raw or []) + [""] * 8)[:8])
        subs_by_doctor[doc] = rows

    # chart_no → (doctor, row_data) reverse lookup
    chart_loc: dict[str, str] = {}
    for doc, rows in subs_by_doctor.items():
        for r in rows:
            ch = (r[1] or "").strip()
            if ch:
                chart_loc[ch] = doc

    new_by_chart: dict[str, dict] = {}
    for p in new_patients:
        ch = (p.get("chart_no") or "").strip()
        if ch:
            new_by_chart[ch] = p

    removed_done: list[str] = []
    added_done: list[dict] = []
    unattached_added: list[dict] = []
    auto_created_doctors: list[str] = []

    def _ensure_doctor(doc: str) -> bool:
        """Auto-create an empty sub-table slot for a doctor that doesn't yet
        have one. Returns True if a new entry was created."""
        if not doc or doc in subs_by_doctor:
            return False
        subs_by_doctor[doc] = []
        doctor_order.append(doc)
        auto_created_doctors.append(doc)
        return True

    # 1) Removed: drop from wherever they are
    for r in diff.get("removed", []):
        ch = r["chart_no"]
        doc = chart_loc.get(ch)
        if not doc:
            continue
        subs_by_doctor[doc] = [row for row in subs_by_doctor[doc]
                               if (row[1] or "").strip() != ch]
        chart_loc.pop(ch, None)
        removed_done.append(ch)

    # 2) Doctor changed: intentionally skipped — same chart_no rows are
    #    NEVER touched on a re-upload (2026-05-20 rule). The diff is still
    #    surfaced to the UI for information, but sub-table state stays put.

    # 3) Added: append to their A-L doctor's sub-table (auto-create if missing)
    for a in diff.get("added", []):
        ch = a["chart_no"]
        doc = a.get("doctor") or (new_by_chart.get(ch) or {}).get("doctor", "")
        name = a.get("name") or (new_by_chart.get(ch) or {}).get("name", "")
        if doc:
            _ensure_doctor(doc)
            subs_by_doctor[doc].append([name, ch, "", "", "", "", "", ""])
            chart_loc[ch] = doc
            added_done.append({"chart_no": ch, "name": name, "doctor": doc})
        else:
            unattached_added.append({"chart_no": ch, "name": name, "doctor": doc})

    # Build the rendered block and write it back
    start_row = real_subs[0]["title_row"]
    block: list[list[str]] = []
    for i, doc in enumerate(doctor_order):
        rows = subs_by_doctor.get(doc, [])
        block.append([f"{doc}（{len(rows)}人）", "", "", "", "", "", "", ""])
        block.append(SUB_HEADER)
        for row in rows:
            block.append(row)
        if i < len(doctor_order) - 1:
            block.append([""] * 8)
            block.append([""] * 8)

    new_end = start_row + len(block) - 1
    old_last = real_subs[-1]
    old_end = (old_last["last_patient_row"]
               or old_last["subheader_row"]
               or old_last["title_row"])
    # Clear residual rows from the old sub-table area before writing
    if old_end > new_end:
        sheet_service.clear_range(ws, f"A{new_end + 1}:H{old_end}")
    sheet_service.write_range(ws, f"A{start_row}:H{new_end}", block, raw=False)
    # Re-apply F/G dropdown validation across the (possibly grown) sub-table area
    try:
        from . import emr_service
        f_opts, g_opts = emr_service.get_fg_options()
        sheet_service.set_fg_validation(ws, start_row, new_end + 100,
                                        f_opts, g_opts)
    except Exception:
        pass

    return {
        "updated": True,
        "range": f"A{start_row}:H{new_end}",
        "removed": removed_done,
        "moved":   [],            # doctor_changed intentionally not applied
        "added":   added_done,
        "unattached_added":   unattached_added,
        "unattached_changed": [],
        "auto_created_doctors": auto_created_doctors,
    }
