"""Bug-report builder: scrubbing must strip PHI + credentials before
anything can leave the machine (public repo + patient data)."""
from __future__ import annotations

import json

from app import config as appconfig
from app import log_buffer
from app.services import bug_report


def test_scrub_removes_chart_numbers_and_keys():
    raw = ("病人 王小明 病歷號 12345678 入院；"
           "api_key=sk-abcdef0123456789ABCDEF token: ghp_zzzzzzzzzzzz "
           "email a.b+x@hosp.ncku.edu.tw")
    out = bug_report.scrub(raw)
    assert "12345678" not in out
    assert "sk-abcdef0123456789ABCDEF" not in out
    assert "ghp_zzzzzzzzzzzz" not in out
    assert "a.b+x@" not in out
    assert "[數字已隱藏]" in out
    assert "姓名" in out or "[姓名已隱藏]" in out  # name-context redaction


def test_scrub_redacts_exact_config_values(monkeypatch, tmp_path):
    monkeypatch.setattr(appconfig, "CONFIG_PATH", tmp_path / "c.json")
    appconfig.reset_cache()
    (tmp_path / "c.json").write_text(json.dumps({
        "llm_api_key": "MY-SUPER-SECRET-KEY-VALUE",
        "cathlab_pass": "p@ssw0rd-very-unique",
    }), encoding="utf-8")
    appconfig.reset_cache()
    txt = "log line with MY-SUPER-SECRET-KEY-VALUE and p@ssw0rd-very-unique"
    out = bug_report.scrub(txt)
    assert "MY-SUPER-SECRET-KEY-VALUE" not in out
    assert "p@ssw0rd-very-unique" not in out
    appconfig.reset_cache()


def test_collect_shape_and_logs_scrubbed():
    log_buffer.record("patient 病歷號 87654321 crashed")
    diag = bug_report.collect({"note": "壞了 病歷號 11223344",
                               "step": "Step 3", "error": "boom"})
    assert diag["version"] and "flags" in diag
    assert "87654321" not in "\n".join(diag["logs"])
    assert "11223344" not in diag["user_note"]
    # flags are booleans / safe strings only — no raw secret values
    assert isinstance(diag["flags"]["llm_key_set"], bool)


def test_issue_url_is_prefilled_and_bounded():
    diag = bug_report.collect({"note": "x", "step": "y", "error": "z"})
    url = bug_report.build_issue_url(diag)
    assert url.startswith(
        "https://github.com/alexdodochen/daily_admission_list_app/issues/new?")
    assert "title=" in url and "body=" in url and "labels=bug" in url


def test_write_report_file(tmp_path, monkeypatch):
    monkeypatch.setattr(appconfig, "DATA_DIR", tmp_path)
    diag = bug_report.collect({"note": "n", "step": "s", "error": "e"})
    p = bug_report.write_report_file(diag)
    assert p.exists() and p.parent.name == "bug_reports"
    assert "環境" in p.read_text(encoding="utf-8")


def test_long_logs_trimmed_under_url_cap():
    for i in range(2000):
        log_buffer.record(f"line {i} aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    diag = bug_report.collect({"note": "n"}, log_lines=400)
    url = bug_report.build_issue_url(diag)
    assert len(url) < 16000  # comfortably within browser/GitHub limits
