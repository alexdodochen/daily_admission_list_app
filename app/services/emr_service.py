"""
Step 3 — EMR extraction (no-summary).

Per `feedback_no_emr_summary.md` (5/10), the LLM-based 4-section summary
feature is fully retired. EMR processing now produces:

  - Raw SOAP text, truncated at [Medicine] / [Plan : 依類別] / 藥品 / 檢驗
    blocks (so药/lab/registration data doesn't pollute downstream views).
  - Age/gender/name from EMR `#divUserSpec` for cross-correction against
    main A-L (rule: EMR demographics are canonical, screenshot is +1).
  - Auto-detected F (術前診斷) / G (預計心導管) from keyword rules
    (`DIAG_RULES` / `CATH_RULES` + F→G default fallback).

Sub-table writeback (caller's responsibility, not this module):
  C col = "<age> y/o <gender>\\n" + truncated raw EMR
  D col = placeholder (never written)
  F col = auto-detected 術前診斷
  G col = auto-detected 預計心導管

Playwright orchestration: user manually logs in to EMR, copies the
session URL (`http://hisweb.hosp.ncku/Emrquery/(S(...))/EQ.aspx`), pastes
into the UI. We drive Playwright with that URL so the session cookie is
already valid (per `feedback_emr_manual_login`).
"""
from __future__ import annotations

import re
from datetime import date as _date


# ---------------------------- diagnosis / cath rules ----------------------------
# Source of truth: process_emr.py in daily-admission-list-public.
# Order matters — specific > broad.

DIAG_RULES: list[tuple[list[str], str]] = [
    (["STEMI", "ST elevation myocardial"], "STEMI"),
    (["NSTEMI", "non-ST elevation", "non ST elevation"], "Others:NSTEMI"),
    (["unstable angina"], "Unstable"),
    (["severe AS", "aortic stenosis"], "AS"),
    (["severe AR", "aortic regurgitation"], "AR"),
    (["severe MR", "mitral regurgitation", "MVRepair", "MVR"], "MR"),
    (["severe TR", "tricuspid regurgitation"], "Others:Severe TR"),
    (["generator replacement", "PPM generator", "ICD generator"], "Generator replacement"),
    (["paroxysmal Af", "paroxysmal atrial fibrillation",
      "Long persistent atrial fibrillation", "persistent Af",
      "persistent atrial fibrillation", "pAf"], "pAf"),
    (["supraventricular tachycardia", "PSVT"], "PSVT"),
    (["WPW"], "WPW syndrome"),
    (["atrial flutter", "Aflutter"], "Atrial flutter"),
    (["ventricular premature", "VPC"], "VPC"),
    (["sick sinus", "sinus nodal dysfunction", "sinus pause",
      "tachy-brady", "SSS"], "Sinus nodal dysfunction"),
    (["complete AV block", "AV nodal dysfunction", "CAVB", "AV block"], "AV nodal dysfunction"),
    (["PAOD", "peripheral arterial occlusive", "peripheral arterial disease"], "PAOD"),
    (["carotid stenting", "carotid stenosis"], "Carotid stenting"),
    (["HFrEF", "HFpEF", "heart failure", "CHF", "congestive heart failure"], "CHF"),
    (["dilated cardiomyopathy", "DCM"], "DCM"),
    (["hypertrophic cardiomyopathy", "HCM"], "HCM"),
    (["pulmonary hypertension", "pulmonary HTN"], "Pulmonary HTN"),
    (["syncope"], "Syncope"),
    (["angina pectoris", "angina"], "Angina pectoris"),
    (["CAD", "coronary artery disease",
      "chest pain", "chest tightness", "chest tigthness",
      "ACS", "acute coronary syndrome",
      "I259", "I250", "I251",
      "TET (+)", "TMT (+)", "THL (+)", "TET+", "TMT+", "THL+"], "CAD"),
]

CATH_RULES: list[tuple[list[str], str]] = [
    (["CRT-D", "CRT-P", "CRT upgrade", "cardiac resynchronization"], "CRT"),
    (["TAVI", "transcatheter aortic valve"], "TAVI"),
    (["plan PCI", "plan for PCI", "arrange PCI", "PCI for",
      "primary PCI", "→PCI", "→ PCI", "PCI ", "intervention"], "PCI"),
    (["RF ablation", "RFA", "ablation"], "RF ablation"),
    (["PPM", "pacemaker implant"], "PPM"),
    (["EP study"], "EP study"),
    (["PTA"], "PTA"),
    (["carotid angiography", "carotid stenting"], "Carotid angiography + stenting"),
    (["both-sided cath", "BHC"], "Both-sided cath."),
    (["right heart cath", "RHC"], "Right heart cath."),
    (["myocardial biopsy", "EMB"], "Myocardial biopsy"),
    (["cath study", "catheterization", "Cath on", "cath on", "CAG", "LHC"], "Left heart cath."),
]

