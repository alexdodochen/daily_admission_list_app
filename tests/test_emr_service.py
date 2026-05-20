"""Pure-logic tests for emr_service.

No LLM dependency — the 4-section summary feature is retired (5/10).
Tests cover truncation, divUserSpec parsing, F/G detection, and the
high-level `process_patient` aggregator.
"""
from __future__ import annotations

from app.services import emr_service as es


# --------------------- inpatient-only boilerplate (2026-05-15) ---------------------

def test_is_index_page_boilerplate_detects_typical_index():
    text = "住院資料量較大,請點選個別項目後瀏覽\n全部摺疊 | 全部展開\n執行時間 : 00:00:01.656s"
    assert es.is_index_page_boilerplate(text) is True


def test_is_index_page_boilerplate_passes_real_soap():
    text = "S: chest pain x 3 days\nO: BP 130/80\nA: rule out ACS\nP: admit for cath"
    assert es.is_index_page_boilerplate(text) is False


def test_is_index_page_boilerplate_handles_empty():
    assert es.is_index_page_boilerplate("") is False


def test_process_patient_inpatient_only_marks_no_record():
    """Boilerplate SOAP → has_record False + INPATIENT_ONLY_TEXT body."""
    boilerplate = "住院資料量較大,請點選個別項目後瀏覽\n全部摺疊 | 全部展開"
    info = es.process_patient(boilerplate, "", "20260515")
    assert info["has_record"] is False
    assert es.INPATIENT_ONLY_TEXT in info["c_text"]
    assert info["f"] == ""
    assert info["g"] == ""


# ---------------- truncation ----------------

def test_truncate_at_medicine():
    text = "Dx line\n[Assessment & Plan]\nplan\n[Medicine]\nDRUG_A 5 mg"
    out = es.truncate_emr(text)
    assert "plan" in out
    assert "DRUG_A" not in out


def test_truncate_at_chinese_drug_marker():
    text = "Dx info\n-------藥品-------\nDRUG_X"
    assert es.truncate_emr(text).rstrip() == "Dx info"


def test_truncate_returns_input_when_no_marker():
    assert es.truncate_emr("clean SOAP") == "clean SOAP"


def test_truncate_handles_empty():
    assert es.truncate_emr("") == ""


def test_truncate_picks_earliest_marker():
    text = "abc[Plan : 依類別]xxx[Medicine]yyy"
    assert es.truncate_emr(text).rstrip() == "abc"


# ---------------- divUserSpec ----------------

def test_parse_name_from_divuserspec():
    raw = "姓名 : 謝秀嬌 , 生日 : 1955/02/20 , 性別 : 女"
    assert es.parse_name_from_raw(raw) == "謝秀嬌"


def test_parse_name_missing():
    assert es.parse_name_from_raw("生日 : 2000/01/01") == ""


def test_parse_birth():
    raw = "姓名 : 王小明 , 生日 : 1960/05/15 , 性別 : 男"
    assert es.parse_birth_from_raw(raw) == (1960, 5, 15)


def test_parse_birth_missing():
    assert es.parse_birth_from_raw("姓名 : 王小明") is None


def test_parse_gender():
    assert es.parse_gender_from_raw("姓名 : x , 性別 : 男") == "男"
    assert es.parse_gender_from_raw("姓名 : x , 性別 : 女") == "女"
    assert es.parse_gender_from_raw("nothing") == ""


def test_compute_age_before_birthday():
    # Born 1960/05/15, admit 2026/03/01 → not yet 66
    assert es.compute_age((1960, 5, 15), "20260301") == 65


def test_compute_age_after_birthday():
    assert es.compute_age((1960, 5, 15), "20260601") == 66


def test_compute_age_on_birthday():
    assert es.compute_age((1960, 5, 15), "20260515") == 66


def test_compute_age_invalid_date():
    assert es.compute_age((1960, 5, 15), "not-a-date") is None


def test_compute_age_none_birth():
    assert es.compute_age(None, "20260101") is None


# ---------------- detect_fg ----------------

def test_detect_fg_cad_lhc():
    text = "[Diagnosis]\n1. CAD\n[Assessment & Plan]\nplan LHC"
    f, g = es.detect_fg(text)
    assert f == "CAD"
    assert g == "Left heart cath."


