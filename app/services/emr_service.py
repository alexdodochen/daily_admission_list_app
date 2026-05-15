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

# DIAG_RULES — ported from daily-admission-list-public@4f7b53e (2026-05-15).
# Order matters. Key changes vs prior local version:
#   * NSTEMI checked BEFORE STEMI ('non ST elevation' contains 'ST elevation')
#   * Dropped 'ST elevation myocardial' from STEMI keywords (use abbrev only)
#   * CAD family moved UP above soft comorbidities (Unstable / Angina / Syncope)
#     — when CAD keyword appears in a Dx item, human picks CAD regardless of
#     co-mentioned Unstable/Angina/CHF/Syncope/VPC. See _SOFT_COMORBID_F override
#     in detect_diag().
DIAG_RULES: list[tuple[list[str], str]] = [
    (["NSTEMI", "non-ST elevation", "non ST elevation"], "Others:NSTEMI"),
    (["STEMI"], "STEMI"),
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
    (["CAD", "coronary artery disease",
      "chest pain", "chest tightness", "chest tigthness",
      "ACS", "acute coronary syndrome",
      "I259", "I250", "I251",
      "TET (+)", "TMT (+)", "THL (+)", "TET+", "TMT+", "THL+"], "CAD"),
    # Soft comorbidities — only fire when CAD is absent. detect_diag() applies
    # the override (CAD keyword anywhere → CAD wins).
    (["unstable angina"], "Unstable"),
    (["angina pectoris", "angina"], "Angina pectoris"),
    (["syncope"], "Syncope"),
]

def get_fg_options() -> tuple[list[str], list[str]]:
    """F/G option lists. Reads the user-maintained 下拉選單 worksheet first;
    falls back to DIAG_RULES/CATH_RULES outputs if Sheet is unreachable.

    Used by /api/options/fg, the Sheet data-validation builder, and the
    in-app combobox.
    """
    from . import sheet_service
    try:
        sheet_opts = sheet_service.read_fg_options_from_sheet()
    except Exception:
        sheet_opts = None
    if sheet_opts:
        return sheet_opts
    f = [out for _, out in DIAG_RULES]
    g = [out for _, out in CATH_RULES]
    if "s/p PCI" not in f:
        f.append("s/p PCI")
    if "Cover stent" not in g:
        g.append("Cover stent")
    return f, g


