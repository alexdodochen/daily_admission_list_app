"""
Step 5 — WEBCVIS 導管排程：驗證 + 規劃 + keyin（完整版）

本地版三個操作：
  - verify(admit_date): 跨比對子表格 vs WEBCVIS 排程，找出漏排/誤排
  - plan(admit_date):   列出該入院日的 keyin 計畫（時段 / 時間 / 房間 / 診斷 ID）
  - keyin(admit_date):  實際 ADD + UPT（Phase 1 新增、Phase 2 補 pdijson/phcjson）

規則來源：CLAUDE.md 第 1-9、17-18 條 + memory/feedback_cathlab_*。
靜態對應表放在 app/data/static/（id_maps, doctor_codes, schedule）。
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .. import config as appconfig
from . import sheet_service
from . import emr_service


# 註記內含以下任一關鍵字 → 該病人從 Step 5 keyin 排程剔除。
# 「不排」用前綴匹配（規避 false positive「不排除」見下方 _SKIP_NEGATIVE）。
# UI placeholder 寫「不排導管 / 待會診…」所以這裡必須涵蓋 不排導管 / 不排程 / 不排 cath。
SKIP_KEYWORDS = ["不排", "不做", "取消", "檢查"]
# 帶有以下 substring 時，即使匹配上 SKIP_KEYWORDS 也視為 false positive，不剔除。
# 例：「不排除做導管」≠「不排」。
_SKIP_NEGATIVE = ["不排除"]


def note_means_skip(note: str) -> bool:
    """True iff 註記 contains a skip keyword AND no negating phrase."""
    if not note:
        return False
    if any(neg in note for neg in _SKIP_NEGATIVE):
        return False
    return any(k in note for k in SKIP_KEYWORDS)
ZHANG_BORROWED_BY = ["王思翰", "張倉惟"]  # 借用張獻元時段時的註記關鍵字

# 第二主治醫師短碼 → 全名（用於從註記抽取 attendingdoctor2）
# 順序代表優先度；CLAUDE.md 規則 15：多人時葉立浩 > 其他
SECOND_DOCTORS: list[tuple[str, str]] = [
    ("浩", "葉立浩"),
    ("寬", "葉建寬"),
    ("晨", "洪晨惠"),
    ("嘉", "蘇奕嘉"),
    ("軨", "許毓軨"),
]

# Mon-cathlab + EP-family procedure → second forced to 洪晨惠 (CLAUDE.md rule 15,
# feedback_monday_ep_hong_chenhui_second.md, 5/8 broadened rule). Existing second
# from 時段表 gets pushed to recommendationDoctor (third doctor field).
EP_PROCEDURE_KEYWORDS = [
    "RF ablation", "RFA", "ablation",
    "PFA", "AF ablation", "AFL ablation", "PSVT ablation",
    "EP study",
    "PPM", "pacemaker", "ICD implant", "ICD generator",
    "CRT", "generator replacement",
]

# 陳則瑋 special: when sub-table C col contains 門診 entry by 劉秉彥, push him
# as second (memory feedback_chen_zewei_liu_bingyan_second.md). Limited to 劉秉彥.
CHEN_ZEWEI_OPD_DOCTOR = "陳則瑋"
LIU_BINGYAN_NAME = "劉秉彥"

# 'Others:XXX' fallback PDI (feedback_others_diag_freetext.md, 2026-04-27).
# When DIAG_IDS lacks an 'Others:foo' entry, use the parent Others PDI with the
# full freetext preserved as the name (verified for 'Others:opd', 'Others:s/p HTx').
OTHERS_PDI = "PDI20090908120008"

# The 3 cathlab lookup tables. Kept .gitignore'd (PHI: doctor / chart-no
# maps must not hit the public repo), so the public CI release CANNOT bundle
# them. They are resolved at runtime, mirroring the service-account drop-in
# decouple (config._detect_sa, commit 4acbcb8): a recipient of the public
# build drops the 3 JSONs into DATA_DIR/cathlab_static and they survive
# every auto-update. A local Path-B build bundles them via packaging.spec
# (datas += app/data/static) and they resolve from APP_ROOT/data/static.
_STATIC_FILES = ("cathlab_id_maps.json", "doctor_codes.json", "cathlab_schedule.json")
_PRIMARY = _STATIC_FILES[0]

# Legacy default (= APP_ROOT/data/static in practice); kept for any external
# reference. Real resolution goes through _resolve_static_dir().
STATIC_DIR = Path(__file__).resolve().parent.parent / "data" / "static"

_static_dir: Optional[Path] = None
_id_maps: Optional[dict] = None
_doctor_codes: Optional[dict] = None
_schedule: Optional[dict] = None
_schedule_overlay: Optional[dict] = None  # 主治醫師導管時段表 → second/third overlay


# ---------------------------------- static loaders ----------------------------------

def _has_static(d: Path) -> bool:
    try:
        return (d / _PRIMARY).is_file()
    except Exception:
        return False


def _migrate_into(persistent: Path, src_dir: Path) -> bool:
    """Copy the 3 JSONs from src_dir into the persistent dir so they survive
    every auto-update. Returns True if the persistent dir ends up complete."""
    try:
        persistent.mkdir(parents=True, exist_ok=True)
        for fn in _STATIC_FILES:
            src = src_dir / fn
            if src.is_file():
                (persistent / fn).write_bytes(src.read_bytes())
        return _has_static(persistent)
    except Exception:
        return False


def _resolve_static_dir() -> Path:
    """
    Find the dir holding the 3 cathlab JSONs. Priority:
      1. DATA_DIR/cathlab_static   — persistent drop-in, survives auto-update
      2. DATA_DIR (loose)          — same folder as service_account.json;
         the one drop spot the settings page tells users about. Migrated
         into (1) on hit.
      3. <exe>/cathlab_static, <exe>/static, <exe>  — intuitive frozen drop
         spots; on hit, migrate the files into (1) so updates keep them
      4. APP_ROOT/data/static      — bundled by Path-B local build / dev tree
      5. STATIC_DIR (legacy)       — last resort
    Returns the first dir that actually contains cathlab_id_maps.json; if
    none do, returns the persistent dir so the error message points the user
    at where to drop the files.
    """
    persistent = appconfig.DATA_DIR / "cathlab_static"
    if _has_static(persistent):
        return persistent

    # Loose drop directly into DATA_DIR (next to service_account.json) —
    # the single folder users already know from the settings page.
    if _has_static(appconfig.DATA_DIR):
        if _migrate_into(persistent, appconfig.DATA_DIR):
            return persistent
        return appconfig.DATA_DIR

    import sys
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        for cand in (exe_dir / "cathlab_static", exe_dir / "static", exe_dir):
            if _has_static(cand):
                if _migrate_into(persistent, cand):
                    return persistent
                return cand

    bundled = appconfig.APP_ROOT / "data" / "static"
    if _has_static(bundled):
        return bundled
    if _has_static(STATIC_DIR):
        return STATIC_DIR
    return persistent


def _load_json(name: str) -> dict:
    global _static_dir
    if _static_dir is None:
        _static_dir = _resolve_static_dir()
    path = _static_dir / name
    if not path.is_file():
        raise FileNotFoundError(
            f"找不到導管設定檔 {name}。請把這 3 個檔 "
            f"（{', '.join(_STATIC_FILES)}）放到跟 service_account.json "
            f"同一個資料夾：{appconfig.DATA_DIR}（放完按設定頁的測試連線即可，"
            f"不用重開 app）。"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def reset_cache() -> None:
    """Drop cached static-dir + parsed tables so the next access re-resolves.
    Call after the user drops the 3 JSONs without restarting (mirrors the
    service-account drop-in: files may appear AFTER first load)."""
    global _static_dir, _id_maps, _doctor_codes, _schedule, _schedule_overlay
    _static_dir = None
    _id_maps = None
    _doctor_codes = None
    _schedule = None
    _schedule_overlay = None


def cathlab_static_status() -> dict:
    """For the settings page / diagnostics: are the 3 JSONs available?"""
    d = _resolve_static_dir()
    return {
        "present": _has_static(d),
        "source": str(d),
        # Same folder as service_account.json — one place to remember.
        "drop_dir": str(appconfig.DATA_DIR),
        "files": list(_STATIC_FILES),
    }


def id_maps() -> dict:
    global _id_maps
    if _id_maps is None:
        _id_maps = _load_json("cathlab_id_maps.json")
    return _id_maps


def doctor_codes() -> dict:
    global _doctor_codes
    if _doctor_codes is None:
        _doctor_codes = _load_json("doctor_codes.json")
    return _doctor_codes


def schedule() -> dict:
    global _schedule
    if _schedule is None:
        _schedule = _load_json("cathlab_schedule.json")
    return _schedule


# ---------------------------------- 主治醫師導管時段表 overlay ----------------------------------
# Source-repo parity: read 主治醫師導管時段表 from the admission Sheet to derive
# per-(doctor × weekday) default second / third attending doctors. Source ref:
# `每日入院名單 Claude/schedule_lookup.py`.
#
# Sheet layout (matches source):
#   Cols  B=room (H1/H2/C1/C2)  C=Mon  D=Tue  E=Wed  F=Thu  G=Fri
#   Rows  2-7  = AM (H1 spans 2-4, H2 r5, C1 r6, C2 r7)
#         8-12 = PM (H1 spans 8-9, H2 r10, C1 r11, C2 r12)
#
# Cell format examples:
#   "陳柏升"          → primary=陳柏升, no second/third
#   "詹世鴻(軨)"      → primary=詹世鴻, second=許毓軨
#   "黃鼎鈞(浩、晨)"  → primary=黃鼎鈞, second=葉立浩, third=洪晨惠
#   "EP(李柏增)(晨)"  → primary=EP, tags=[李柏增,晨]
#   "(陳則瑋)"        → secondary listing, no primary (ignored for primary lookup)
#
# Abbreviations resolved via SECOND_DOCTORS (浩/寬/晨/嘉/軨); full names also accepted.

_SCHEDULE_WS_NAME = "主治醫師導管時段表"
_SCHEDULE_WEEKDAY_COL_OFFSET = {0: 2, 1: 3, 2: 4, 3: 5, 4: 6}  # 0-indexed column in A1:G15 grid (A=0..G=6); weekday 0=Mon → col C → idx 2
_SCHEDULE_SLOT_ROWS = [
    (1, "AM", "H1"), (4, "AM", "H2"), (5, "AM", "C1"), (6, "AM", "C2"),
    (7, "PM", "H1"), (9, "PM", "H2"), (10, "PM", "C1"), (11, "PM", "C2"),
]  # 0-indexed row in A1:G15 grid; rows 2-12 in 1-indexed → 1-11 in 0-indexed
_SCHEDULE_CONT_ROWS = {2: 1, 3: 1, 8: 7}  # 0-indexed continuation rows belong to their primary slot row above
_ABBREV_TO_FULL = dict(SECOND_DOCTORS)  # ("浩", "葉立浩") → {"浩": "葉立浩", ...}


def _parse_schedule_cell(text: str) -> Optional[dict]:
    """Parse a 主治醫師導管時段表 cell. Returns {name, tags: [str]} or None if empty/continuation."""
    if not text or not text.strip():
        return None
    raw = text.strip()
    # name = everything before the first '('
    m = re.match(r"^([^()]+)?(.*)$", raw)
    name = (m.group(1) or "").strip() if m else raw
    rest = m.group(2) if m else ""
    tags: list[str] = []
    for grp in re.findall(r"\(([^()]+)\)", rest):
        for sub in re.split(r"[、,，]", grp):
            sub = sub.strip()
            if sub:
                tags.append(sub)
    if not name:
        return None  # continuation row like "(陳則瑋)" — no primary
    return {"name": name, "tags": tags}


def _resolve_tag_to_doctor(tag: str) -> str:
    """Map abbreviation or full name to canonical doctor name. '' if unresolved."""
    if not tag:
        return ""
    if tag in _ABBREV_TO_FULL:
        return _ABBREV_TO_FULL[tag]
    # Full name?
    try:
        codes = doctor_codes()
        if tag in codes.get("DOCTOR_CODES", codes):  # support both raw {name:code} and {"DOCTOR_CODES":{...}}
            return tag
    except Exception:
        pass
    return ""


def _build_schedule_overlay_from_grid(grid: list[list[str]]) -> dict:
    """Pure helper — parse a 主治醫師導管時段表 grid into the overlay dict.

    Returns: {doctor: {wd_str: {"second": str, "third": str}}}.
    `wd_str` = "0".."4" to match cathlab_schedule.json convention.
    """
    overlay: dict[str, dict[str, dict[str, str]]] = {}
    for wd_int, col_idx in _SCHEDULE_WEEKDAY_COL_OFFSET.items():
        wd_str = str(wd_int)
        for row_idx, _session, _room in _SCHEDULE_SLOT_ROWS:
            cont_rows = [r for r, parent in _SCHEDULE_CONT_ROWS.items() if parent == row_idx]
            for r in [row_idx] + cont_rows:
                if r >= len(grid):
                    continue
                row = grid[r]
                if col_idx >= len(row):
                    continue
                cell = _parse_schedule_cell(row[col_idx])
                if not cell:
                    continue
                doctor = cell["name"]
                resolved_tags = [_resolve_tag_to_doctor(t) for t in cell["tags"]]
                resolved_tags = [d for d in resolved_tags if d]
                if not resolved_tags:
                    continue
                slot_info = {"second": resolved_tags[0]}
                if len(resolved_tags) >= 2:
                    slot_info["third"] = resolved_tags[1]
                # First match per (doctor, weekday) wins — multi-slot doctors get
                # one default; note-based override still applies per-patient.
                overlay.setdefault(doctor, {}).setdefault(wd_str, slot_info)
    return overlay


def read_schedule_overlay() -> dict:
    """Cached read of 主治醫師導管時段表 → second/third overlay dict.

    Lazy: skipped (returns {}) if worksheet is missing or any read fails. The
    user maintains this sheet; if it isn't present, fall back to note-based
    second-doctor extraction.
    """
    global _schedule_overlay
    if _schedule_overlay is not None:
        return _schedule_overlay
    try:
        from . import sheet_service  # local import — avoid hard dep at import time
        ws = sheet_service.get_worksheet(_SCHEDULE_WS_NAME)
        if ws is None:
            _schedule_overlay = {}
            return _schedule_overlay
        grid = sheet_service.read_range(ws, "A1:G15")
        _schedule_overlay = _build_schedule_overlay_from_grid(grid)
    except Exception:
        _schedule_overlay = {}
    return _schedule_overlay


def lookup_schedule_doctors(doctor: str, cath_date_str: str) -> dict:
    """Return {"second": str, "third": str} for a (doctor, cath_date). Empty strings if missing."""
    try:
        wd = str(datetime.strptime(cath_date_str, "%Y/%m/%d").weekday())
    except ValueError:
        return {"second": "", "third": ""}
    info = read_schedule_overlay().get(doctor, {}).get(wd, {})
    return {"second": info.get("second", ""), "third": info.get("third", "")}


# ---------------------------------- cath date rule ----------------------------------

def get_cathlab_date(admit_date: str, doctor: str, note: str) -> str:
    """
    入院日 -> 導管日：
    - 週五入院 → 同日（週六無排程）
    - 張獻元週二入院 + 註記不含 王思翰/張倉惟 → 同日 PM（他週二自己時段）
    - 其他 → N+1
    """
    dt = datetime.strptime(admit_date, "%Y%m%d")
    wd = dt.weekday()
    if wd == 4:  # Friday
        cath = dt
    elif doctor == "張獻元" and wd == 1 and not any(k in note for k in ZHANG_BORROWED_BY):
        cath = dt
    else:
        cath = dt + timedelta(days=1)
    return cath.strftime("%Y/%m/%d")


# ---------------------------------- id / slot resolvers ----------------------------------

def _resolve_id(text: str, table: dict) -> tuple[str, str]:
    """
    Try exact, then suffix-after-">", then substring; return (resolved_label, id) or ("", "").
    """
    if not text:
        return "", ""
    t = text.strip()
    if t in table:
        return t, table[t]
    # "EP study/RFA > pAf" → try "pAf"
    if ">" in t:
        tail = t.rsplit(">", 1)[1].strip()
        if tail in table:
            return tail, table[tail]
    # substring (longest label that appears in t wins)
    best = ""
    for k in table:
        if k and k in t and len(k) > len(best):
            best = k
    if best:
        return best, table[best]
    return "", ""


def resolve_diag(text: str) -> tuple[str, str]:
    """
    Resolve 術前診斷 → (label, id). Applies _normalize_diag first
    (angina/unstable → CAD per feedback_diag_angina_false_positive.md). Any
    non-empty text that can't be matched to a known id falls back to OTHERS_PDI
    so user-typed custom diagnoses always make it to WEBCVIS — the cathlab
    keyin then picks "OTHERS" in the dropdown and types the label as free text.
    """
    norm = emr_service.normalize_diag_for_cathlab(text)
    label, idv = _resolve_id(norm, id_maps().get("diag", {}))
    if idv:
        return label, idv
    if norm.strip():
        # Preserve `Others:` prefix if user used it; otherwise add it so the
        # WEBCVIS keyin layer can distinguish "this is a free-text OTHERS"
        # from a known label.
        out_label = norm if norm.startswith("Others:") else f"Others:{norm}"
        return out_label, OTHERS_PDI
    return "", ""


def resolve_proc(text: str) -> tuple[str, str]:
    return _resolve_id(text, id_maps().get("proc", {}))


# ---------------------------------- Mon-EP / OPD rules ----------------------------------

def _is_monday_cath(cath_date_str: str) -> bool:
    try:
        return datetime.strptime(cath_date_str, "%Y/%m/%d").weekday() == 0
    except ValueError:
        return False


def _is_ep_procedure(proc_text: str) -> bool:
    if not proc_text:
        return False
    t = proc_text.lower()
    return any(kw.lower() in t for kw in EP_PROCEDURE_KEYWORDS)


def _opd_doctor_in_emr(doctor: str, emr_c_text: str) -> str:
    """
    陳則瑋 patient whose sub-table C col mentions 劉秉彥 in a 門診 line →
    returns '劉秉彥'. Otherwise ''.
    """
    if doctor != CHEN_ZEWEI_OPD_DOCTOR or not emr_c_text:
        return ""
    for line in emr_c_text.split("\n"):
        if "門診" in line and LIU_BINGYAN_NAME in line:
            return LIU_BINGYAN_NAME
    return ""


def compute_all_slots(doctor: str, cath_date_str: str) -> list[dict]:
    """
    Returns list of all scheduled slots for `doctor` on `cath_date_str`.
    Each slot = {session: AM|PM, room: H1/H2/C1/C2}. Empty list if none.
    """
    try:
        dt = datetime.strptime(cath_date_str, "%Y/%m/%d")
    except ValueError:
        return []
    wd = str(dt.weekday())   # 0..4
    info = schedule().get("doctors", {}).get(doctor, {})
    entries = info.get(wd)
    if not entries:
        return []
    # Back-compat: accept dict (single slot) as well as list
    if isinstance(entries, dict):
        entries = [entries]
    return list(entries)


def compute_slot(doctor: str, cath_date_str: str, prefer_session: str = "") -> dict:
    """
    Returns {session, room, in_schedule}. OFF → 非時段（H1, 2100+）.
    If doctor has multiple slots same day, `prefer_session` ('AM'/'PM') picks
    one; otherwise returns the first (AM-before-PM in our schedule).
    """
    slots = compute_all_slots(doctor, cath_date_str)
    if not slots:
        return {"session": "OFF", "room": "H1", "in_schedule": False}
    if prefer_session:
        for s in slots:
            if s["session"] == prefer_session:
                return {"session": s["session"], "room": s["room"], "in_schedule": True}
    s = slots[0]
    return {"session": s["session"], "room": s["room"], "in_schedule": True}


def compute_time(session: str, index: int) -> str:
    """AM starts 0600, PM starts 1800 (skip 1700 legacy), OFF starts 2100. +index minutes."""
    base = {"AM": 6 * 60, "PM": 18 * 60, "OFF": 21 * 60}.get(session, 21 * 60)
    minute = base + index
    return f"{minute // 60:02d}{minute % 60:02d}"


# ---------------------------------- patient reader ----------------------------------

def _read_v_markers(data: list[list[str]]) -> dict[str, str]:
    """N-V ordering 區塊的 V 欄（改期，YYYYMMDD）— 回傳 {病歷號: V值}.

    New 9-col layout: N=13, O=14, P=15, Q=16, R=17, S=18, T=19, U=20, V=21.
    """
    out = {}
    for row in data:
        if len(row) < 22:
            continue
        chart = (row[18] or "").strip()   # S = index 18
        v     = (row[21] or "").strip()   # V = index 21
        if chart and v and v != "改期":
            out[chart] = v
    return out


def read_patients(date: str) -> list[dict]:
    """Scan date sheet 子表格 + V-column reschedule skips. Returns patient
    dicts with fields: seq, doctor, name, chart, diag, cath, note, emr, skip.

    Reschedule marker is now V (col idx 21 in N-V 9-col layout) — index by
    chart no via _read_v_markers."""
    ws = sheet_service.get_worksheet(date)
    if not ws:
        raise ValueError(f"找不到工作表：{date}")
    data = ws.get_all_values()
    reschedules = _read_v_markers(data)

    patients: list[dict] = []
    current_doctor = ""
    seq = 0
    for row in data:
        r = (row[:8] + [""] * 8)[:8]
        col_a = r[0].strip()

        if "人）" in col_a:
            current_doctor = col_a.split("（")[0].strip()
            continue
        if col_a == "姓名":
            continue
        if col_a and r[1].strip() and current_doctor:
            seq += 1
            # Strip the OCR "?" / "？" uncertainty mark so it never leaks
            # into the dry-run table or WEBCVIS keyin (same rule as Step 3).
            name = re.sub(r"[?？�⁇‽]+\s*$", "", col_a).strip()
            chart = r[1].strip()
            emr  = r[2]      # C col (EMR raw with age/gender prefix); keep newlines
            note = r[7].strip()
            diag = r[5].strip()
            cath = r[6].strip()
            v_mark = reschedules.get(chart, "")
            should_skip = note_means_skip(note) or bool(v_mark)
            if v_mark:
                note = (note + f" [改期→{v_mark}]").strip()
            patients.append({
                "seq": seq, "doctor": current_doctor,
                "name": name, "chart": chart, "emr": emr,
                "diag": diag, "cath": cath, "note": note,
                "skip": should_skip,
            })
    return patients


# ------------------------------ WEBCVIS queries ------------------------------

async def _login(page, cfg) -> None:
    base_host = cfg.cathlab_base_url.rsplit("/WEBCVIS", 1)[0] + "/WEBCVIS"
    await page.goto(base_host + "/")
    await page.wait_for_load_state("networkidle", timeout=15000)
    await page.fill('input[name="userid"]', cfg.cathlab_user)
    await page.fill('input[name="password"]', cfg.cathlab_pass)
    await page.click('input[type="submit"], button[type="submit"]')
    await page.wait_for_load_state("networkidle", timeout=10000)


async def _set_date_and_query(page, base_url: str, date_str: str) -> None:
    await page.goto(base_url)
    await page.wait_for_load_state("networkidle", timeout=10000)
    await asyncio.sleep(1)
    await page.evaluate(f"""() => {{
        let a = document.getElementById("daySelect1");
        let b = document.getElementById("daySelect2");
        if(a){{a.removeAttribute("readonly"); a.value = "{date_str}";}}
        if(b){{b.removeAttribute("readonly"); b.value = "{date_str}";}}
    }}""")
    await asyncio.sleep(0.3)
    await page.evaluate("""() => {
        if (document.HCO1WForm) {
            document.HCO1WForm.buttonName.name = "QRY";
            document.HCO1WForm.buttonName.value = "QRY";
            document.HCO1WForm.submit();
        }
    }""")
    await page.wait_for_load_state("networkidle", timeout=10000)
    await asyncio.sleep(1)


def _week_span(date_str: str) -> list[str]:
    """Return [Mon..Fri] dates (YYYY/MM/DD) for the ISO-week containing date_str.

    Week-scan rule (CLAUDE.md rule 19, feedback_cathlab_week_check_before_keyin.md):
    before any ADD, check the whole Mon-Fri window — if chart exists on ANY day,
    skip it (don't duplicate). Saturday/Sunday have no cathlab, so 5-day span.
    """
    try:
        dt = datetime.strptime(date_str, "%Y/%m/%d")
    except ValueError:
        return [date_str]
    monday = dt - timedelta(days=dt.weekday())
    return [(monday + timedelta(days=i)).strftime("%Y/%m/%d") for i in range(5)]


async def _get_existing_charts(page) -> set[str]:
    charts = await page.evaluate(r"""() => {
        let c = [];
        document.querySelectorAll("#row tr").forEach(r => {
            let el = r.querySelector("#hes_patno");
            if (el && el.value) c.push(el.value.trim());
        });
        if (c.length === 0) {
            document.querySelectorAll("#row td").forEach(td => {
                let t = td.textContent.trim();
                if (/^\d{7,8}$/.test(t)) c.push(t);
            });
        }
        return c;
    }""")
    return set(charts)


async def _login_and_query(dates: list[str]) -> dict[str, set[str]]:
    """Return {cath_date: set(chart_no)} using the user's WEBCVIS creds."""
    cfg = appconfig.load()
    if not cfg.cathlab_base_url or not cfg.cathlab_user or not cfg.cathlab_pass:
        raise RuntimeError("請先在設定頁填入 WEBCVIS URL / 帳號 / 密碼")

    from playwright.async_api import async_playwright

    results: dict[str, set[str]] = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=100)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await ctx.new_page()
        try:
            await _login(page, cfg)
            for d in dates:
                await _set_date_and_query(page, cfg.cathlab_base_url, d)
                results[d] = await _get_existing_charts(page)
        finally:
            await browser.close()
    return results