def test_detect_fg_stemi_pci():
    text = "[Diagnosis]\n1. STEMI\n[Assessment & Plan]\nprimary PCI"
    f, g = es.detect_fg(text)
    assert f == "STEMI"
    assert g == "PCI"


def test_detect_fg_paf_rfa():
    text = "[Diagnosis]\n1. pAf\n[Assessment & Plan]\nRF ablation"
    f, g = es.detect_fg(text)
    assert f == "pAf"
    assert g == "RF ablation"


def test_detect_fg_plan_pci_overrides_unstable_to_cad():
    """5/15 plan-section logic: 'plan PCI' → cath-lab books LHC → derives F=CAD,
    overriding Dx 'unstable angina' (which would have given F=Unstable)."""
    text = "[Diagnosis]\n1. unstable angina\n[Assessment & Plan]\nplan PCI"
    f, g = es.detect_fg(text)
    assert f == "CAD"  # PLAN_G_TO_F['Left heart cath.'] = CAD
    assert g == "Left heart cath."  # plan PCI → LHC booking, not PCI


def test_detect_fg_pure_unstable_no_plan_keeps_unstable():
    """Without a plan signal, Dx-only with bare 'unstable angina' → Unstable.
    (Soft-comorbid override only fires when CAD is also present in Dx.)"""
    text = "[Diagnosis]\n1. unstable angina\n[Assessment & Plan]\nfollow up"
    f, _ = es.detect_fg(text)
    assert f == "Unstable"


def test_detect_fg_unstable_with_cad_dx_overrides_to_cad():
    """Soft-comorbidity CAD override (5/15): unstable + CAD in Dx → CAD."""
    text = "[Diagnosis]\n1. unstable angina, CAD - 2VD\n[Assessment & Plan]\nfollow up"
    f, _ = es.detect_fg(text)
    assert f == "CAD"


def test_detect_fg_tavi_plan_overrides_to_AS():
    """Plan TAVI → G=TAVI + F=AS via PLAN_G_TO_F."""
    text = "[Diagnosis]\n1. severe AS\n[Assessment & Plan]\narrange TAVI"
    f, g = es.detect_fg(text)
    assert f == "AS"
    assert g == "TAVI"


def test_detect_fg_primary_pci_for_stemi():
    text = "[Diagnosis]\n1. STEMI\n[Assessment & Plan]\nprimary PCI"
    f, g = es.detect_fg(text)
    assert f == "STEMI"
    assert g == "PCI"


def test_detect_fg_af_ablation_plan_overrides_to_paf():
    """Plan AF ablation → G=RF ablation + F=pAf via PLAN_F_RULES."""
    text = "[Diagnosis]\n1. paroxysmal Af\n[Assessment & Plan]\nplan AF ablation with PVI"
    f, g = es.detect_fg(text)
    assert f == "pAf"
    assert g == "RF ablation"


def test_detect_fg_expanded_past_pci_doesnt_fire():
    """Expanded `s/p percutaneous coronary intervention (PCI)` must be cleaned."""
    text = ("[Diagnosis]\n1. CAD, s/p percutaneous coronary intervention (PCI) on 2020/05\n"
            "[Assessment & Plan]\nfollow OPD")
    _, g = es.detect_fg(text)
    # Past PCI cleaned; no plan signal; F=CAD via Dx; G=F_TO_G_DEFAULT[CAD]=LHC
    assert g == "Left heart cath."


def test_detect_fg_numbered_priority():
    """Item 1 wins over item 2."""
    text = "[Diagnosis]\n1. CAD\n2. pAf\n[Assessment & Plan]\nplan"
    f, _ = es.detect_fg(text)
    assert f == "CAD"


def test_detect_fg_f_to_g_fallback():
    """G empty in plan but F=CAD → G falls back to Left heart cath."""
    text = "[Diagnosis]\n1. CAD\n[Assessment & Plan]\nwait for OPD"
    f, g = es.detect_fg(text)
    assert f == "CAD"
    assert g == "Left heart cath."


def test_detect_fg_past_pci_doesnt_fire():
    """s/p PCI from 2020 must NOT trigger CATH=PCI."""
    text = "[Diagnosis]\n1. CAD\n[Assessment & Plan]\ns/p PCI on 2020/05"
    _, g = es.detect_fg(text)
    assert g == "Left heart cath."  # F→G fallback, not PCI


