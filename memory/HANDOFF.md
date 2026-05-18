============================================
  HANDOFF — Last Updated: 2026-05-18 12:30
============================================

[What this session did]
  1. claude-skills bidirectional sync: pulled workflow-docs (EN) → local;
     pushed local-newer skills + pci-cert (×2) → repo; restored global
     ~/.claude/memory (42 files, was absent). claude-skills@d38113b.
  2. Fixed dead /sched 「載入月份資料」button — app.js global `$` vs
     inline `$` redeclare aborted whole script. IIFE-wrapped. (7a94419)
  3. Verified Phase 13 e2e incl. real EMR (20260525, 7 pts, F/G detect +
     NO_RECORD handling all correct, writeback 7/7).
  4. Card 1: fully ported canonical UI from Key-Schedule-APP — VS 不值假日
     exempt checkboxes, prev-tail cross-month box, CR 預估表, 寫入後預估
     累計表. Backend: read_calendar_tail/previous_year_month, /init prev_tail,
     /compute+/solve param forwarding, _build_projection helper.
  5. Step 5 manual schedule edit (Key-Schedule-APP 7b6ccf4, LAST sync):
     cv_solver.recompute_from_schedule + /api/sched/apply-edits + editable
     <select> calendar + 套用手調/還原 buttons. (101f0f1)
  6. Built exe (pyinstaller) + zipped → "每日入院名單 for 麒翔.zip"
     (380MB, C:\Users\dr\Downloads\Y\, outside repo). exe boots + bundled
     SA connects to Sheet (verified).
  7. Sync-cutover follow-through: upstream.py SOURCES trimmed to {self}
     only; base.html upstream panel → single 本 App row (was 3-repo
     check). Topbar now only reports daily_admission_list_app.
  8. LLM "getaddrinfo failed" the user hit = transient hospital-net DNS
     blip; re-test now all green (llm/sheet/sched ok). Not a bug.

[Current state]
  - Branch: main, clean, synced with origin/main
  - Latest commit: 101f0f1 (Card 1 port + Step 5) — pushed
  - Dev server: NOT running (was killed for exe test; restart via
    `python -m app.run` if needed)
  - Tests: 335/335 pass
  - exe deliverable ready at C:\Users\dr\Downloads\Y\每日入院名單 for 麒翔.zip

[Next steps]
  - User manual-verify on /sched real 6月 + prefs: full solve→edit→
    套用手調並重算 cycle + 寫入後預估累計表 render (solver slow on
    synthetic baseline — UI-only verification per CLAUDE.md).
  - Optional: add pure-logic tests for recompute_from_schedule +
    apply-edits routing (not yet covered; upstream added none either).
  - Hand the zip to 麒翔 via large-file transfer; rotate SA key when
    he leaves (BUILD.md "Rotating credentials").

[Known issues / blockers]
  - Pushing to main is gated by the auto-mode classifier each time —
    needs explicit user "授權push" per push.
  - exe console shows Chinese path as mojibake (cosmetic only).

[Don't repeat these mistakes]
  - Sub-page extending base.html → IIFE-wrap inline script or app.js
    global `$` collision kills it. [[feedback-subpage-iife-scope]]
  - Git Bash `tar` treats `C:/...` as remote host → use Windows
    `tar.exe` (PowerShell) or `--force-local`.
  - Don't direct-API-call /api/sched/solve on synthetic baseline — it
    blocks the single uvicorn worker for minutes and holds port 8766
    (kill by port to recover).
  - Do NOT sync from Key-Schedule-APP anymore — updates only from
    daily_admission_list_app. [[feedback-card1-sync-source-cutover]]

[Relevant files]
  - app/services/cv_solver.py (recompute_from_schedule)
  - app/main.py (_build_projection, /api/sched/apply-edits, init/compute/
    solve param forwarding)
  - app/services/scheduling_service.py (previous_year_month,
    read_calendar_tail)
  - app/templates/schedule_gen.html (full upstream port + IIFE + Step 5)
  - app/VERSION (bumped), packaging.spec / BUILD.md (exe build)

[Important memory files]
  - project_3card_app_state.md (Phase 14 prepended)
  - feedback_card1_sync_source_cutover.md (NEW)
  - feedback_subpage_iife_scope.md (NEW)