# --------------------------------- plan enrichment ---------------------------------

def _pick_second_doctor(note: str) -> tuple[str, str]:
    """
    From a patient's 備註 extract a single secondary-attending-doctor name
    (for attendingdoctor2). Returns (full_name, short_tag) or ("", "").
    Rule 16: when multiple present, 葉立浩 wins; others fall back to first-hit.
    """
    if not note:
        return "", ""
    hits: list[tuple[str, str]] = []
    for tag, full in SECOND_DOCTORS:
        if tag in note:
            hits.append((tag, full))
    if not hits:
        return "", ""
    # Priority: 葉立浩 first
    for tag, full in hits:
        if full == "葉立浩":
            return full, tag
    tag, full = hits[0]
    return full, tag


def _enrich(patients: list[dict], admit_date: str) -> list[dict]:
    """Attach cath_date / session / room / time / diag_id / proc_id / second_doctor / third_doctor to each patient.

    Second/third doctor priority (CLAUDE.md rule 15 + 5/8 broadening):
      1. Start with note-extracted second (葉立浩 wins on ties).
      2. 陳則瑋 + sub-table C 門診 by 劉秉彥 → second=劉秉彥 (overrides note).
      3. Mon cathlab + EP-family procedure → second forced to 洪晨惠; if a
         second was already set, push it to third (recommendationDoctor).
    """
    counters: dict[tuple[str, str], int] = {}
    for p in patients:
        if p["skip"]:
            p["cath_date"] = ""
            p["session"] = ""
            p["room"] = ""
            p["time"] = ""
            p["diag_id"] = ""
            p["diag_label"] = ""
            p["proc_id"] = ""
            p["proc_label"] = ""
            p["second_doctor"] = ""
            p["third_doctor"] = ""
            p["note_out"] = p["note"]
            continue
        cath = get_cathlab_date(admit_date, p["doctor"], p["note"])
        prefer = ""
        if any(k in p["note"] for k in ("下午", "PM", "pm", "晚")):
            prefer = "PM"
        elif any(k in p["note"] for k in ("上午", "AM", "am", "早")):
            prefer = "AM"
        if p["doctor"] == "張獻元" and datetime.strptime(admit_date, "%Y%m%d").weekday() == 1 \
                and cath == datetime.strptime(admit_date, "%Y%m%d").strftime("%Y/%m/%d"):
            prefer = "PM"
        slot = compute_slot(p["doctor"], cath, prefer_session=prefer)
        key = (cath, p["doctor"])
        idx = counters.get(key, 0)
        counters[key] = idx + 1
        time_s = compute_time(slot["session"], idx)
        d_label, d_id = resolve_diag(p["diag"])
        q_label, q_id = resolve_proc(p["cath"])
        note_out = p["note"]
        if not slot["in_schedule"] and "本日無時段" not in note_out:
            note_out = (note_out + " 本日無時段").strip()
        if p["cath"] and not q_id and p["cath"] not in note_out:
            note_out = (note_out + " " + p["cath"]).strip()

        # --- second/third doctor resolution ---
        # Priority (highest first):
        #   1. 備註 (note) — explicit user typing wins.
        #   2. 主治醫師導管時段表 overlay — per (doctor × weekday) default
        #      (e.g. 詹世鴻 週三 → 許毓軨; 黃鼎鈞 週四 → 葉立浩 / 洪晨惠).
        #   3. Other override rules below (陳則瑋 OPD, Mon+EP).
        sched = lookup_schedule_doctors(p["doctor"], cath)
        second, _tag = _pick_second_doctor(p["note"])
        if not second:
            second = sched["second"]
        third = sched["third"] if second != sched["third"] else ""

        # 陳則瑋 OPD by 劉秉彥 → second=劉秉彥
        opd_second = _opd_doctor_in_emr(p["doctor"], p.get("emr", ""))
        if opd_second:
            second = opd_second

        # Mon + EP-family → second forced to 洪晨惠, current second pushed to third
        if _is_monday_cath(cath) and _is_ep_procedure(p["cath"]):
            if second and second != "洪晨惠":
                third = second
            second = "洪晨惠"

        p["cath_date"] = cath
        p["session"] = slot["session"]
        p["room"] = slot["room"]
        p["time"] = time_s
        p["diag_id"] = d_id
        p["diag_label"] = d_label
        p["proc_id"] = q_id
        p["proc_label"] = q_label
        p["second_doctor"] = second
        p["third_doctor"] = third
        p["note_out"] = note_out
    return patients


