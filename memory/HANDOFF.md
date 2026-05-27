============================================
  HANDOFF — Last Updated: 2026-05-27
============================================

[What this session did]
  1. Step 3 EMR card 4-field row (術前診斷 / 預計心導管 / 註記 / 備註(住服))
     was wrapping to 2 lines on default viewport. Fixed by:
     - Widening main container: max-width 1100px → 1280px.
     - .emr-fg-edit: flex-wrap wrap → nowrap.
     - Wrapped each label+input in <span class="emr-fg-pair">
       (white-space: nowrap) so a label can't break away from its input.
     - Shrunk fg-input inside the pair from 160px → 140px for breathing room.

[Current state]
  - Branch: main, 2 uncommitted CSS+JS edits (about to commit).
  - Latest commit at session start: 2c3ee57 (姓名 col widen + drop E/F/G suffixes).
  - Tests: untouched (pure CSS+markup tweak, no test impact expected).
  - Deploy: pending push after commit.

[Next steps]
  - User to verify on /admission after server restart that the 4 EMR fields
    now sit on one line at typical laptop width.
  - Still-open from prior handoff: gh-equipped machine should close
    GitHub issues #2-#7 (already fixed by d7b3450). Commands in the
    previous HANDOFF — quote them from git history if needed.

[Known issues / blockers]
  - None new this session.

[Don't repeat these mistakes]
  - .emr-fg-edit was using inline-flex with flex-wrap: wrap, which let
    a label text node break away from its <input> mid-row. Always group
    each label+input as a single inline-flex item with white-space: nowrap
    so flex wrapping doesn't tear them apart.
  - From prior handoff (still valid):
    - Never `git add -A` here — pulls in embedded repo. Stage explicit paths.
    - Sub-table F/G/H cols 6/7/8 collide with main name/gender/age cols —
      col-based logic must validate against block row maps.
    - Screenshots can't be PHI-scrubbed → private zip only.

[Relevant files]
  - app/static/app.css (main max-width, .emr-fg-edit, .emr-fg-pair)
  - app/static/app.js (renderEmrResults fgEditor pair wrapping, ~line 1724)

[Important memory files]
  - No memory updates this session — change is captured directly in CSS
    and is self-explanatory from the .emr-fg-pair selector + comment.
