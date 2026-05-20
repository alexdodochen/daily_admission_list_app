---
name: diagnose-common-errors-not-raw-traces
description: "When the app surfaces a common operational error (connection failure, permission denied, network DNS, etc.), it must show an actionable hint card with cause + self-service steps. Never dump a raw exception / stack trace at the user."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 9db9da1c-30f7-4824-888b-4b74c6d0cfaa
---

When a user-facing operation fails with a known-class error, the UI must
render a friendly card with:
- A one-line diagnosis title (e.g. "DNS 解析失敗 — 網路或防火牆問題")
- The cause in plain Chinese
- A numbered list of self-service steps the user can try
- The raw error tucked into a `<details>` for developers, NOT the
  default view.

**Why:** field report 2026-05-20 (GitHub issue #1) — user clicked 設定 →
測試連線, got `Failed to resolve 'sheets.googleapis.com' (getaddrinfo
failed)` dumped as raw JSON. They concluded "the app is broken" and
filed a bug. Same log showed Gemini API was reachable — i.e. it was
a network-side issue, not an app bug. Without an actionable hint, every
common network glitch turns into a bug report and erodes trust.

User quote (preserved verbatim):
> 那你出現bug你就要在app提供解決方案給使用者 如果是常見的bug理應有這種服務

**How to apply:**

- For any new endpoint that can fail with a known error class (network /
  perm / cred / quota), route the error string through
  `app/services/diagnose.py::diagnose(err, scope=...)` so it gets a
  `hint` block attached to the JSON response.
- New diagnosable patterns belong in `diagnose.py` (one matcher per
  failure mode). Cover at minimum: DNS, timeout, 403, 404, invalid
  creds, missing cred file, SSL, quota.
- UI renderers must check for `hint` and render it as a card, not as
  raw JSON. Pattern: `renderConnTest()` in `app/static/app.js`.
- The hint must say whether it's a code bug (`is_code_bug: false` for
  user-environment issues like DNS — important so the user doesn't
  re-report it as our bug).
- Tests in `tests/test_diagnose.py` pin every pattern.

Related: [[bug-report-feature]] — the 🐞 button is the escape hatch for
errors `diagnose.py` doesn't cover yet. As patterns get added to
`diagnose.py`, fewer escalations should reach the bug reporter.
