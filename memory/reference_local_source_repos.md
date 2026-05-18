---
name: local source repos for porting + static data
description: Where the read-only reference repos live on this machine — needed for Card 1/2 ports and for missing app/data/static/ JSON
type: reference
originSessionId: 72454ca2-3f8b-459c-b668-ba750a7a2e97
---
This public repo intentionally **does not ship** the upstream code or the static data; both must be sourced locally when needed.

**Reference repos on this machine (Windows):**

- `C:\Users\dr\Downloads\Y\排班 APP\` — local clone of `CV-Schedulling-APP`. Contains `cv_solver.py`, `gsheet_io.py`, `app.py` (server with auth), `templates/schedule_gen.html`, `templates/home.html`, `templates/login.html|register.html|admin.html`. **Card 1 was ported from here**; **Card 2** (keyin_*) is **not yet present** in this folder either — confirm before claiming the port can be done.
- `C:\Users\dr\Downloads\Y\每日入院名單 Claude\` — local clone of the **private** `daily-admission-list` workflow repo. Contains the missing `cathlab_id_maps.json` plus the reference impls (`cathlab_keyin.py`, `process_emr.py`, `fetch_emr.py`, `verify_cathlab.py`, `webcvis_*.py`, per-date JSON archives, `_step5_line_push.md`).
- The other folder name `C:\Users\dr\Downloads\Y\排班 Key班APP\` is currently **empty** — don't confuse with `排班 APP` (with space).

**GitHub remotes:**
- This repo: `https://github.com/alexdodochen/daily_admission_list_app.git`
- Reference: `https://github.com/alexdodochen/CV-Schedulling-APP` (公開), `https://github.com/alexdodochen/daily-admission-list` (私有)

**Public sheet IDs (assumed sanitised; default in `app/bundled/defaults.json`):**
- Admission (card 3): `1KR9fyszCFvoPmV9-9cGqSpf6kFNRC6je8BjUNaY2Pc0`
- Schedule (card 1): `10ilVOmJrr8jjfnMMbtj60tAIIAe1YX3ZRU1RLgn6Elk`

**Missing static data:** `app/data/static/cathlab_id_maps.json`, `doctor_codes.json`, `cathlab_schedule.json` — `app/data/` is `.gitignored`. Fresh clones are missing these → 26 cathlab tests fail with `FileNotFoundError` and Step 5 (cathlab) 500s. To fix on a clone, copy these three from `C:\Users\dr\Downloads\Y\每日入院名單 Claude\`.