# --------------------------------- high-level ---------------------------------

async def verify(admit_date: str, overrides: dict | None = None) -> dict:
    """Returns a report: per-patient OK / MISSING / SKIP.

    `overrides`: the user's manual edits from the dry-run (預覽排程) table —
    same shape as `keyin()` takes. Critically this carries the 「不排」 toggle
    so a patient the user un-checked in the preview is NOT cross-checked /
    counted as missing. (Field bug 2026-05-21 #6/#7: un-checking 不排 in step 1
    had no effect on step 2 對照.)
    """
    patients = _enrich(read_patients(admit_date), admit_date)
    _apply_overrides(patients, overrides)
    to_check = [p for p in patients if not p["skip"]]
    skipped  = [p for p in patients if p["skip"]]

    unique_dates = sorted({p["cath_date"] for p in to_check})
    webcvis = await _login_and_query(unique_dates) if unique_dates else {}

    found, missing = [], []
    for p in to_check:
        charts = webcvis.get(p["cath_date"], set())
        (found if p["chart"] in charts else missing).append(p)

    all_charts: set[str] = set()
    for s in webcvis.values():
        all_charts |= s

    return {
        "admit_date": admit_date,
        "dates_queried": unique_dates,
        "found":   found,
        "missing": missing,
        "skipped": [
            {**p, "unexpected_present": p["chart"] in all_charts}
            for p in skipped
        ],
        "totals": {
            "ok": len(found), "missing": len(missing), "skip": len(skipped),
        },
    }