F_TO_G_DEFAULT: dict[str, str] = {
    "CAD": "Left heart cath.",
    "Angina pectoris": "Left heart cath.",
    "Unstable": "Left heart cath.",
    "CHF": "Left heart cath.",
    "STEMI": "PCI",
    "Others:NSTEMI": "PCI",
    "s/p PCI": "Left heart cath.",
    "PAOD": "PTA",
    "pAf": "RF ablation",
    "PSVT": "RF ablation",
    "WPW syndrome": "RF ablation",
    "Atrial flutter": "RF ablation",
    "VPC": "RF ablation",
    "Sinus nodal dysfunction": "PPM",
    "AV nodal dysfunction": "PPM",
    "Generator replacement": "PPM",
    "AS": "Both-sided cath.", "AR": "Both-sided cath.", "MR": "Both-sided cath.",
    "Others:Severe TR": "Both-sided cath.",
    "DCM": "Right heart cath.",
    "HCM": "Left heart cath.",
    "Pulmonary HTN": "Right heart cath.",
    "Carotid stenting": "Carotid angiography + stenting",
    "Syncope": "EP study",
}

ICD10_FALLBACK: list[tuple[tuple[str, ...], str]] = [
    ((r"I25[019]",), "CAD"),
    ((r"I21[0-9]",), "STEMI"),
    ((r"I50[0-9]",), "CHF"),
    ((r"I48[0-9]",), "pAf"),
    ((r"I47[0-9]",), "PSVT"),
    ((r"I49[5]",), "Sinus nodal dysfunction"),
    ((r"I44[12]",), "AV nodal dysfunction"),
    ((r"I35[0]",), "AS"),
    ((r"I35[1]",), "AR"),
    ((r"I34[0]",), "MR"),
    ((r"I70[2]",), "PAOD"),
]

NO_RECORD_TEXT = "無本院一年內主治醫師門診紀錄"


# ---------------------------- text truncation ----------------------------

TRUNCATE_MARKERS = [
    "[Medicine]",
    "[Plan : 依類別]",
    "-------藥品-------",
    "-------檢驗-------",
    "-------其他-------",
]


def truncate_emr(text: str) -> str:
    """Cut off at the first medicine/lab marker so药/lab/registration
    data doesn't pollute downstream views."""
    if not text:
        return ""
    earliest = len(text)
    for m in TRUNCATE_MARKERS:
        i = text.find(m)
        if i != -1 and i < earliest:
            earliest = i
    return text[:earliest].rstrip()


# ---------------------------- divUserSpec parsing ----------------------------

def parse_name_from_raw(raw: str) -> str:
    """`姓名 : 謝秀嬌 , 生日 : 1955/02/20 , ...` → `謝秀嬌`."""
    if not raw:
        return ""
    m = re.search(r"姓名\s*[：:]\s*([^\s,，]+)", raw)
    return m.group(1).strip() if m else ""


def parse_birth_from_raw(raw: str) -> tuple[int, int, int] | None:
    if not raw:
        return None
    m = re.search(r"生日\s*[：:]\s*(\d{4})/(\d{1,2})/(\d{1,2})", raw)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def parse_gender_from_raw(raw: str) -> str:
    if not raw:
        return ""
    m = re.search(r"性別\s*[：:]\s*([男女])", raw)
    return m.group(1) if m else ""


def compute_age(birth: tuple[int, int, int] | None, admission_date: str) -> int | None:
    """`admission_date` is YYYYMMDD or YYYY-MM-DD. Returns age at that date."""
    if not birth or not admission_date:
        return None
    s = admission_date.replace("-", "").replace("/", "")
    if len(s) != 8 or not s.isdigit():
        return None
    ay, am, ad = int(s[:4]), int(s[4:6]), int(s[6:])
    by, bm, bd = birth
    age = ay - by
    if (am, ad) < (bm, bd):
        age -= 1
    return age


# ---------------------------- F/G detection ----------------------------

def _match_rules(text: str, rules: list[tuple[list[str], str]]) -> str:
    t = (text or "").lower()
    for keywords, value in rules:
        for kw in keywords:
            kl = kw.lower()
            if len(kw) <= 4:
                if re.search(r"(?<![a-zA-Z])" + re.escape(kl) + r"(?![a-zA-Z])", t):
                    return value
            else:
                if kl in t:
                    return value
    return ""


