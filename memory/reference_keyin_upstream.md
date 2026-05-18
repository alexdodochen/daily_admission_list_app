---
name: reference-keyin-upstream
description: Upstream source repo for Card 2 (Key 班) — where to pull future updates from
metadata: 
  node_type: memory
  type: reference
  originSessionId: 2e27ecbd-39a1-425a-b28b-3c4df41994ad
---

Card 2 (Key 班) in the 3-card local app was ported from
https://github.com/alexdodochen/Key-Schedule-APP on 2026-05-15.

The local files are downstream of upstream. When upstream gets new features:

- `keyin_scheduler.py` — copied verbatim to `app/services/keyin_scheduler.py`. Pure Python + Playwright. Should diff cleanly against upstream.
- `keyin_excel_parser.py` — copied verbatim to `app/services/keyin_excel_parser.py`. Standalone.
- `keyin_routes.py` (upstream) → `app/services/keyin_routes.py` (local) — **needs manual merge**: auth (`from auth import TokenData`) + audit (`import audit`) are stripped, `_get_user(request)` removed, all `audit.log()` calls removed, Jinja2 path changed from `BASE_DIR / "templates"` to `app/templates/`, template rendered with `static_version` not `username/is_admin`, prefill cache changed from per-username dict to single-slot.
- `keyin_index.html` (upstream) → `app/templates/keyin.html` (local) — copied verbatim. References `/keyin/api/*` endpoints which match the local APIRouter prefix.

Upstream is a server app (PyQt5 wrapper + bcrypt/JWT auth + multi-user). This
local fork is single-user. See [[feedback-strip-auth-for-local-ports]].

Deps added: `openpyxl>=3.1`, `xlrd>=2.0` (for .xls/.xlsx parsing in
`keyin_excel_parser`).