def plan(admit_date: str) -> dict:
    """
    Dry-run: list what would be keyed in, grouped by cath_date.
    Safe to run anytime — reads sub-tables + static data only.
    """
    # Bust the schedule overlay cache so mid-session edits to 主治醫師導管時段表 take effect.
    global _schedule_overlay
    _schedule_overlay = None
    patients = _enrich(read_patients(admit_date), admit_date)
    buckets: dict[str, list[dict]] = {}
    for p in patients:
        if p["skip"]:
            continue
        buckets.setdefault(p["cath_date"], []).append(p)
    return {
        "admit_date": admit_date,
        "plan": buckets,
        "skipped": [p for p in patients if p["skip"]],
    }


# --------------------------------- keyin (real ADD + UPT) ---------------------------------

def _build_json(label: str, item_id: str) -> str:
    if not item_id:
        return ""
    return json.dumps([{"name": label, "id": item_id}], ensure_ascii=False)


async def _add_patient(page, base_url: str, cath_date: str, p: dict) -> dict:
    chart = p["chart"]
    codes = doctor_codes()
    doc_code = codes["doctors"].get(p["doctor"], "")
    room_code = codes["rooms"].get(p["room"], "")
    if not doc_code:
        return {"chart": chart, "name": p["name"], "result": "error",
                "reason": f"主治醫師代碼未知：{p['doctor']}"}
    if not room_code:
        return {"chart": chart, "name": p["name"], "result": "error",
                "reason": f"房間代碼未知：{p['room']}"}

    diag_json = _build_json(p["diag_label"], p["diag_id"])
    proc_json = _build_json(p["proc_label"], p["proc_id"])
    note = p.get("note_out") or ""

    try:
        await page.click('input[name="patno2"]')
        await asyncio.sleep(0.4)
        await page.fill('input[name="patno2"]', chart)
        await asyncio.sleep(0.3)
        await page.press('input[name="patno2"]', "Enter")
        await asyncio.sleep(2)

        await page.evaluate(f"""() => {{
            document.querySelector('input[name="inspectiondate"]').value = "{cath_date}";
        }}""")
        await page.fill('input[name="inspectiontime"]', p["time"])
        await page.select_option('select[name="examroom"]', value=room_code)
        await page.select_option('select[name="attendingdoctor1"]', value=doc_code)
        # Second attending (CLAUDE.md rule 15): 葉立浩 priority > first-hit
        second_name = p.get("second_doctor", "")
        second_code = codes["doctors"].get(second_name, "") if second_name else ""
        if second_code:
            try:
                await page.select_option('select[name="attendingdoctor2"]', value=second_code)
            except Exception:
                pass  # field may not be present on this form variant

        # Third attending / recommendationDoctor (Mon-EP push rule, feedback_cathlab_third_doctor.md)
        third_name = p.get("third_doctor", "")
        third_code = codes["doctors"].get(third_name, "") if third_name else ""
        if third_code:
            try:
                await page.select_option('select[name="recommendationDoctor"]', value=third_code)
            except Exception:
                pass

        await page.evaluate(
            """([dj, pj]) => {
                if (dj) document.querySelector('[name="pdijson"]').value = dj;
                if (pj) document.querySelector('[name="phcjson"]').value = pj;
            }""",
            [diag_json, proc_json],
        )

        if note:
            await page.fill('input[name="note"]', note)

        await asyncio.sleep(0.3)
        await page.evaluate("""() => {
            document.HCO1WForm.buttonName.name = "ADD";
            document.HCO1WForm.buttonName.value = "ADD";
            document.HCO1WForm.submit();
        }""")
        await page.wait_for_load_state("networkidle", timeout=15000)
        await asyncio.sleep(1)
        return {"chart": chart, "name": p["name"], "result": "ok"}
    except Exception as e:
        return {"chart": chart, "name": p["name"], "result": "error", "reason": str(e)}