def test_detect_fg_generator_replacement_override():
    text = "[Diagnosis]\n1. pAf\n[Assessment & Plan]\nplan PPM generator replacement"
    f, g = es.detect_fg(text)
    assert f == "Generator replacement"
    assert g == "PPM"


def test_detect_fg_icd_fallback():
    """Empty Dx free text, ICD-10 code carries the diagnosis."""
    text = "[Diagnosis]\n* (ICD-10:I259) chronic CAD\n[Assessment & Plan]\nplan"
    f, _ = es.detect_fg(text)
    assert f == "CAD"


def test_detect_fg_empty():
    assert es.detect_fg("") == ("", "")


# ---------------- normalize_diag_for_cathlab ----------------

def test_normalize_diag_angina_to_cad():
    assert es.normalize_diag_for_cathlab("Angina pectoris") == "CAD"


def test_normalize_diag_unstable_to_cad():
    assert es.normalize_diag_for_cathlab("Unstable") == "CAD"


def test_normalize_diag_pass_through():
    assert es.normalize_diag_for_cathlab("CAD") == "CAD"
    assert es.normalize_diag_for_cathlab("pAf") == "pAf"


def test_normalize_diag_empty():
    assert es.normalize_diag_for_cathlab("") == ""


# ---------------- process_patient ----------------

def test_process_patient_full_fields():
    soap = "[Diagnosis]\n1. CAD\n[Assessment & Plan]\nplan LHC\n[Medicine]\nDRUG"
    div = "姓名 : 王小明 , 生日 : 1960/05/15 , 性別 : 男"
    out = es.process_patient(soap, div, "20260601")
    assert out["name"] == "王小明"
    assert out["age"] == 66
    assert out["gender"] == "男"
    assert out["f"] == "CAD"
    assert out["g"] == "Left heart cath."
    assert out["has_record"] is True
    assert out["c_text"].startswith("66 y/o 男\n")
    assert "DRUG" not in out["c_text"]


def test_process_patient_no_record():
    """No SOAP → NO_RECORD_TEXT placeholder, but demographics still parsed."""
    div = "姓名 : 林大姊 , 生日 : 1950/01/01 , 性別 : 女"
    out = es.process_patient("", div, "20260101")
    assert out["has_record"] is False
    assert out["f"] == ""
    assert out["g"] == ""
    assert es.NO_RECORD_TEXT in out["c_text"]
    assert out["c_text"].startswith("76 y/o 女\n")  # demographic prefix kept


def test_process_patient_no_demographics_no_prefix():
    soap = "[Diagnosis]\nCAD\n[Assessment & Plan]\nplan"
    out = es.process_patient(soap, "", "20260101")
    assert not out["c_text"].startswith(("0 y/o", "1 y/o"))
    assert "y/o" not in out["c_text"].split("\n")[0]


def test_process_patient_partial_demographics():
    """Missing gender → no prefix (age alone not enough)."""
    soap = "x"
    div = "姓名 : 林大姊 , 生日 : 1950/01/01"
    out = es.process_patient(soap, div, "20260101")
    assert "y/o" not in out["c_text"]
    assert out["name"] == "林大姊"


# ---------------- verify_main_emr (pure logic) ----------------

def test_parse_divuserspec_full():
    raw = "姓名 : 王小明 , 生日 : 1960/05/15 , 性別 : 男 , 病歷 : 12345678"
    name, birth, gender = es.parse_divuserspec(raw)
    assert name == "王小明"
    assert birth == (1960, 5, 15)
    assert gender == "男"


def test_parse_divuserspec_empty():
    name, birth, gender = es.parse_divuserspec("")
    assert name == ""
    assert birth is None
    assert gender == ""


def test_get_fg_options_falls_back_when_sheet_unavailable(monkeypatch):
    """When Sheet 下拉選單 unreachable, falls back to DIAG_RULES/CATH_RULES."""
    from app.services import sheet_service as ss
    monkeypatch.setattr(ss, "read_fg_options_from_sheet", lambda: None)
    f, g = es.get_fg_options()
    assert "STEMI" in f and "CAD" in f
    assert "PCI" in g and "CRT" in g
    assert "s/p PCI" in f
    assert "Cover stent" in g
    # Idempotency
    f2, g2 = es.get_fg_options()
    assert f2.count("s/p PCI") == 1
    assert g2.count("Cover stent") == 1


