============================================
  HANDOFF — Last Updated: 2026-05-20 04:00
============================================

[What this session did]
  1. Triaged field bug report GitHub issue #1 (2026-05-20):
     - DNS error on sheets.googleapis.com (network-side, not code)
     - 🐞 button too pale → red pill (white 700 text, 2px dark-red
       border, shadow) — see app/static/app.css.
  2. Built `app/services/diagnose.py` — maps 8 common conn failures
     (DNS / timeout / 403 / 404 / invalid_grant / SA missing / SSL /
     quota) → {title, cause, suggestions, is_code_bug}. Hooked into
     /api/settings/test; UI renders friendly cards via renderConnTest()
     (no more raw JSON dump). +13 tests.
  3. Fixed self-sync 'TypeError: Failed to fetch' UX race — moved
     schedule_restart to FastAPI BackgroundTasks so the response flushes
     BEFORE os._exit fires; bumped restart delay 0.8s → 1.5s; JS treats
     Failed-to-fetch on name='self' as expected restart and auto-reload.
  4. Topbar split into two rows — Row1: brand + upstream-bar + status;
     Row2: nav links + 🐞 (right-aligned). Wraps cleanly on narrow.
  5. **Critical** — fixed in-app updater that bricked an install:
     - v1 (a68c3da): UTF-8 .bat + chcp + IMAGENAME → mojibake → stuck
     - v2 (4eae323): OEM .bat + tasklist|find " PID " → still stuck
       (user saw `find:23168` looping)
     - v3 (0e3501b stable): **PowerShell .ps1 + Get-Process -Id +
       60s hard timeout + Stop-Process fallback + 20×500ms rename
       retries + ASCII .bat shim.** Loop CANNOT spin forever now.

[Field-bug triage 2026-05-20 — 6 commits, 372 passed]
  407023d — feat: diagnose + red bug button (issue #1 both parts)
  2d87786 — fix: self-sync Failed to fetch (BackgroundTasks)
  4eae323 — fix(updater): swap.bat codepage trap (incomplete)
  e53beda — ui: 2-row topbar
  0e3501b — fix(updater): migrate swap to PowerShell (stable)

[Current state]
  - Branch: main, clean, IN SYNC with origin/main @ 0e3501b
  - Tests: 372 passed (353 → +19 across diagnose + updater)
  - CI release: 0e3501b is the deliverable once GitHub Actions finishes
    its ~5-10 min build (release asset = ASCII admission-app.zip,
    361 MB onedir bundle).
  - GitHub Issue #1: closed + 2 follow-up comments posted explaining
    the DNS triage, the diagnose feature, and the 3-attempt updater fix.

[Next steps]
  - When CI finishes building 0e3501b release: tell every existing user
    on any commit BETWEEN a68c3da and 4eae323 (inclusive) that they
    MUST manually download the latest release zip ONCE — clicking the
    in-app 更新 button on those versions still uses the buggy bat code
    and will brick. After that one manual install, all future updates
    are safe (PS1-based).
  - If user 麒翔's install is currently bricked from the field bug:
    close stuck cmd window → relaunch old exe from install_dir
    (file lock not yet acquired since rename failed) → manually drop
    new release zip ONCE.
  - Carry-over from prior session: /sched real-month solve→手調→套用重算
    manual verify (still pending, lower priority).

[Known issues / blockers]
  - Pre-0e3501b installs cannot self-update without bricking. ONE
    manual zip download required per affected install.
    [[updater-swap-must-use-powershell]]
  - Push to main is still authorization-gated per session.
  - Public CI release has NO SA + NO 3 cathlab JSONs (PHI by design;
    [[delivery-protocol-inapp-update]]).

[Don't repeat these mistakes]
  - Never embed Chinese paths in a cmd .bat — cmd parses .bat in OEM
    codepage regardless of `chcp 65001`. Use PowerShell for any post-
    update / restart script touching Chinese paths.
    [[updater-swap-must-use-powershell]]
  - Never use `tasklist | find " N "` for process-alive checks — output
    formatting and PID column alignment make it unreliable. Use
    Get-Process -Id from PowerShell instead.
  - Never let an exit-detection loop be unbounded — always cap with a
    timeout + force-kill fallback so a broken check can't spin forever.
  - Common operational errors must surface actionable hints, NOT raw
    stack traces. [[diagnose-common-errors-not-raw-traces]]
  - Self-restart endpoints must use BackgroundTasks so the response is
    flushed before the process dies — otherwise the browser sees
    Failed-to-fetch and the user thinks the update failed.

[Relevant files]
  - app/services/diagnose.py (new — 150 lines, 8 error patterns)
  - app/services/updater.py (_write_swap_bat → PowerShell .ps1)
  - app/main.py (/api/settings/test hint wiring, /api/update/sync
    BackgroundTasks)
  - app/static/app.js (renderConnTest + self-sync restart catch)
  - app/static/app.css (red bug-link pill + conn-block hint cards +
    2-row topbar)
  - app/templates/base.html (2-row topbar structure)
  - tests/test_diagnose.py (new — 13 cases)
  - tests/test_updater.py (+6 cases for PS1 contract)

[Important memory files]
  - feedback_updater_swap_must_use_powershell.md (NEW — pin PS1 rule)
  - feedback_diagnose_common_errors_not_raw_traces.md (NEW — hint rule)
  - feedback_delivery_protocol_inapp_update.md (still holds, w/ caveat)