async def _upt_patient(page, p: dict) -> dict:
    """Re-open the row by chart and force pdijson/phcjson via UPT."""
    chart = p["chart"]
    if not (p["diag_id"] or p["proc_id"]):
        return {"chart": chart, "name": p["name"], "result": "skip",
                "reason": "no id to fix"}
    diag_json = _build_json(p["diag_label"], p["diag_id"])
    proc_json = _build_json(p["proc_label"], p["proc_id"])

    found = await page.evaluate(
        """(chart) => {
            let rows = document.querySelectorAll("#row tr");
            for (let row of rows) {
                let el = row.querySelector("#hes_patno");
                if (el && el.value === chart) { row.click(); return true; }
            }
            return false;
        }""",
        chart,
    )
    if not found:
        return {"chart": chart, "name": p["name"], "result": "error",
                "reason": "row not found on page"}

    await asyncio.sleep(0.5)
    await page.evaluate(
        """([dj, pj, dt, pt]) => {
            if (dj) {
                document.querySelector('[name="pdijson"]').value = dj;
                let f = document.querySelector('[name="prediagnosisitem"]');
                if (f) f.value = dt;
            }
            if (pj) {
                document.querySelector('[name="phcjson"]').value = pj;
                let f = document.querySelector('[name="preheartcatheter"]');
                if (f) f.value = pt;
            }
        }""",
        [diag_json, proc_json, p["diag_label"], p["proc_label"]],
    )
    await asyncio.sleep(0.3)
    await page.evaluate("""() => {
        document.HCO1WForm.buttonName.name = "UPT";
        document.HCO1WForm.buttonName.value = "UPT";
        document.HCO1WForm.submit();
    }""")
    await page.wait_for_load_state("networkidle", timeout=15000)
    await asyncio.sleep(1)
    return {"chart": chart, "name": p["name"], "result": "ok"}


