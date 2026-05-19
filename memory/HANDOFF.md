============================================
  HANDOFF — Last Updated: 2026-05-19 14:30
============================================

[What this session did]
  1. Fixed SA service-account detection bug reported in the field
     (麒翔 dropped SA into %LOCALAPPDATA%\admission-app but connection
     failed with "No such file or directory: ''").
  2. Root cause = two bugs stacked:
     (a) appconfig._cached never reset → SA dropped AFTER first load()
         stayed undetected for the process lifetime;
     (b) save_settings unconditionally wrote the hidden/blank
         google_creds_path form field as "" into config.json.
  3. Fix (config.py + main.py) + 2 regression tests; 334 passed.

[Current state]
  - Branch: main, IN SYNC with origin (about to commit this fix).
  - Uncommitted: app/config.py, app/main.py, tests/test_config.py.
  - Tests: 334 passed (was 332 + 2 new regression tests).
  - No new release built yet for this fix.

[Next steps]
  - Build + publish a new release carrying this fix so 麒翔 can
    pure-drop the SA file with no manual steps. Then deliver per
    package-distribute Path A.
  - Tell 麒翔 the immediate workaround if he can't wait for the new
    build: file must be named EXACTLY service_account.json (Windows
    hides extensions → service_account.json.txt silently fails),
    placed at C:\Users\Greg\AppData\Local\admission-app\, then FULLY
    restart the app (clears stale _cached).

[Known issues / blockers]
  - Push to main gated — user authorized this session's push+release.
  - package-distribute SKILL.md should warn recipients the dropped
    file must be named exactly service_account.json — needs user
    authorization to edit SKILL.md (flagged, not yet done).
  - Public CI release still has NO SA / NO cathlab static (PHI by
    design) — unchanged.

[Don't repeat these mistakes]
  - appconfig._cached is process-global; any "drop a file then it
    should be picked up" flow must call appconfig.reset_cache().
  - Blank settings-form fields must NOT clobber bundle-supplied
    values (mirror the llm_api_key / cathlab_pass guard).
  - _detect_sa() only matches the literal name service_account.json.

[Relevant files]
  - app/config.py (save() re-detects SA on blank path; new
    reset_cache())
  - app/main.py (save_settings: don't wipe creds on blank submit;
    /api/settings/test resets caches before re-load)
  - tests/test_config.py (2 regression tests)

[Important memory files]
  - project_cathlab_static_decouple.md (delivery context)
  - project_bundle_naming_invariant.md (release asset naming)
  - feedback_no_column_letters_in_ui.md
