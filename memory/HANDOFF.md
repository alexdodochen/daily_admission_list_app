============================================
  HANDOFF — Last Updated: 2026-05-19 14:30
============================================

[What this session did]
  1. Fixed SA detection bug from the field (SA dropped into
     %LOCALAPPDATA%\admission-app, connection failed empty creds path).
     Root cause = (a) appconfig._cached never reset; (b) save_settings
     wrote the blank google_creds_path form field as "". Pushed 05e6e33.
  2. Hardened _detect_sa(): accepts ANY *.json that is a valid SA key
     (no exact-rename — Windows hides ext → service_account.json.txt),
     normalises to canonical name. config.reset_cache() +
     /api/settings/test cache reset (drop-after-launch, no restart).
  3. User chose option 2 for cathlab: KEEP drop-in (not bundle PHI),
     but upgrade UX to SA parity. cathlab_service: loose-drop into
     DATA_DIR (next to service_account.json) now detected + migrated
     into cathlab_static; reset_cache() wired into /api/settings/test;
     error msg + status drop_dir now point at DATA_DIR.
  4. Tests: 338 passed (+6 regression across config/cathlab).

[Field-bug triage 2026-05-19 (3 issues, all fixed, 347 passed)]
  A. Auto-update dead-ended on .exe: 更新 button → upstream._sync_self
     was git-only. Fixed: frozen → updater.apply() (zip swap). Also
     updater.schedule_restart frozen → os._exit (was os.execv →
     swap.bat dead-lock). IMPLICATION: pre-fix installs (incl. 麒翔)
     must manually download the new zip ONCE; then 更新 works.
  B. Playwright chromium missing: release.yml cached browsers under a
     hardcoded key (chromium-1208) with install gated on cache-miss →
     stale browser bundled vs newer Playwright wanting chromium-1223.
     Fixed: cache key = resolved Playwright version + presence guard.
  C. 20260601 not loadable: sheet_service memoised Spreadsheet; a tab
     created by another instance was invisible. Fixed: get_worksheet
     refresh-metadata+retry; list_sheets refreshes first.
  Pending follow-up: in-app "回報 bug" button (user request) — NOT
  yet built; design TBD (must scrub PHI/credentials).

[What this session ALSO did]
  5. Step 1 OCR re-upload behavior changed per user rule: new
     screenshot consulted for MEMBERSHIP ONLY. No add/remove →
     write NOTHING (照舊, keyed cells survive). Add/remove → keep
     each kept patient's A-L row VERBATIM, only drop removed +
     append added; sub-table/N-V reconcile unchanged. UI message
     de-jargoned (no "A2:L34"). 340 passed (+2 regression).
     Trade-off: doctor-change-without-add/remove → 照舊 (not
     auto-applied to main; UI just notes it).

[Current state]
  - Branch: main. Pushed: 05e6e33 (SA fix), b7fd622 (cathlab UX),
    c0d6cb2 (使用方法.txt one-folder wording), 8e595aa (docs sync).
  - Uncommitted: app/services/ocr_service.py, app/static/app.js,
    tests/test_ocr_service.py (the membership-only merge).
  - CI release v20260519-0638-c0d6cb2 published + STEP V VERIFIED:
    VERSION sha == HEAD, cathlab static absent (PHI-correct Path A),
    使用方法.txt at bundle root with new wording, zip+exe ok.
    NOTE: PyInstaller onedir packs app/*.py into PYZ — cannot grep
    .py from the zip; provenance = VERSION sha + git ancestry only.
  - SKILL.md package-distribute updated (one-folder drop, in-app
    update protocol, rename caveat + version-detection, Step V.3
    rewrite). UNCOMMITTED.
  - Tests: 338 passed.

[Next steps]
  - Commit + push the SKILL.md sync (push gated — ask user).
  - Deliver to 麒翔 (existing install → Path A in-app update):
    1. FIRST check his installed version (filename: Chinese
       行政總醫師.排班.Key班.入院.exe = post-rename → just press 更新;
       old name = pre-rename → ONE manual re-download of
       v20260519-0638-c0d6cb2 admission-app.zip this time).
    2. Privately, separately send service_account.json + 3 cathlab
       JSONs; tell him to drop ALL 4 LOOSE into
       %LOCALAPPDATA%\admission-app (no subfolder, SA name free),
       then press 設定頁 測試連線 (no restart).

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