def _apply_overrides(patients: list[dict], overrides: dict | None) -> None:
    """Apply user's manual dry-run edits (keyed by chart no) onto the enriched
    plan, in place. Only whitelisted fields — diag/proc IDs stay computed.
    session='非時段'/'OFF' → in_schedule False (cosmetic; ADD uses room/time/note).
    skip=True / 'true' → patient flipped to skipped (no WEBCVIS write).
    cath_date='YYYY/MM/DD' → manual reschedule of which day this patient
    lands on (e.g. user wants 病人 X delayed two days).
    """
    if not overrides:
        return
    allowed = ("second_doctor", "third_doctor", "note_out",
               "room", "time", "session", "cath_date")
    truthy = {"1", "true", "True", "yes", "on"}
    for p in patients:
        ov = overrides.get(p.get("chart", ""))
        if not ov:
            continue
        for k in allowed:
            if k in ov and ov[k] is not None:
                p[k] = str(ov[k]).strip()
        sess = (ov.get("session") or "").strip()
        if sess in ("OFF", "非時段"):
            p["session"] = "OFF"
            p["in_schedule"] = False
        elif sess in ("AM", "PM"):
            p["in_schedule"] = True
        # Skip toggle — when the user unchecks 「排」 in the dry-run table.
        if "skip" in ov:
            v = ov["skip"]
            if isinstance(v, bool):
                p["skip"] = v
            else:
                p["skip"] = str(v).strip() in truthy