def _extract_dx_section(emr_text: str) -> str:
    """Return content under [Diagnosis] (up to next bracket section)."""
    parts = re.split(r"\[(Diagnosis|Subjective|Objective|Assessment & Plan)\]", emr_text)
    diag_text = ""
    for i, part in enumerate(parts):
        if part == "Diagnosis" and i + 1 < len(parts):
            diag_text = parts[i + 1]
            break
    if not diag_text:
        return ""
    out = []
    for line in diag_text.split("\n"):
        s = line.strip()
        if not s or s.startswith("Description"):
            continue
        s = re.sub(r"^\*?\s*\(Dx\)\s*", "", s)
        out.append(s)
    return "\n".join(out)


def _detect_via_icd(dx_text: str) -> str:
    codes = re.findall(r"ICD[\-‐-―]?10[^A-Z]{0,3}([A-Z]\d{2,4})", dx_text)
    if not codes:
        return ""
    joined = " ".join(codes)
    for patterns, value in ICD10_FALLBACK:
        for p in patterns:
            if re.search(p, joined):
                return value
    return ""


def _clean_past_tense_pci(text: str) -> str:
    patterns = [
        r"s/p\s+PCI[^\n]*",
        r"post[\-\s]+PCI[^\n]*",
        r"status\s+post[^\n]*PCI[^\n]*",
        r"PCI\s+on\s+\d{4}[/\-]?\d{0,2}[/\-]?\d{0,2}",
        r"PCI\s+done[^\n]*",
        r"previous\s+PCI[^\n]*",
        r"history\s+of\s+PCI[^\n]*",
        r"old\s+PCI[^\n]*",
    ]
    for p in patterns:
        text = re.sub(p, " ", text, flags=re.IGNORECASE)
    return text


def detect_diag(dx_text: str) -> str:
    """Apply DIAG_RULES with numbered-item priority (1.X > 2.Y)."""
    if not dx_text:
        return ""
    text_no_icd = "\n".join(
        l for l in dx_text.split("\n") if not l.strip().startswith("* (ICD")
    )
    items = re.findall(r"(?:^|\n)\s*\d+\s*[\.\)]\s*([^\n]+)", text_no_icd)
    if items:
        for item in items:
            m = _match_rules(item, DIAG_RULES)
            if m:
                return m
    m = _match_rules(text_no_icd, DIAG_RULES)
    if m:
        return m
    return _detect_via_icd(dx_text)


def detect_fg(emr_text: str) -> tuple[str, str]:
    """
    Auto-detect (F=術前診斷, G=預計心導管) from raw EMR text.
    F = Dx-section keywords; G = plan-section keywords with F→G fallback.
    Plan-driven overrides (generator replacement) force F too.
    """
    if not emr_text:
        return "", ""
    dx = _extract_dx_section(emr_text)
    f_diag = detect_diag(dx) if dx else _match_rules(emr_text, DIAG_RULES)

    if "[Assessment & Plan]" in emr_text:
        plan_sec = emr_text.split("[Assessment & Plan]")[1][:1500]
    else:
        plan_sec = emr_text

    pl = plan_sec.lower()
    if any(k in pl for k in (
        "generator replacement", "ppm replacement", "icd replacement",
        "crt replacement", "change generator",
    )):
        f_diag = "Generator replacement"

    g_cath = _match_rules(_clean_past_tense_pci(plan_sec), CATH_RULES)
    if not g_cath and f_diag:
        g_cath = F_TO_G_DEFAULT.get(f_diag, "")
    return f_diag, g_cath


# ---------------------------- _normalize_diag (cathlab side) ----------------------------

def normalize_diag_for_cathlab(diag: str) -> str:
    """
    Cathlab keyin rule: angina / unstable angina → CAD. Other values pass through.
    Keeps cathlab's pdijson aligned with the typical CAD mapping users expect.
    """
    if not diag:
        return diag
    d = diag.lower()
    if "unstable" in d or "angina" in d:
        return "CAD"
    return diag


# ---------------------------- high-level patient processing ----------------------------

def process_patient(emr_text: str,
                    div_user_spec: str,
                    admission_date: str) -> dict:
    """
    Pure-logic transform of raw EMR + #divUserSpec for one patient.
    Returns:
      {
        'c_text': '<age> y/o <gender>\\n<truncated raw>',
        'f': str, 'g': str,
        'name': str | '',
        'age':  int | None,
        'gender': str | '',
        'has_record': bool,
      }
    """
    truncated = truncate_emr(emr_text)
    has_record = bool(truncated.strip())

    name = parse_name_from_raw(div_user_spec)
    gender = parse_gender_from_raw(div_user_spec)
    age = compute_age(parse_birth_from_raw(div_user_spec), admission_date)

    if has_record:
        f, g = detect_fg(truncated)
        body = truncated
    else:
        f, g = "", ""
        body = NO_RECORD_TEXT

    prefix = ""
    if age is not None and gender:
        prefix = f"{age} y/o {gender}\n"

    return {
        "c_text": prefix + body,
        "f": f,
        "g": g,
        "name": name,
        "age": age,
        "gender": gender,
        "has_record": has_record,
    }