def test_get_fg_options_uses_sheet_when_available(monkeypatch):
    """Sheet 下拉選單 wins over hardcoded fallback."""
    from app.services import sheet_service as ss
    sheet_f = ["STEMI", "CAD", "MyCustomDx"]
    sheet_g = ["TAVI", "CRT", "MyCustomCath"]
    monkeypatch.setattr(ss, "read_fg_options_from_sheet", lambda: (sheet_f, sheet_g))
    f, g = es.get_fg_options()
    assert f == sheet_f
    assert g == sheet_g


def test_apply_emr_main_fixes_writes_changed_fields(monkeypatch):
    """EMR-corrected name/age/gender writes to main F/G/H. Same values skip."""
    main_grid = [
        ["", "", "", "", "", "張三", "男", "60", "111", "", "", ""],
        ["", "", "", "", "", "舊名", "女", "70", "222", "", "", ""],
    ]
    patches_captured = []

    class _FakeWS:
        id = 1

    monkeypatch.setattr(es, "__name__", es.__name__)  # no-op, keep import path
    from app.services import sheet_service as ss
    monkeypatch.setattr(ss, "get_worksheet", lambda d: _FakeWS())
    monkeypatch.setattr(ss, "read_range", lambda ws, a1: main_grid)
    monkeypatch.setattr(ss, "batch_write_cells",
                        lambda ws, patches, raw=False: patches_captured.extend(patches))

    results = [
        # 111: same name/gender, age 60→61
        {"chart_no": "111", "emr_name": "張三", "gender": "男", "age": 61, "error": ""},
        # 222: name fixed + age fixed, gender same
        {"chart_no": "222", "emr_name": "新名", "gender": "女", "age": 71, "error": ""},
        # 333: not in main → ignored, not in patches
        {"chart_no": "333", "emr_name": "甲", "gender": "男", "age": 50, "error": ""},
    ]
    out = es.apply_emr_main_fixes("20260515", results)
    assert out["patches_count"] == 3  # 111 age + 222 name + 222 age
    cells = {a1 for a1, _ in patches_captured}
    assert cells == {"H2", "F3", "H3"}
    fields = {(f["chart_no"], f["field"]) for f in out["fixes"]}
    assert fields == {("111", "age"), ("222", "name"), ("222", "age")}


def test_apply_emr_main_fixes_skips_errors_and_empty(monkeypatch):
    """Patients with error= or empty EMR demographics don't trigger writes."""
    main_grid = [["", "", "", "", "", "甲", "男", "60", "111", "", "", ""]]
    patches_captured = []

    class _FakeWS:
        id = 1

    from app.services import sheet_service as ss
    monkeypatch.setattr(ss, "get_worksheet", lambda d: _FakeWS())
    monkeypatch.setattr(ss, "read_range", lambda ws, a1: main_grid)
    monkeypatch.setattr(ss, "batch_write_cells",
                        lambda ws, patches, raw=False: patches_captured.extend(patches))

    results = [
        {"chart_no": "111", "emr_name": "正確", "gender": "男", "age": 99,
         "error": "fetch failed"},  # has error → skipped entirely
    ]
    out = es.apply_emr_main_fixes("20260515", results)
    assert out["patches_count"] == 0
    assert patches_captured == []


def test_apply_emr_main_fixes_missing_sheet_returns_skipped(monkeypatch):
    from app.services import sheet_service as ss
    monkeypatch.setattr(ss, "get_worksheet", lambda d: None)
    out = es.apply_emr_main_fixes("20260515", [{"chart_no": "111"}])
    assert out["skipped"] is True
    assert out["patches_count"] == 0


def test_compare_demographics_all_match():
    row = {"row": 5, "chart": "111", "sheet_name": "王小明",
           "sheet_gender": "男", "sheet_age": "66"}
    out = es.compare_demographics(row, "王小明", (1960, 5, 15), "男", "20260601")
    assert out["patches"] == []
    assert out["diffs"] == []