async def keyin(admit_date: str, dry_run: bool = False,
                overrides: dict | None = None,
                op_id: str = "") -> dict:
    """
    Real WEBCVIS ADD + UPT for all non-skipped patients.
    dry_run=True → returns the plan without launching a browser.
    overrides: {chart: {second_doctor, third_doctor, note_out, room, time,
    session}} — user's manual edits from the dry-run table, applied verbatim.
    `op_id`: cooperative cancel checkpoint (see cancel_registry). Polled
    between Phase 1 / Phase 2 / per-patient ADD / per-patient UPT. Mid-batch
    cancel stops the next iteration and returns partial results.
    """
    cfg = appconfig.load()
    if not dry_run:
        if not cfg.cathlab_base_url or not cfg.cathlab_user or not cfg.cathlab_pass:
            raise RuntimeError("請先在設定頁填入 WEBCVIS URL / 帳號 / 密碼")

    # Bust the schedule overlay cache so mid-session edits to 主治醫師導管時段表 take effect.
    global _schedule_overlay
    _schedule_overlay = None
    patients = _enrich(read_patients(admit_date), admit_date)
    _apply_overrides(patients, overrides)
    active = [p for p in patients if not p["skip"]]
    skipped = [p for p in patients if p["skip"]]

    if dry_run or not active:
        return {
            "admit_date": admit_date,
            "dry_run": True,
            "would_add": active,
            "skipped": skipped,
        }

    from playwright.async_api import async_playwright
    from . import cancel_registry

    log: list[str] = []
    add_results: list[dict] = []
    upt_results: list[dict] = []
    canceled = False

    def _cancel_check() -> bool:
        nonlocal canceled
        if op_id and cancel_registry.is_canceled(op_id):
            canceled = True
            log.append("⚠ 使用者取消")
            return True
        return False

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, slow_mo=150)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await ctx.new_page()
        try:
            await _login(page, cfg)
            log.append("登入成功")

            unique_dates = sorted({p["cath_date"] for p in active})
            # Week-scan (rule 19): scan Mon-Fri of each ISO week touching any
            # cath_date so we can skip charts already on ANOTHER day.
            scan_dates: set[str] = set()
            for d in unique_dates:
                scan_dates.update(_week_span(d))
            existing: dict[str, set[str]] = {}
            for d in sorted(scan_dates):
                await _set_date_and_query(page, cfg.cathlab_base_url, d)
                existing[d] = await _get_existing_charts(page)
                log.append(f"查詢 {d}：現有 {len(existing[d])} 筆")

            def _existing_anywhere(chart: str) -> str:
                """Return cath_date string where chart already exists in scan window, or ''."""
                for d, charts in existing.items():
                    if chart in charts:
                        return d
                return ""

            # Phase 1: ADD (skip if chart present on ANY day in the scan window)
            log.append("--- Phase 1: ADD ---")
            for i, p in enumerate(active):
                if _cancel_check():
                    break
                d = p["cath_date"]
                already = _existing_anywhere(p["chart"])
                if already:
                    reason = f"already exists on {already}" if already != d else "already exists"
                    add_results.append({"chart": p["chart"], "name": p["name"],
                                        "result": "skip", "reason": reason})
                    continue
                if i > 0:
                    await _set_date_and_query(page, cfg.cathlab_base_url, d)
                r = await _add_patient(page, cfg.cathlab_base_url, d, p)
                add_results.append(r)

            # Phase 2: UPT (pdijson / phcjson)
            if not canceled:
                log.append("--- Phase 2: UPT ---")
                for p in active:
                    if _cancel_check():
                        break
                    if not (p["diag_id"] or p["proc_id"]):
                        continue
                    await _set_date_and_query(page, cfg.cathlab_base_url, p["cath_date"])
                    r = await _upt_patient(page, p)
                    upt_results.append(r)

            # Final verification (skipped on cancel — partial state isn't comparable)
            final: dict[str, set[str]] = {}
            if not canceled:
                for d in unique_dates:
                    await _set_date_and_query(page, cfg.cathlab_base_url, d)
                    final[d] = await _get_existing_charts(page)
        finally:
            await browser.close()

    summary = {
        "ok": sum(1 for r in add_results if r["result"] == "ok"),
        "skip": sum(1 for r in add_results if r["result"] == "skip"),
        "error": sum(1 for r in add_results if r["result"] == "error"),
    }
    # Pair each missing patient with the matching Phase-1 add_results row so
    # the UI can show WHY they aren't in the schedule, not just "沒寫進去".
    add_by_chart = {r["chart"]: r for r in add_results}
    missing_after: list[dict] = []
    for p in active:
        if p["chart"] in final.get(p["cath_date"], set()):
            continue
        add = add_by_chart.get(p["chart"], {})
        result = add.get("result") or ""
        reason = (add.get("reason") or "").strip()
        if result == "error":
            explanation = reason or "建立排程時失敗（請看詳細執行記錄）"
        elif result == "skip":
            # "already exists on YYYY-MM-DD" — patient is on a different day
            explanation = (f"WEBCVIS 已有這位（{reason}），未在 {p['cath_date']} 新增"
                           if reason else "WEBCVIS 已有這位，未在目標日新增")
        elif result == "ok":
            explanation = "Phase 1 顯示新增成功，但複查時找不到 → 可能 WEBCVIS 介面回退 / 同分鐘衝堂；建議手動核對"
        else:
            # Patient was in `active` but never reached Phase 1 (defensive)
            explanation = "未進入建立排程流程（請看詳細執行記錄）"
        missing_after.append({
            "chart": p["chart"], "name": p["name"],
            "cath_date": p["cath_date"],
            "phase1_result": result or "unknown",
            "reason": explanation,
        })

    return {
        "admit_date": admit_date,
        "add": add_results,
        "upt": upt_results,
        "summary": summary,
        "missing_after": missing_after,
        "skipped": skipped,
        "log": log,
        "implemented": True,
        "canceled": canceled,
    }


