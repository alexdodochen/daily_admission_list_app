---
name: strip auth when porting CV-Schedulling-APP code
description: This is a single-user local app; never reintroduce login/users/audit/admin when porting from the multi-user server version
type: feedback
originSessionId: 72454ca2-3f8b-459c-b668-ba750a7a2e97
---
When porting code from `CV-Schedulling-APP` (which has `auth.py`, `manage_users.py`, `audit.py`, login/register/admin templates, cookie-based session tokens, role checks), **strip every auth-related thing** before landing it here.

**Why:** This repo (`daily_admission_list_app`) is built as a **double-clickable .exe for one person at a time** — the year's incoming 行政總醫師 runs it locally on their own machine with their own LLM key + their own SA JSON. The handoff doc (`CV_APP_INTEGRATION_HANDOFF.md` line 65) explicitly states *"Auth: login bypass like CV-Schedulling-APP (synthetic local admin)"* — meaning no real auth. Adding it back would be a regression in scope. CV-Schedulling-APP itself uses auth because it's deployed as a shared service; this app is single-user.

**How to apply:**
- When porting routes/templates, remove `_get_user(request)` checks, `login_required` decorators, `is_admin` template guards, `audit.log(...)` calls
- Drop `templates/login.html|register.html|admin.html` from the port set
- Drop the `_get_user`, `_client_ip`, `audit`, `auth` imports
- Page routes use the same redirect-to-/settings pattern as Card 3 when `cfg.is_ready()` is false — that's the only gate
- API endpoints take payload directly (no `_get_user` cookie check)