def test_compare_demographics_age_diff():
    row = {"row": 5, "chart": "111", "sheet_name": "王小明",
           "sheet_gender": "男", "sheet_age": "65"}  # sheet says 65, EMR DOB → 66
    out = es.compare_demographics(row, "王小明", (1960, 5, 15), "男", "20260601")
    assert ("H5", "66") in out["patches"]
    assert any("age" in d for d in out["diffs"])


def test_compare_demographics_name_mismatch_patches_F():
    row = {"row": 7, "chart": "111", "sheet_name": "王小銘",  # OCR typo
           "sheet_gender": "男", "sheet_age": "66"}
    out = es.compare_demographics(row, "王小明", (1960, 5, 15), "男", "20260601")
    cells = [p[0] for p in out["patches"]]
    assert "F7" in cells
    assert ("F7", "王小明") in out["patches"]


def test_compare_demographics_multiple_diffs():
    row = {"row": 9, "chart": "222", "sheet_name": "X",
           "sheet_gender": "男", "sheet_age": "30"}
    out = es.compare_demographics(row, "李大姊", (1950, 1, 1), "女", "20260601")
    cells = [p[0] for p in out["patches"]]
    assert sorted(cells) == ["F9", "G9", "H9"]
    assert ("G9", "女") in out["patches"]


def test_compare_demographics_empty_emr_skips_those_fields():
    """If EMR returns empty name/gender, don't overwrite sheet with empties."""
    row = {"row": 5, "chart": "111", "sheet_name": "王小明",
           "sheet_gender": "男", "sheet_age": "66"}
    out = es.compare_demographics(row, "", (1960, 5, 15), "", "20260601")
    cells = [p[0] for p in out["patches"]]
    assert "F5" not in cells
    assert "G5" not in cells
    # Age does get checked because we have birth + today
    # 1960-05-15 → 66 at 2026-06-01 → matches sheet 66, no patch
    assert out["patches"] == []


def test_compare_demographics_no_birth_skips_age():
    row = {"row": 5, "chart": "111", "sheet_name": "王",
           "sheet_gender": "男", "sheet_age": "30"}
    out = es.compare_demographics(row, "王", None, "男", "20260601")
    cells = [p[0] for p in out["patches"]]
    assert "H5" not in cells


# --------------------- write_results_to_subtables preserve-existing rule ---------------------

class _FakeWS:
    """Minimal sheet stub — accepts the calls the writeback function makes."""
    def __init__(self):
        self.batch_calls = []
    def update_cell(self, *a, **kw): pass


def _stub_writeback_io(monkeypatch, tables):
    """Mock the I/O surfaces so write_results_to_subtables runs against `tables`."""
    from app.services import sheet_service, ordering_service, subtable_service
    ws = _FakeWS()
    monkeypatch.setattr(sheet_service, "get_worksheet", lambda d: ws)
    monkeypatch.setattr(sheet_service, "ensure_chart_text_format", lambda w: None)
    monkeypatch.setattr(sheet_service, "set_fg_validation",
                        lambda *a, **kw: None)
    written: list = []
    monkeypatch.setattr(sheet_service, "batch_write_cells",
                        lambda w, patches: written.extend(patches))
    monkeypatch.setattr(ordering_service, "read_doctor_subtables",
                        lambda d: {doc: list(pts) for doc, pts in tables.items()})
    monkeypatch.setattr(subtable_service, "build_subtables_from_main",
                        lambda d: None)
    return written


def test_writeback_preserves_chart_with_existing_emr(monkeypatch):
    """Row with non-empty C (emr text) — preserve all, no patches."""
    tables = {"許志新": [{
        "row": 5, "name": "張三", "chart_no": "12345",
        "emr": "65 y/o 男\nS: chest pain", "diagnosis": "", "cathlab": "",
    }]}
    written = _stub_writeback_io(monkeypatch, tables)
    results = [{"chart_no": "12345",
                "c_text": "70 y/o 女\nNEW SOAP",
                "f": "AS", "g": "TAVI", "emr_name": "張三",
                "emr_gender": "女", "emr_birth_y": 1956}]
    out = es.write_results_to_subtables("20260526", results)
    assert out["written"] == 0
    assert "12345" in out["preserved"]
    assert written == []  # nothing got patched


