============================================
  HANDOFF — Last Updated: 2026-05-19 03:55
============================================

[What this session did]
  1. Step 5 cathlab key-in UI de-jargoned + name "?" fix (321e95d,
     CI release verified OK).
  2. ROOT bug fixed: packaging.spec never bundled app/data/static →
     Step 5 broke in every shipped exe. Two-ended fix + new skill
     package-distribute (0b4e5d3, Step V verified).
  3. Renamed exe/bundle → 行政總醫師.排班.Key班.入院; release asset
     kept ASCII admission-app.zip (non-ASCII → action-gh-release
     "default.zip"). 3 files synced (spec/release.yml/updater)
     (1f86e70).
  4. Added 使用方法.txt Chinese end-user guide (aae0cdf).
  5. Step V on aae0cdf release found 使用方法.txt landed in _internal/
     (PyInstaller 6.x forces datas there) → FIXED: removed from
     packaging.spec datas, release.yml + BUILD.md now COPY it to the
     bundle ROOT before zip; skill Step V.5 added. NOT yet committed.

[Current state]
  - Branch: main, clean, IN SYNC with origin/main @ e1f9a1a.
  - Latest release v20260519-0316-e1f9a1a — verified deliverable.
  - Scratch cleaned (_wait_verify.py, _verify_release.zip removed).
  - Tests: 332 passed (build-only fixes since; no code change).

[DONE — distribution hardening fully shipped + verified]
  - e1f9a1a pushed; CI release v20260519-0316-e1f9a1a published.
  - Step V on that release: PASS — sha e1f9a1a, exe Chinese name,
    使用方法.txt at bundle ROOT (NOT _internal/), zip ok. Deliverable.

[Next steps]
  - Deliver 麒翔 from v20260519-0316-e1f9a1a: release link +
    service_account.json + 3 cathlab JSONs (at app/data/static/,
    gitignored PHI), all private/separate; "解壓後先讀 使用方法.txt".
    Skill Path A. (NOT yet sent as of this handoff.)
  - Optional: wire cathlab_static_status() into /settings drop-in card.
  - Carry-over: /sched real-month solve→手調→套用重算 manual verify.

[Known issues / blockers]
  - Push to main gated — explicit user "授權 push" each time.
  - RENAME = one-time auto-update break for any pre-rename install
    (needs ONE manual re-download). [[bundle-naming-invariant]]
  - Public CI release has NO SA / NO cathlab static (PHI by design);
    Step 5 needs the 3 JSONs in DATA_DIR/cathlab_static.
  - PyInstaller 6.x onedir forces datas → _internal/; root-level
    files must be copied in the zip step, not via spec datas.

[Don't repeat these mistakes]
  - Don't trust file mtime for build provenance — only bundled
    app/VERSION sha.
  - Bundle naming: 3 files must agree, asset stays ASCII.
    [[bundle-naming-invariant]]
  - Never un-gitignore app/data/static (PHI). [[cathlab-static-decouple]]
  - No engineering jargon in user-facing copy. [[no-column-letters-in-ui]]
  - Always run Step V on the actual released zip before delivery —
    it caught the _internal regression.

[Relevant files]
  - packaging.spec (datas; 使用方法.txt NOT here by design)
  - .github/workflows/release.yml (Copy 使用方法.txt → bundle root)
  - BUILD.md (local copy step), .claude/skills/package-distribute
  - app/services/{updater,cathlab_service}.py, 使用方法.txt
  - app/templates/admission.html, app/static/app.js (Step 5 wording)

[Important memory files]
  - project_bundle_naming_invariant.md
  - project_cathlab_static_decouple.md
  - feedback_no_column_letters_in_ui.md (generalised 2026-05-19)
