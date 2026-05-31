============================================
  HANDOFF — Last Updated: 2026-05-31
============================================

[What this session did]
  1. Cross-machine sync: local had unpushed 9675065 (bottom stepper +
     EMR reflow + 王思翰/張倉惟 second doctor) that another machine had
     ALREADY re-done better in 9 pushed commits. User approved hard
     reset to origin/main (1c40396). Salvaged ONE unique memory the
     remote never recorded: feedback_long_forms_get_bottom_nav.
  2. Fixed GitHub issue #8 (updater brick) — see below. Replied to
     reporter (GregHsu21226) with manual zip-recovery steps; issue
     left OPEN pending his confirmation.
  3. Shipped: commit 5088deb pushed → CI Build+Release succeeded →
     release v20260531-0914-5088deb published with admission-app.zip.

[Current state]
  - Branch: main, in sync with origin/main (after this session's push).
  - Latest commit: 5088deb fix(updater): observable swap + user_data
    migration + failure breadcrumb (#8).
  - Latest release: v20260531-0914-5088deb (IS the fixed build).
  - Tests: 445 passed, 3 pre-existing test_config env failures
    (real service_account.json on disk — NOT a regression).
  - line-reminder-bot (sibling repo, prior session): single-source
    push live @ 460291f; LINE quota resets 2026-06-01.

[Next steps]
  - 2026-06-01 Mon 07:50: verify line-reminder-bot single-source push
    fires exactly 1 msg (carried over from 5/29 handoff).
  - Watch issue #8 for Greg's confirmation that manual recovery worked;
    close it once confirmed.
  - admission-line-push SKILL.md still stale (dual-source / GATE_DATE /
    "Claude push 被硬擋") — edit pending user authorization.

[Known issues / blockers]
  - issue #8 fix is FORWARD-ONLY: a bricked install can't auto-update,
    so already-broken users must recover manually once (download zip,
    copy user_data\ into new folder, run new exe).
  - Cannot exercise the real frozen Windows swap on a dev box — only
    PS1 codegen + syntax (PowerShell Parser) + unit tests are verified.

[Don't repeat these mistakes]
  - The 來源有更新 button routes through upstream.sync_source('self'),
    NOT updater.apply directly (both reach _apply_frozen when frozen).
  - The detached swap discards all Write-Host and can't Read-Host — any
    swap change MUST keep the log file + user_data migration + no
    blocking prompt. See [[updater-swap-must-use-powershell]].
  - This repo is PUBLIC; memory/ IS tracked here and another machine
    pushes it. Keep memory PHI-clean. (Skill workflow-docs still says
    public→claude-skills; reality diverged — flagged to user.)

[Relevant files]
  - app/services/updater.py — _write_swap_bat PS1 (log + user_data +
    breadcrumb)
  - tests/test_updater.py — 3 new swap tests
  - CLAUDE.md — Auto-update section rewritten (two-mode)
  - memory/feedback_updater_swap_must_use_powershell.md — #8 lesson

[Important memory files]
  - feedback_updater_swap_must_use_powershell.md (updated, #8)
  - feedback_long_forms_get_bottom_nav.md (salvaged from dropped commit)