def test_writeback_preserves_chart_with_existing_diagnosis_only(monkeypatch):
    """Row with C empty but F filled — still preserve (user typed F)."""
    tables = {"許志新": [{
        "row": 5, "name": "張三", "chart_no": "12345",
        "emr": "", "diagnosis": "CAD", "cathlab": "",
    }]}
    written = _stub_writeback_io(monkeypatch, tables)
    results = [{"chart_no": "12345",
                "c_text": "70 y/o 女\nNEW",
                "f": "AS", "g": "TAVI"}]
    out = es.write_results_to_subtables("20260526", results)
    assert out["written"] == 0
    assert out["preserved"] == ["12345"]
    assert written == []


def test_writeback_writes_to_empty_row(monkeypatch):
    """Fresh row with empty C/F/G — write everything normally."""
    tables = {"許志新": [{
        "row": 5, "name": "張三", "chart_no": "12345",
        "emr": "", "diagnosis": "", "cathlab": "",
    }]}
    written = _stub_writeback_io(monkeypatch, tables)
    results = [{"chart_no": "12345",
                "c_text": "70 y/o 女\nNEW",
                "f": "AS", "g": "TAVI"}]
    out = es.write_results_to_subtables("20260526", results)
    assert out["written"] == 1
    assert out["preserved"] == []
    cells = [p[0] for p in written]
    assert "C5" in cells
    assert "F5" in cells
    assert "G5" in cells


def test_writeback_skips_error_results(monkeypatch):
    """Result with error field — skipped (not preserved, not written)."""
    tables = {"許志新": [{
        "row": 5, "name": "張三", "chart_no": "12345",
        "emr": "", "diagnosis": "", "cathlab": "",
    }]}
    written = _stub_writeback_io(monkeypatch, tables)
    results = [{"chart_no": "12345", "error": "fetch timeout",
                "c_text": "", "f": "", "g": ""}]
    out = es.write_results_to_subtables("20260526", results)
    assert out["written"] == 0
    assert out["preserved"] == []  # error path doesn't trigger preserve
    assert written == []


def test_writeback_emr_name_overrides_preserved_row(monkeypatch):
    """When C/F/G filled (preserve) but EMR canonical name differs from
    sub-table A, A IS still patched. Models the 2026-05-21 石文明 → 周素珍
    case (prior fetch wrote wrong name due to divUserSpec race; new fetch
    must rename even with the row otherwise preserved).
    """
    tables = {"詹世鴻": [{
        "row": 7, "name": "石文明", "chart_no": "00385733",
        "emr": "65 y/o 男\nOLD", "diagnosis": "CAD", "cathlab": "LHC",
    }]}
    written = _stub_writeback_io(monkeypatch, tables)
    results = [{"chart_no": "00385733",
                "c_text": "NEW", "f": "AS", "g": "TAVI",
                "emr_name": "周素珍"}]
    out = es.write_results_to_subtables("20260526", results)
    # C/F/G NOT written (preserved); A IS written (canonical name update).
    assert "00385733" in out["preserved"]
    cells = [(p[0], p[1]) for p in written]
    assert ("A7", "周素珍") in cells
    assert not any(c.startswith("C7") for c, _ in cells)
    assert not any(c.startswith("F7") for c, _ in cells)
    assert not any(c.startswith("G7") for c, _ in cells)


def test_writeback_mixed_batch_one_preserved_one_new(monkeypatch):
    """Two charts: one already-EMR'd → preserved; one fresh → written."""
    tables = {"許志新": [
        {"row": 5, "name": "張三", "chart_no": "12345",
         "emr": "65 y/o 男\nOLD", "diagnosis": "CAD", "cathlab": "LHC"},
        {"row": 6, "name": "李四", "chart_no": "67890",
         "emr": "", "diagnosis": "", "cathlab": ""},
    ]}
    written = _stub_writeback_io(monkeypatch, tables)
    results = [
        {"chart_no": "12345", "c_text": "NEW", "f": "AS", "g": "TAVI"},
        {"chart_no": "67890", "c_text": "60 y/o 男\nfresh",
         "f": "AS", "g": "TAVI"},
    ]
    out = es.write_results_to_subtables("20260526", results)
    assert out["written"] == 1
    assert out["preserved"] == ["12345"]
    cells = [p[0] for p in written]
    # Only row 6 (chart 67890) got writes
    assert any(c.endswith("6") for c in cells)
    assert not any(c.endswith("5") for c in cells)
