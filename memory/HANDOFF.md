============================================
  HANDOFF — Last Updated: 2026-05-19 01:00
============================================

[What this session did] (Phase 14, multi-turn)
  1. claude-skills bidirectional sync + restored global ~/.claude/memory
     (42 files). LAST cross-repo sync ever — see cutover below.
  2. /sched dead button fixed: app.js global `$` vs inline `$` redeclare
     → IIFE-wrapped schedule_gen.html. (7a94419)
  3. Card 1 fully ported from Key-Schedule-APP: VS 不值假日 exempt,
     prev-tail box, CR 預估表, 寫入後預估累計表; backend
     read_calendar_tail/previous_year_month, _build_projection. (101f0f1)
  4. Step 5 manual schedule edit (last Key-Schedule-APP port 7b6ccf4):
     recompute_from_schedule + /api/sched/apply-edits + editable cal.
  5. Sync cutover: ALL sync now daily_admission_list_app ONLY. upstream.py
     SOURCES={self}, base.html 1 row, test_upstream rewritten. (82c0bd0)
  6. ② EMR auto-loads patient list (no JSON paste) — step1Write caches +
     run3-btn fetches /api/step4/subtables by date. (3cba995)
  7. 姓名 always EMR-corrected, "?" stripped (main F + sub-table A +
     cards) + manual 註記 (H) field. (61492de)
  8. ③ 入院序整合 renders the written N-W order on screen. (9e0a531)
  9. ② EMR long body collapsible + 全部收合/展開 bar. (61f3907)
 10. SA decoupled from build: config._detect_sa (DATA_DIR persists across
     updates), settings drop-in card, CI releases stay credential-free →
     auto-update safe. (4acbcb8)
 11. (user/other machine) Step5 房 dropdown + editable dry-run + auto
     time-by-session + OCR '?' fix. (e9254d6, acb012f)
 12. exe built+zipped twice → C:\Users\dr\Downloads\Y\每日入院名單 for
     麒翔.zip (380MB, outside repo).

[Current state]
  - Branch: main, clean, IN SYNC with origin/main @ acb012f
  - CI auto-builds+releases every push (release.yml, on push:main);
    latest tag v20260519-0025-e9254d6
  - Dev server: launch with `python -m app.run` (port 8766)
  - Tests: 330 passed
  - app/VERSION is a build-time stamp (CI rewrites it) — don't hand-commit

[Next steps]
  - Deliver to 麒翔: send the zip + service_account.json SEPARATELY;
    he drops the .json into the path shown on /settings (DATA_DIR) →
    survives auto-update. Optionally rebuild a clean (no-SA) zip as the
    standard public distributable.
  - Manual-verify on /sched real month: solve→手調→套用重算 cycle.
  - Optional: pytest for recompute_from_schedule / apply-edits.

[Known issues / blockers]
  - Push to main gated by auto-mode classifier — needs explicit user
    "授權push" each time.
  - Hand-built zip has SA bundled; CI/public release does NOT (by
    design). Recipient must drop service_account.json into DATA_DIR.

[Don't repeat these mistakes]
  - Sub-page extends base.html → IIFE-wrap inline script (global `$`
    collision). [[feedback-subpage-iife-scope]]
  - Git Bash `tar` treats `C:/` as remote host → Windows `tar.exe`.
  - Don't direct-call /api/sched/solve on synthetic baseline (blocks
    worker minutes, holds port 8766; kill by port).
  - Sync ONLY daily_admission_list_app — no other repos.
    [[feedback-card1-sync-source-cutover]]
  - Never put SA in a public GitHub Release (repo is public).

[Relevant files]
  - app/config.py (_detect_sa, sa_status), app/main.py (_ctx sa=,
    _build_projection, apply-edits, step3 note enrich)
  - app/services/{cv_solver,scheduling_service,emr_service}.py
  - app/static/app.js (EMR autoload, name, 註記, order-result, collapse)
  - app/templates/{schedule_gen,admission,settings,base}.html

[Important memory files]
  - project_3card_app_state.md (Phase 14)
  - feedback_card1_sync_source_cutover.md (sync = project repo only)
  - feedback_subpage_iife_scope.md