# ---------------------------- Playwright orchestration ----------------------------

async def fetch_raw_html(page, session_url: str, chart_no: str) -> tuple[str, str]:
    """
    Load EMR, query by chart number, return (soap_text, divUserSpec_raw).
    `divUserSpec` is the always-populated patient header (name/DOB/gender) —
    available even if the chart has no clinic visit history.
    """
    await page.goto(session_url, wait_until="networkidle")
    try:
        await page.fill("input[name='chartno']", chart_no, timeout=3000)
        await page.press("input[name='chartno']", "Enter")
        await page.wait_for_load_state("networkidle")
    except Exception:
        pass

    soap = await page.evaluate("""
        () => {
            const blocks = document.querySelectorAll('div.small');
            if (!blocks.length) return document.body.innerText || '';
            return Array.from(blocks).map(b => b.innerText).join('\\n---\\n');
        }
    """)
    div_spec = await page.evaluate("""
        () => {
            const el = document.getElementById('divUserSpec');
            return el ? el.innerText : '';
        }
    """)
    return soap or "", div_spec or ""


async def extract_patients(session_url: str,
                           patients: list[dict],
                           admission_date: str = "") -> list[dict]:
    """
    For each {chart_no, name, doctor} fetch SOAP + divUserSpec, then auto-detect
    F/G + age/gender prefix. NO LLM summary.

    Returns per-patient: {chart_no, name, doctor, c_text, f, g,
                          emr_name, age, gender, has_record, error}.
    """
    from playwright.async_api import async_playwright

    results: list[dict] = []
    admit = admission_date or _date.today().strftime("%Y%m%d")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        try:
            for p in patients:
                try:
                    soap, div_spec = await fetch_raw_html(page, session_url, p["chart_no"])
                    info = process_patient(soap, div_spec, admit)
                    results.append({
                        **p,
                        "c_text": info["c_text"],
                        "f": info["f"],
                        "g": info["g"],
                        "emr_name": info["name"],
                        "age": info["age"],
                        "gender": info["gender"],
                        "has_record": info["has_record"],
                        "error": "",
                    })
                except Exception as e:
                    results.append({
                        **p,
                        "c_text": "", "f": "", "g": "",
                        "emr_name": "", "age": None, "gender": "",
                        "has_record": False,
                        "error": str(e),
                    })
        finally:
            await browser.close()
    return results


# ============================================================================
# Verify main A-L vs EMR #divUserSpec (5/12 race-fix flow)
# ============================================================================

def compare_demographics(sheet_row: dict,
                         emr_name: str,
                         emr_birth: tuple[int, int, int] | None,
                         emr_gender: str,
                         today_yyyymmdd: str) -> dict:
    """
    Pure-logic compare. Returns:
      {
        "patches": [(cell, new_value), ...],   # ready for batch_write_cells
        "diffs": ["name 'X'→'Y'", ...],         # human-readable
      }

    `sheet_row` must include: row (int), chart, sheet_name, sheet_gender, sheet_age.
    `today_yyyymmdd` lets tests pin the reference date.
    """
    patches: list[tuple[str, str]] = []
    diffs: list[str] = []
    ri = sheet_row["row"]

    sn = (sheet_row.get("sheet_name") or "").strip()
    sg = (sheet_row.get("sheet_gender") or "").strip()
    sa = (sheet_row.get("sheet_age") or "").strip()

    if emr_name and sn != emr_name:
        patches.append((f"F{ri}", emr_name))
        diffs.append(f"name {sn!r}→{emr_name!r}")
    if emr_gender and sg != emr_gender:
        patches.append((f"G{ri}", emr_gender))
        diffs.append(f"gender {sg!r}→{emr_gender!r}")

    age = compute_age(emr_birth, today_yyyymmdd) if emr_birth else None
    if age is not None and sa != str(age):
        patches.append((f"H{ri}", str(age)))
        diffs.append(f"age {sa!r}→{age}")

    return {"patches": patches, "diffs": diffs}


