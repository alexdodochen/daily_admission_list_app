============================================
  HANDOFF — Last Updated: 2026-05-19 17:20
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
  D. In-app "🐞 回報問題" BUILT (user request): topbar link + modal;
     /api/bug-report/{preview,save}; app/log_buffer.py ring +
     app/services/bug_report.py hard scrub (config values, k=v
     secrets, sk-/AIza/40+ blobs, 6-12 digit runs, emails, name
     context). Both delivery paths: prefilled GitHub-issue URL (user
     reviews before submit) + local scrubbed file under
     DATA_DIR/bug_reports. +6 tests. 353 passed.

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
  - Branch: main, clean, IN SYNC with origin. HEAD = (post d0f63e3 +
    使用方法/HANDOFF doc commit). Full chain pushed this session:
    05e6e33 SA fix → b7fd622 cathlab loose-drop → c0d6cb2 使用方法 →
    8e595aa docs/skill sync → b81a5b2 OCR membership-only → 780a322
    3 field bugs → d0f63e3 bug-report feature.
  - Tests: 353 passed.
  - CI builds a fresh release on every push; the LATEST release (sha
    == current HEAD) is the deliverable. Step V verified earlier on
    c0d6cb2; same checks apply to the newest (provenance = VERSION
    sha == HEAD + git ancestry; cannot grep app/*.py from onedir zip).

[Next steps]
  - Deliver to 麒翔 (existing install). His build is PRE-FIX → the
    更新 button is itself broken → he MUST manually download the
    latest zip ONCE:
    https://github.com/alexdodochen/daily_admission_list_app/releases/latest
    (settings folder untouched; after this build, 更新 works forever
    AND Playwright chromium is correct). 使用方法.txt now documents
    this + the 🐞 回報問題 button.
  - Then privately + separately send service_account.json + 3 cathlab
    JSONs; he drops ALL 4 LOOSE into %LOCALAPPDATA%\admission-app
    (no subfolder, SA name free), presses 設定頁 測試連線 (no restart).
  - Carry-over: /sched real-month solve→手調→套用重算 manual verify.

[Known issues / blockers]
  - Push to main gated — explicit user authorization each time.
  - Pre-fix installs cannot self-update (updater bug) → one manual
    zip download required this once. [[delivery-protocol-inapp-update]]
  - Public CI release has NO SA / NO cathlab static (PHI by design).
  - Playwright runtime auto-install fallback NOT implemented (frozen
    has no `python -m playwright`); CI cache-key fix is the resolution.

[Don't repeat these mistakes]
  - Process-global caches (appconfig._cached, sheet_service._sh,
    cathlab _static_dir): any "drop a file / new tab" flow needs an
    explicit reset/refresh path.
  - The in-app 更新 button calls upstream._sync_self (NOT
    updater.apply directly) — frozen must delegate to updater.apply.
  - CI cache keys must track the dep version, never hardcode.
  - Bug-report scrub must never be weakened / made auto-submit
    (public repo + PHI). [[bug-report-feature]]

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
