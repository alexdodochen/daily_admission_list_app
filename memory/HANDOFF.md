============================================
  HANDOFF — Last Updated: 2026-05-19 02:55
============================================

[What this session did]
  1. Step 5 cathlab key-in UI de-jargoned (buttons/headings/status →
     plain Chinese + foldable explainer; pdijson/phcjson never shown).
     Name 「翁潘淑琴?」 fixed: backend regex + JS cleanName()/escName()
     display net. Committed + pushed @ 321e95d (CI released
     v20260519-0126-321e95d, success, credential-free).
  2. Found ROOT bug: packaging.spec never bundled app/data/static →
     EVERY shipped exe (incl. 麒翔 9e0a531 zip) had Step 5 broken with
     FileNotFoundError (not just "stale version").
  3. Fixed BOTH ends (user chose 兩段都修):
     - packaging.spec: conditionally bundles app/data/static (local
       Path-B build only; CI checkout lacks it by PHI design)
     - cathlab_service._resolve_static_dir(): DATA_DIR/cathlab_static
       drop-in + frozen drop-spot migration + helpful FileNotFoundError;
       new cathlab_static_status() for a future /settings card
  4. New project skill `.claude/skills/package-distribute/SKILL.md` —
     CI-release vs local-SA-build decision + mandatory Step V verify.
  5. Tests 330 → 332 (2 new cathlab static cases). All green.
  6. Memory: project_cathlab_static_decouple.md added; MEMORY.md +
     no-column-letters-in-ui generalised earlier this session.

[Current state]
  - Branch: main. 321e95d pushed. NEW work (spec + cathlab_service +
    skill + tests + memory) committed locally? NO — pending commit,
    awaiting user "授權 push".
  - CI auto-builds+releases on push:main.
  - Tests: 332 passed.

[Next steps]
  - Commit the spec/cathlab_service/skill/tests/memory changes; push
    (needs explicit "授權 push") → CI emits a corrected release whose
    LOCAL build path can bundle cathlab static.
  - Re-deliver to 麒翔 from the NEW release tag (NOT the 9e0a531 zip):
    send release link + service_account.json + 3 cathlab JSONs
    separately; tell him to drop all into DATA_DIR (see skill Path A).
  - Optional follow-up: wire cathlab_static_status() into /settings as
    a drop-in card (mirror the SA card). Not done this session.
  - Carry-over: /sched real-month solve→手調→套用重算 manual verify.

[Known issues / blockers]
  - Push to main gated by auto-mode classifier — explicit user
    "授權 push" each time.
  - Public CI release intentionally has NO SA and NO cathlab static
    (both PHI). Step 5 only works after the recipient drops the 3 JSONs
    into DATA_DIR/cathlab_static. /settings does not yet surface this.
  - "exe 無法啟動" earlier = port 8766 already bound (an instance was
    running). NOT a build bug.

[Don't repeat these mistakes]
  - Don't trust file mtime for build provenance — only bundled
    app/VERSION sha. (9e0a531 zip looked fresh, was old.)
  - Never un-gitignore app/data/static to "fix" CI Step 5 — leaks PHI.
    [[cathlab-static-decouple]]
  - No engineering jargon in user-facing copy at all.
    [[no-column-letters-in-ui]]

[Relevant files]
  - packaging.spec (datas += app/data/static, conditional)
  - app/services/cathlab_service.py (_resolve_static_dir,
    cathlab_static_status, _load_json error)
  - .claude/skills/package-distribute/SKILL.md (NEW)
  - app/templates/admission.html, app/static/app.js (Step 5 wording)
  - tests/test_cathlab_service.py (+2)

[Important memory files]
  - project_cathlab_static_decouple.md (NEW — the decouple rule)
  - feedback_no_column_letters_in_ui.md (generalised 2026-05-19)
  - project_3card_app_state.md (Phase 14 context)