def parse_divuserspec(text: str) -> tuple[str, tuple[int, int, int] | None, str]:
    """Aggregate name + birth + gender extraction (returns triple)."""
    return (
        parse_name_from_raw(text),
        parse_birth_from_raw(text),
        parse_gender_from_raw(text),
    )


# --- Playwright orchestration (sentinel-stamping race-fix per 5/12 b3815f9) ---

async def _verify_query_and_read(page, chart: str) -> str:
    """
    Stamp leftFrame + divUserSpec with a sentinel, fire BTQuery, wait for
    divUserSpec to be refreshed (sentinel gone + has 姓名 marker).

    Root cause (5/12 incident): divUserSpec lives in a different frame and
    refreshes async after BTQuery click. Waiting only on leftFrame let the
    read return the PREVIOUS chart's divUserSpec — off-by-one corruption.
    """
    import asyncio
    import time
    sentinel = f"VERIFY-SENT-{chart}-{int(time.time() * 1000) % 1000000}"

    await page.evaluate(f"""() => {{
        for (let i = 0; i < window.frames.length; i++) {{
            try {{
                const el = window.frames[i].document.querySelector('#divUserSpec');
                if (el) el.innerText = '{sentinel}';
            }} catch(e) {{}}
        }}
        try {{ window.frames['leftFrame'].document.body.innerHTML = '<!--{sentinel}-->'; }} catch(e) {{}}
    }}""")
    await page.evaluate(f"""() => {{
        const d = window.frames['topFrame'].document;
        const inp = d.getElementById('txtChartNo');
        inp.value = '{chart}';
        d.getElementById('BTQuery').click();
    }}""")
    for _ in range(30):
        await asyncio.sleep(0.5)
        st = await page.evaluate(f"""() => {{
            for (let i = 0; i < window.frames.length; i++) {{
                try {{
                    const el = window.frames[i].document.querySelector('#divUserSpec');
                    if (!el) continue;
                    const t = el.innerText || '';
                    if (t.indexOf('{sentinel}') >= 0) return 'stamped';
                    if (t.indexOf('姓名') >= 0) return 'ready';
                }} catch(e) {{}}
            }}
            return 'wait';
        }}""")
        if st == "ready":
            break
    await asyncio.sleep(0.4)
    return await page.evaluate(f"""() => {{
        for (let i = 0; i < window.frames.length; i++) {{
            try {{
                const el = window.frames[i].document.querySelector('#divUserSpec');
                if (!el) continue;
                const t = (el.innerText || '').trim();
                if (t && t.indexOf('{sentinel}') < 0 && t.indexOf('姓名') >= 0) return t;
            }} catch(e) {{}}
        }}
        return '';
    }}""")


async def verify_main_emr(session_url: str, sheet_rows: list[dict],
                          today_yyyymmdd: str) -> dict:
    """
    For each `sheet_row` ({row, chart, sheet_name, sheet_gender, sheet_age}),
    query EMR by chart, parse divUserSpec, diff vs sheet. Returns:

      {
        "patches": [(cell, new_value), ...],
        "diffs":   ["[chart] row N: ...", ...],
        "skipped": [{"chart", "reason"}],
        "ok":      [chart, ...],
      }

    Caller is expected to apply patches via batch_write_cells. Playwright
    failures (session expired, etc.) raise; per-chart failures are recorded
    in `skipped`.
    """
    from playwright.async_api import async_playwright

    patches: list[tuple[str, str]] = []
    diffs: list[str] = []
    skipped: list[dict] = []
    ok: list[str] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        try:
            await page.goto(session_url, wait_until="domcontentloaded", timeout=15000)
            valid = await page.evaluate("""() => {
                try {
                    const d = window.frames['topFrame'].document;
                    return !!d.getElementById('txtChartNo');
                } catch(e) { return false; }
            }""")
            if not valid:
                raise RuntimeError("EMR session URL invalid or expired (no txtChartNo)")

            for r in sheet_rows:
                chart = r["chart"]
                try:
                    div = await _verify_query_and_read(page, chart)
                except Exception as e:
                    skipped.append({"chart": chart, "reason": f"query failed: {e}"})
                    continue
                name, birth, gender = parse_divuserspec(div)
                if not (name and birth and gender):
                    skipped.append({"chart": chart, "reason": "divUserSpec empty"})
                    continue
                cmp = compare_demographics(r, name, birth, gender, today_yyyymmdd)
                if cmp["patches"]:
                    patches.extend(cmp["patches"])
                    diffs.append(f"[{chart}] row {r['row']}: " + ", ".join(cmp["diffs"]))
                else:
                    ok.append(chart)
        finally:
            await browser.close()

    return {"patches": patches, "diffs": diffs, "skipped": skipped, "ok": ok}
