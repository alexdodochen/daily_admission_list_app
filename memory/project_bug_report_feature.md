---
name: bug-report-feature
description: "In-app 🐞 回報問題 — collects scrubbed diagnostics; two delivery paths (prefilled public GitHub issue + local private file); hard PHI/credential scrub mandatory"
metadata:
  node_type: memory
  type: project
  originSessionId: 8f6f0aa1
---

Built 2026-05-19 on user request ("app 裡面要有蒐集問題回報給開發者
的按鈕，例如出問題時有回報bug按鈕"). User chose: BOTH delivery paths
+ include logs with strong scrub.

Pieces:
- `app/log_buffer.py` — process-local bounded ring (maxlen 400) logging
  handler; `install()` called once at import in `app/main.py`;
  `recent(limit)` / `record(line)`.
- `app/services/bug_report.py` — `collect()` (version+platform+frozen+
  boolean config flags+scrubbed logs+scrubbed user context),
  `render_markdown()`, `build_issue_url()` (prefilled GitHub new-issue
  URL, body trimmed < ~6.5k, labels=bug), `write_report_file()` →
  `DATA_DIR/bug_reports/bug_report_<ts>.txt`.
- Endpoints `POST /api/bug-report/preview` + `/save`.
- UI: topbar `🐞 回報問題` (`#bug-link`) + `#bug-modal`; `flash()` now
  stashes the last red error into `window.__lastError` to auto-fill the
  modal. IIFE-wrapped per [[subpage-iife-scope]].

**Why:** repo is PUBLIC and the app handles PHI (病歷號/姓名/EMR), so
nothing may auto-transmit. Scrub before anything can leave: exact
config values, `k=v` secret pairs, `sk-`/`AIza`/40+-char blobs, 6–12
digit runs (病歷號/DOB), emails, name-context (label + sep + short
CJK/alpha — whitespace separator allowed, OVER-redaction is the safe
side). The GitHub path is user-reviewed before submit (user = final
PHI gate); nothing here makes a network call or auto-submits.

**How to apply:**
- Never weaken the scrub or add an auto-submit/telemetry path — the
  public-repo + PHI constraint is hard. See [[no-column-letters-in-ui]]
  sibling discipline for user-facing safety.
- If logs start carrying a new secret shape, extend `bug_report` regexes
  + add a `test_bug_report.py` case (don't rely on the name-context
  catch-all).
- Tests: `tests/test_bug_report.py` (6).
