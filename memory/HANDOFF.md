============================================
  HANDOFF — Last Updated: 2026-06-04
============================================

[What this session did]
  Cross-project: disabled the LINE admission auto-push.
  1. Diagnosed that the 2026-06-02 "cron jobs ALL DISABLED" note
     was WRONG — user still received an auto-push on 2026-06-04,
     proving cron-job.org was still firing.
  2. Added a code-level master kill switch in the sibling
     line-reminder-bot repo: admission_push.PUSH_ENABLED (default
     False). Both push_admission_list / push_admission_weekend
     now return [DISABLED] before any sheet read or LINE send.
     Env var ADMISSION_PUSH_ENABLED=1 re-enables.
  3. Updated 4 skip-logic tests to patch PUSH_ENABLED=True; added
     test_push_disabled_blocks_all_sends. 10/10 pass.
  4. Committed (3e793ee) + pushed to line-reminder-bot main →
     Render auto-deploy. /health 200 OK.
  5. User then MANUALLY disabled the cron-job.org jobs (the real
     trigger). Both defenses now in place.
  6. This repo: added memory note + HANDOFF, pushed via rebase.

[Current state]
  - line-reminder-bot: main @ 3e793ee, pushed, Render deploying.
  - LINE auto-push: OFF (cron disabled by user + code kill switch).
  - THIS repo (daily_admission_list_app): memory commit rebased
    onto origin (updater #8 pulled in). Pre-existing local WIP
    (revert 改期 column N-V/N-W → N-U across app/services/* + tests/*
    + CLAUDE.md) is STASHED then restored to the working tree,
    UNCOMMITTED — it is the user's in-progress work, not this session's.

[Next steps]
  - Finish + commit the user's 改期-column revert WIP (working tree).
    Run pytest before committing (WIP touches many tests/).
  - To re-enable LINE push later: (a) cron-job.org dashboard
    re-enable jobs, AND (b) Render env var ADMISSION_PUSH_ENABLED=1
    + redeploy. Both required.
  - Watch GitHub issue #8 (updater brick) for reporter GregHsu21226's
    confirmation that manual zip-recovery worked; close once confirmed.

[Known issues / blockers]
  - issue #8 fix is FORWARD-ONLY: a bricked install can't auto-update,
    so already-broken users recover manually once (carried from 5/31).
  - admission-line-push SKILL.md (~/.claude/skills/) cleaned this
    session to single-source / no-GATE_DATE (see below).

[Don't repeat these mistakes]
  - Do NOT trust a doc note that says "cron disabled" — cron-job.org
    is external state, unverifiable from code. The reliable off
    switch is code-level PUSH_ENABLED. (User got a push 6/04 despite
    the 6/02 "disabled" note.)
  - Per [[feedback-card1-sync-source-cutover]]: this repo's memory/ IS
    tracked here; sync stays on daily_admission_list_app. Keep PHI-clean.
  - When pushing a small memory commit while big unrelated WIP sits in
    the tree: stash WIP → rebase → push → pop. Never commit the WIP as
    your own.

[Relevant files]
  - C:\Users\dr\repos\line-reminder-bot\line_reminder_bot\admission_push.py
  - C:\Users\dr\repos\line-reminder-bot\tests\test_app.py
  - C:\Users\dr\repos\line-reminder-bot\CLAUDE.md
  - this repo: memory/project_line_push_kill_switch.md (new)

[Important memory files]
  - project_line_push_kill_switch.md (NEW)