# CATH_RULES — Dx-fallback only (used when plan-section yields nothing).
# Plan-section detection uses PLAN_G_RULES below, which encodes the key 5/15
# insight: G is the cath-lab BOOKING slot, not the procedure outcome.
# `plan PCI` / `arrange PCI` / `TRA PCI` all book as Left heart cath., not PCI.
CATH_RULES: list[tuple[list[str], str]] = [
    (["CRT-D", "CRT-P", "CRT upgrade", "cardiac resynchronization"], "CRT"),
    (["TAVI", "transcatheter aortic valve"], "TAVI"),
    # PCI — narrowed (5/15): only forward-looking unambiguous triggers. Removed
    # bare "PCI " and "intervention" which fired on `s/p percutaneous coronary
    # intervention (PCI)` even after past-tense cleanup.
    (["plan PCI", "plan for PCI", "arrange PCI", "PCI for admission",
      "primary PCI", "→PCI", "→ PCI", "POBA", "rotablation"], "PCI"),
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
INPATIENT_ONLY_TEXT = "查無門診紀錄（病人僅有住院資料 / 需手動點開個別住院記錄）"

# Boilerplate phrases that surface when the EMR fetch lands on the chart-summary
# index page instead of a real 門診 SOAP. Common on inpatient-only charts where
# there's no 一年內門診紀錄 for the assigned doctor or FALLBACK_DOCTORS.
INDEX_PAGE_MARKERS = [
    "住院資料量較大",
    "請點選個別項目",
    "全部摺疊",
    "全部展開",
]


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


def is_index_page_boilerplate(text: str) -> bool:
    """True when `text` is the chart-summary index page (boilerplate only),
    not a real 門診 SOAP. We never want this stored as a clinical record —
    it's noise that pollutes Card 3 Step 3 / cathlab / LINE push.

    Triggers if any 2 of `INDEX_PAGE_MARKERS` appear (loose match, so a
    single-marker SOAP that genuinely quotes one of these phrases still
    passes through).
    """
    if not text:
        return False
    hits = sum(1 for m in INDEX_PAGE_MARKERS if m in text)
    return hits >= 2


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
    """Return primary diagnosis lines from the Dx block.

    Supports two EMR formats:
      A. `[Diagnosis] ... [Subjective]` section-marker form (older)
      B. `* (Dx)1. ... \n * (ICD-10：...)` numbered form (current Web EMR)
    Strips `* (Dx)` prefix so numbered items become parseable. Includes the
    ICD-10 block so detect_via_icd has codes to scan.
    """
    diag_text = ""

    # Format B (current Web EMR): `* (Dx)` numbered items until `* (ICD` block
    m_dx = re.search(r'\*\s*\(Dx\)(.*?)(?=\n\s*\*\s*\(ICD|\Z)', emr_text, flags=re.DOTALL)
    m_icd_block = re.search(r'((?:\n\s*\*\s*\(ICD[^\n]*\n?)+)', emr_text)
    if m_dx:
        diag_text = m_dx.group(1)
        if m_icd_block:
            diag_text = diag_text + "\n" + m_icd_block.group(1)

    # Format A fallback (legacy)
    if not diag_text:
        parts = re.split(r"\[(Diagnosis|Subjective|Objective|Assessment & Plan)\]", emr_text)
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
    """Strip historical PCI/ablation mentions so plan-section matching doesn't
    fire on `s/p PCI on 2020` etc.

    Patterns allow up to 200 chars between `s/p` and the keyword to catch
    expanded forms like `s/p percutaneous coronary intervention (PCI)`.
    Past-tense ablation patterns mirror PCI ones.
    """
    patterns = [
        # PCI past-tense
        r"s/p[^\n]{0,200}?PCI[^\n]*",
        r"post[\-\s][^\n]{0,200}?PCI[^\n]*",
        r"status\s+post[^\n]{0,200}?PCI[^\n]*",
        r"PCI\s+(?:on|in)\s+\d{4}[/\-]?\d{0,2}[/\-]?\d{0,2}",
        r"PCI\s+done[^\n]*",
        r"previous\s+PCI[^\n]*",
        r"history\s+of\s+PCI[^\n]*",
        r"old\s+PCI[^\n]*",
        # PCI by year-suffix even without s/p prefix
        r"PCI[^\n]{0,80}\[?\d{4}[/\-]\d{1,2}[/\-]?\d{0,2}\]?",
        # Ablation past-tense
        r"s/p[^\n]{0,200}?ablation[^\n]*",
        r"post[\-\s][^\n]{0,200}?ablation[^\n]*",
        r"status\s+post[^\n]{0,200}?ablation[^\n]*",
        r"previous\s+ablation[^\n]*",
        r"history\s+of\s+ablation[^\n]*",
        r"ablation[^\n]{0,40}\[?\d{4}[/\-]\d{1,2}[/\-]?\d{0,2}\]?",
    ]
    for p in patterns:
        text = re.sub(p, " ", text, flags=re.IGNORECASE)
    return text


# Soft comorbidities that get overridden to CAD when CAD keyword appears
# anywhere in Dx text (5/15 learning — cath-lab admission bias).
_SOFT_COMORBID_F = {"Unstable", "Angina pectoris", "Syncope", "VPC", "CHF"}
_CAD_HINT_RE = re.compile(
    r"\b(CAD|coronary\s+artery\s+disease)\b|\bI25[019]\b",
    re.IGNORECASE,
)


def _cad_anywhere(text: str) -> bool:
    return bool(_CAD_HINT_RE.search(text or ""))


def detect_diag(dx_text: str) -> str:
    """Apply DIAG_RULES with numbered-item priority + soft-comorbidity override.

    Numbered Dx (`2.CAD ... 4.pAf`) means item 2 > item 4, so iterate in order
    and take the first match.

    Soft-comorbidity override (5/15 learning): when first-matching F is
    Unstable / Angina pectoris / Syncope / VPC / CHF, but CAD keyword appears
    ANYWHERE in dx_text, return 'CAD' instead. Cath-lab admission bias.
    """
    if not dx_text:
        return ""
    text_no_icd = "\n".join(
        l for l in dx_text.split("\n") if not l.strip().startswith("* (ICD")
    )
    cad_present = _cad_anywhere(dx_text)  # full text including ICD codes

    items = re.findall(r"(?:^|\n)\s*\d+\s*[\.\)]\s*([^\n]+)", text_no_icd)
    if items:
        for item in items:
            m = _match_rules(item, DIAG_RULES)
            if m:
                if m in _SOFT_COMORBID_F and cad_present:
                    return "CAD"
                return m
    m = _match_rules(text_no_icd, DIAG_RULES)
    if m:
        if m in _SOFT_COMORBID_F and cad_present:
            return "CAD"
        return m
    return _detect_via_icd(dx_text)


# ---- Plan-section rules (5/15 learning) ----
# Attending writes admission reason + planned procedure at the bottom of the
# EMR. Plan signal beats Dx because Dx often has comorbidities while plan
# states the actual cath-lab booking reason.

PLAN_F_RULES: list[tuple[list[str], str]] = [
    # Arrhythmia ablation → specific F
    (["AFL ablation", "atrial flutter ablation",
      "typical flutter ablation", "atypical flutter ablation"], "Atrial flutter"),
    (["AF ablation", "Af ablation", "Afib ablation", "AFFERA",
      "PVI", "pulmonary vein isolation",
      "varipulse", "vari-pulse"], "pAf"),
    (["VPC ablation", "PVC ablation"], "VPC"),
    (["PSVT ablation", "SVT ablation"], "PSVT"),
    # Valve interventions
    (["TAVI", "transcatheter aortic valve"], "AS"),
    (["M-TEER", "MTEER", "MitraClip", "mitral TEER"], "MR"),
    # Generator replacement (also fires from Dx but plan override is reliable)
    (["generator replacement", "ppm replacement", "icd replacement",
      "crt replacement", "change generator"], "Generator replacement"),
]

PLAN_G_RULES: list[tuple[list[str], str]] = [
    # KEY 5/15 INSIGHT: G is the cath-lab BOOKING slot, not the procedure
    # outcome. Plan PCI / TRA PCI / arrange PCI all → "Left heart cath."
    # Only special bookings override: TAVI, CRT, ICD, M-TEER, LAAO, RF ablation,
    # Myocardial biopsy, PTA, PPM, RHC, BHC, Carotid stenting, EP study,
    # primary PCI (STEMI only).
    (["EVICD", "EVCID", "AICD", "ICD implant", "ICD implantation"], "ICD"),
    (["CRT-D", "CRT-P", "CRT upgrade", "cardiac resynchronization", "CRT implant"], "CRT"),
    (["TAVI", "transcatheter aortic valve"], "TAVI"),
    (["M-TEER", "MTEER", "MitraClip", "mitral TEER"], "M-TEER"),
    (["LAAO", "left atrial appendage occlusion", "Watchman"], "LAAO Occluder"),
    (["AFL ablation", "AF ablation", "Af ablation", "Afib ablation",
      "VPC ablation", "PVC ablation", "PSVT ablation", "SVT ablation",
      "VT ablation", "PVI", "pulmonary vein isolation",
      "varipulse", "vari-pulse", "AFFERA",
      "RF ablation", "RFA", "ablation"], "RF ablation"),
    (["EP study"], "EP study"),
    # Primary PCI for STEMI — only true PCI booking. Everything else → LHC.
    (["primary PCI"], "PCI"),
    (["PPM implant", "permanent pacemaker", "pacemaker implant", "PPM"], "PPM"),
    (["both-sided cath", "BHC"], "Both-sided cath."),
    (["right cath", "right heart cath", "RHC"], "Right heart cath."),
    (["myocardial biopsy", "EMB"], "Myocardial biopsy"),
    (["PTA"], "PTA"),
    (["carotid stenting", "carotid angiography"], "Carotid angiography + stenting"),
    # Generic cath — catches "TRA PCI" / "PCI for ..." / "POBA" / "stenting"
    (["cath study", "catheterization", "CAG", "LHC", "left heart cath",
      "cath on", "cath via", "PCI for", "PCI on", "TRA PCI", "TFA PCI",
      "POBA", "rotablation", "stenting", "plan PCI", "arrange PCI"], "Left heart cath."),
]

# When plan yields G but no F, derive F from G when unambiguous
PLAN_G_TO_F: dict[str, str] = {
    "PCI": "STEMI",
    "Left heart cath.": "CAD",
    "PTA": "PAOD",
    "TAVI": "AS",
    "M-TEER": "MR",
    "LAAO Occluder": "pAf",
    "CRT": "CHF",
    "Carotid angiography + stenting": "Carotid stenting",
}

_PROCEDURE_KEYWORDS_RE = re.compile(
    r"\b(?:PCI|POBA|stenting|rotablation|ablation|biopsy|EVICD|EVCID|AICD|ICD|PPM|"
    r"CRT|TAVI|LAAO|Watchman|M-TEER|MTEER|MitraClip|cath|CAG|LHC|RHC|PTA|"
    r"TEE|EMB|PVI|AFFERA|ANS|varipulse|vari-pulse|admission|adm)\b",
    re.IGNORECASE,
)
_ADMISSION_CUE_RE = re.compile(
    r"(?:\b(?:adm(?:ission)?|arrange|plan)\b"
    r"|^\s*\d{1,2}[/-]\d{1,2}\s)",
    re.IGNORECASE | re.MULTILINE,
)


def extract_plan_signal(emr_text: str) -> str:
    """Return admission-plan lines that carry the attending's intent.
    Bottom 60 lines, kept if they contain a procedure keyword OR admission cue.
    Empty result → fall back to Dx-based detection in detect_fg.
    """
    if not emr_text:
        return ""
    lines = emr_text.split("\n")
    tail = lines[-60:] if len(lines) > 60 else lines
    kept = []
    for line in tail:
        s = line.strip()
        if not s:
            continue
        if _PROCEDURE_KEYWORDS_RE.search(s) or _ADMISSION_CUE_RE.search(s):
            kept.append(s)
    return "\n".join(kept)


def detect_fg(emr_text: str) -> tuple[str, str]:
    """Detect (F, G) using PLAN section as primary signal (5/15 learning).

    Priority:
      1. Plan section (bottom of EMR) — attending's stated reason + procedure
      2. Dx section — fallback when plan is missing/unclear
      3. F→G default mapping — fallback for G when plan/Dx silent on procedure

    `clean_past_tense_pci` strips historical PCI/ablation mentions so they
    don't fire the procedure rules.
    """
    if not emr_text:
        return "", ""

    plan_signal = extract_plan_signal(emr_text)
    plan_clean = _clean_past_tense_pci(plan_signal) if plan_signal else ""

    # G from plan (booking slot — most special bookings override here)
    g_cath = _match_rules(plan_clean, PLAN_G_RULES) if plan_clean else ""
    # F from plan (specific arrhythmia / valve / generator overrides)
    f_diag = _match_rules(plan_clean, PLAN_F_RULES) if plan_clean else ""

    # Plan gave G but not F → derive
    if g_cath and not f_diag:
        f_diag = PLAN_G_TO_F.get(g_cath, "")

    # Fallback: Dx-based F if plan didn't classify F
    if not f_diag:
        dx = _extract_dx_section(emr_text)
        f_diag = detect_diag(dx) if dx else _match_rules(emr_text, DIAG_RULES)

    # Fallback: G from F default if plan didn't classify G
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
    # Boilerplate from the chart-summary index page → treat as no record so
    # downstream F/G detection + sub-table display don't get polluted.
    index_only = is_index_page_boilerplate(truncated)
    has_record = bool(truncated.strip()) and not index_only

    name = parse_name_from_raw(div_user_spec)
    gender = parse_gender_from_raw(div_user_spec)
    age = compute_age(parse_birth_from_raw(div_user_spec), admission_date)

    if has_record:
        f, g = detect_fg(truncated)
        body = truncated
    else:
        f, g = "", ""
        body = INPATIENT_ONLY_TEXT if index_only else NO_RECORD_TEXT

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


# ---------------------------- Sheet writeback ----------------------------

def write_results_to_subtables(date: str, results: list[dict]) -> dict:
    """Write per-patient EMR data back to the doctor sub-tables.

    For each result entry whose chart_no matches a sub-table row, patches:
      C col (col 3) = c_text         (age/gender prefix + truncated SOAP)
      F col (col 6) = f              (auto-detected 術前診斷)
      G col (col 7) = g              (auto-detected 預計心導管)

    Returns {"written": int, "missing": [chart_no, ...]}. Errors-only
    patients (where extract failed and c_text is empty) are skipped.
    """
    from . import sheet_service, ordering_service, subtable_service

    ws = sheet_service.get_worksheet(date)
    if ws is None:
        raise ValueError(f"找不到工作表 {date}")
    tables = ordering_service.read_doctor_subtables(date)
    auto_built = False

    # No sub-tables yet? Auto-build them from main A-L so Step 3 can land C/F/G
    # somewhere — otherwise every EMR result silently goes into `missing`.
    # build_subtables_from_main refuses to overwrite existing blocks, so this
    # is safe to call defensively.
    if not tables:
        try:
            subtable_service.build_subtables_from_main(date)
            auto_built = True
            tables = ordering_service.read_doctor_subtables(date)
        except Exception as e:
            return {"written": 0, "missing": [(r.get("chart_no") or "")
                                              for r in results],
                    "patches_count": 0,
                    "error": f"無子表格且自動建立失敗：{e}"}

    chart_to_row: dict[str, int] = {}
    for _, pts in tables.items():
        for p in pts:
            ch = (p.get("chart_no") or "").strip()
            if ch:
                chart_to_row[ch] = p["row"]

    patches: list[tuple[str, str]] = []
    missing: list[str] = []
    written = 0
    for r in results:
        chart = (r.get("chart_no") or "").strip()
        if not chart:
            continue
        if chart not in chart_to_row:
            missing.append(chart)
            continue
        if r.get("error"):
            continue
        row = chart_to_row[chart]
        c_text = r.get("c_text") or ""
        f_val  = r.get("f") or ""
        g_val  = r.get("g") or ""
        if c_text:
            patches.append((f"C{row}", c_text))
        if f_val:
            patches.append((f"F{row}", f_val))
        if g_val:
            patches.append((f"G{row}", g_val))
        written += 1

    # TEXT-format chart-no cols before any write so leading zeros stick (this
    # routine also writes column C which contains chart-no in c_text prefix on
    # the rare patient with all-digit names — defensive).
    try:
        sheet_service.ensure_chart_text_format(ws)
    except Exception:
        pass
    sheet_service.batch_write_cells(ws, patches)

    # Re-apply F/G data validation across the sub-table area each time we
    # write so newly-built blocks (auto_built) and any growth from diff path
    # both get the dropdown rule.
    try:
        first_row = min((p["row"] for _, pts in tables.items() for p in pts
                        if p.get("row")), default=0)
        if first_row:
            f_opts, g_opts = get_fg_options()
            sheet_service.set_fg_validation(ws, first_row, first_row + 500,
                                            f_opts, g_opts)
    except Exception:
        pass  # validation is cosmetic — never block writeback

    return {"written": written, "missing": missing,
            "patches_count": len(patches), "auto_built": auto_built}


def apply_emr_main_fixes(date: str, results: list[dict]) -> dict:
    """Auto-correct main A-L (F=姓名, G=性別, H=年齡) from EMR results.

    For each result whose chart_no matches a main row, write back any
    differing 姓名 / 性別 / 年齡. Returns:
      {"patches_count": N, "fixes": [{chart_no, field, old, new}, ...]}

    Empty/zero values from EMR are NOT overwritten back (avoids clearing a
    correct sheet value with a failed parse).
    """
    from . import sheet_service

    ws = sheet_service.get_worksheet(date)
    if ws is None:
        return {"patches_count": 0, "fixes": [], "skipped": True,
                "error": f"找不到工作表 {date}"}
    main = sheet_service.read_range(ws, "A2:L200")
    chart_to_main_row: dict[str, int] = {}
    main_by_row: dict[int, list[str]] = {}
    for i, r in enumerate(main):
        rr = (r + [""] * 12)[:12]
        ch = rr[8].strip()  # I = 病歷號
        if ch:
            chart_to_main_row[ch] = i + 2  # +2 because read started at row 2
            main_by_row[i + 2] = rr

    patches: list[tuple[str, str]] = []
    fixes: list[dict] = []
    for r in results:
        ch = (r.get("chart_no") or "").strip()
        if not ch or ch not in chart_to_main_row:
            continue
        if r.get("error"):
            continue
        row = chart_to_main_row[ch]
        ex = main_by_row[row]
        ex_name   = (ex[5] or "").strip()  # F
        ex_gender = (ex[6] or "").strip()  # G
        ex_age    = (ex[7] or "").strip()  # H
        new_name   = (r.get("emr_name") or "").strip()
        new_gender = (r.get("gender") or "").strip()
        age_val = r.get("age")
        new_age = str(age_val) if age_val is not None else ""

        if new_name and new_name != ex_name:
            patches.append((f"F{row}", new_name))
            fixes.append({"chart_no": ch, "field": "name",
                          "old": ex_name, "new": new_name})
        if new_gender and new_gender != ex_gender:
            patches.append((f"G{row}", new_gender))
            fixes.append({"chart_no": ch, "field": "gender",
                          "old": ex_gender, "new": new_gender})
        if new_age and new_age != ex_age:
            patches.append((f"H{row}", new_age))
            fixes.append({"chart_no": ch, "field": "age",
                          "old": ex_age, "new": new_age})

    if patches:
        sheet_service.batch_write_cells(ws, patches)
    return {"patches_count": len(patches), "fixes": fixes, "skipped": False}


# ---------------------------- Playwright orchestration ----------------------------

# Fallback doctors used when the assigned 主治醫師 has no 一年內門診紀錄 —
# port of FALLBACK_DOCTORS from daily-admission-list-public/fetch_emr.py.
FALLBACK_DOCTORS = ["劉秉彥", "趙庭興", "蔡惟全", "許志新", "陳柏升", "李貽恒"]

# Same-name characters that surface as Unicode siblings — fetch_emr.py treats
# them as equivalent so a query for one variant still hits anchors carrying
# the other. Ported from daily-admission-list reference impl.
NAME_ALIASES = {
    "林佳凌": ["林佳凌", "林佳淩"],
    "林佳淩": ["林佳凌", "林佳淩"],
}


def _name_variants(name: str) -> list[str]:
    return NAME_ALIASES.get(name, [name])


async def fetch_raw_html(page, session_url: str, chart_no: str,
                         doctor: str = "") -> tuple[str, str, str]:
    """
    NCKU-EMR frameset query. Returns (soap_text, divUserSpec_raw, visit_label).

    Ported from `每日入院名單 Claude\\fetch_emr.py` (private workflow repo —
    source of truth). Anti-race-condition design:

      1. Navigate to the session URL if we're not already on it (a long
         batch reuses one tab, so don't re-goto for every chart).
      2. Stamp `leftFrame` + `mainFrame` body with a per-chart sentinel.
      3. Inside `topFrame`: fill `#txtChartNo` + click `#BTQuery`.
      4. Poll leftFrame until sentinel is gone AND at least one 門診 anchor
         is present (max 12s) → only then is the visit tree loaded.
      5. Stamp mainFrame again, click the matching 門診 anchor (doctor first,
         then FALLBACK_DOCTORS).
      6. Poll mainFrame until sentinel is gone AND body has > 80 chars
         (max 12s).
      7. Read `div.small` blocks **from mainFrame only** (NOT iterating all
         frames — the leftFrame's chart-summary index also has div.small but
         it's just boilerplate). Filter out `iportlet-content` portlet wrappers.
      8. Read `#divUserSpec` from any frame as patient header.

    `visit_label` is the chosen clinic visit's anchor text.

    Returns ("", "", "") if no 門診 record found for this chart (e.g. inpatient-
    only patient with no 一年內門診紀錄 in any allowed doctor).
    """
    import json as _json
    import time as _time

    # Only navigate if we're not already on the EMR session — same page
    # gets reused across the patient batch.
    cur = page.url or ""
    if session_url not in cur and cur.split("?")[0] != session_url.split("?")[0]:
        await page.goto(session_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(1500)

    sentinel_q = f"FETCH-{chart_no}-{int(_time.time() * 1000)}-QUERY"
    sentinel_c = f"FETCH-{chart_no}-{int(_time.time() * 1000)}-CLICK"

    # 1. stamp leftFrame + mainFrame, then submit the query in topFrame.
    await page.evaluate(f"""() => {{
        try {{ window.frames['leftFrame'].document.body.innerHTML = '<!--{sentinel_q}-->'; }} catch(e) {{}}
        try {{ window.frames['mainFrame'].document.body.innerHTML = '<!--{sentinel_q}-->'; }} catch(e) {{}}
    }}""")

    submit = await page.evaluate(f"""() => {{
        try {{
            let d = window.frames['topFrame'].document;
            let inp = d.getElementById('txtChartNo');
            let btn = d.getElementById('BTQuery');
            if (inp && btn) {{
                inp.value = {chart_no!r};
                btn.click();
                return {{ok: true}};
            }}
        }} catch(e) {{}}
        // Fallback: walk every frame (handles non-standard layouts)
        const tryFrames = [window.top, ...Array.from(window.top.frames)];
        for (const w of tryFrames) {{
            try {{
                const d = w.document;
                const inp = d.getElementById('txtChartNo');
                const btn = d.getElementById('BTQuery');
                if (inp && btn) {{
                    inp.value = {chart_no!r};
                    btn.click();
                    return {{ok: true}};
                }}
            }} catch(e) {{}}
        }}
        return {{ok: false, reason: 'no_query_form'}};
    }}""")
    if not submit.get("ok"):
        return "", "", ""

    # 2. poll leftFrame for visit-tree readiness.
    left_ready = False
    for _ in range(24):  # 24 × 0.5s = 12s
        await page.wait_for_timeout(500)
        state = await page.evaluate(f"""() => {{
            try {{
                let d = window.frames['leftFrame'].document;
                let html = d.body.innerHTML || '';
                if (html.indexOf('{sentinel_q}') >= 0) return 'stamped';
                let links = d.querySelectorAll('a');
                let count = 0;
                for (let l of links) if ((l.innerText || '').includes('門診')) count++;
                return count > 0 ? 'ready' : 'empty';
            }} catch(e) {{ return 'err'; }}
        }}""")
        if state == "ready":
            left_ready = True
            break

    div_spec = await page.evaluate("""() => {
        for (let i = 0; i < window.frames.length; i++) {
            try {
                let el = window.frames[i].document.getElementById('divUserSpec');
                if (el && el.innerText.trim()) return el.innerText.trim();
            } catch(e) {}
        }
        return '';
    }""") or ""

    if not left_ready:
        return "", div_spec, ""

    # 3. click the 門診 anchor for `doctor` (and its alias variants), or
    # any FALLBACK_DOCTORS in priority order.
    variants_js = _json.dumps(_name_variants(doctor) if doctor else [], ensure_ascii=False)
    fallback_js = _json.dumps(FALLBACK_DOCTORS, ensure_ascii=False)

    await page.evaluate(f"""() => {{
        try {{ window.frames['mainFrame'].document.body.innerHTML = '<!--{sentinel_c}-->'; }} catch(e) {{}}
    }}""")
    click = await page.evaluate(f"""() => {{
        try {{
            let d = window.frames['leftFrame'].document;
            let links = d.querySelectorAll('a');
            let variants = {variants_js};
            for (let link of links) {{
                let t = (link.innerText || '').trim();
                if (!t.includes('門診')) continue;
                for (let v of variants) {{
                    if (t.includes(v)) {{
                        link.click();
                        return {{ok: true, visit: t, matched_doctor: true}};
                    }}
                }}
            }}
            let allow = {fallback_js};
            for (let fb of allow) {{
                for (let link of links) {{
                    let t = (link.innerText || '').trim();
                    if (t.includes('門診') && t.includes(fb)) {{
                        link.click();
                        return {{ok: true, visit: t, matched_doctor: false}};
                    }}
                }}
            }}
        }} catch(e) {{}}
        return {{ok: false}};
    }}""")

    if not click.get("ok"):
        return "", div_spec, ""

    visit_label = click.get("visit", "")

    # 4. poll mainFrame readiness.
    main_ready = False
    for _ in range(24):
        await page.wait_for_timeout(500)
        state = await page.evaluate(f"""() => {{
            try {{
                let d = window.frames['mainFrame'].document;
                let html = d.body.innerHTML || '';
                if (html.indexOf('{sentinel_c}') >= 0) return 'stamped';
                let txt = (d.body.innerText || '').trim();
                return txt.length > 80 ? 'ready' : 'short';
            }} catch(e) {{ return 'err'; }}
        }}""")
        if state == "ready":
            main_ready = True
            break

    if not main_ready:
        return "", div_spec, visit_label

    # 5. extract SOAP from mainFrame only — filter out the iportlet-content
    # wrapper div that appears at every page level.
    soap = await page.evaluate("""() => {
        try {
            let d = window.frames['mainFrame'].document;
            let divs = d.querySelectorAll('div.small');
            let texts = [];
            for (let div of divs) {
                let t = (div.innerText || '').trim();
                if (t && !t.includes('iportlet-content')) texts.push(t);
            }
            if (texts.length === 0) return (d.body.innerText || '').trim();
            return texts.join('\\n');
        } catch(e) { return ''; }
    }""") or ""

    return soap, div_spec, visit_label


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
                    soap, div_spec, visit = await fetch_raw_html(
                        page, session_url, p["chart_no"], p.get("doctor", ""))
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
                        "visit_label": visit,
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
