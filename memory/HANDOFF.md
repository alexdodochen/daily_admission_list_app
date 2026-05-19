============================================
  HANDOFF — Last Updated: 2026-05-19 03:30
============================================

[What this session did]
  1. Step 5 cathlab key-in UI de-jargoned + name "?" fix.
     Pushed @ 321e95d (CI release v20260519-0126-321e95d, verified OK).
  2. Found + fixed ROOT bug: packaging.spec never bundled
     app/data/static → every shipped exe had Step 5 broken
     (FileNotFoundError). Two-ended fix (user: 兩段都修):
     spec conditionally bundles it (local Path-B only) +
     cathlab_service._resolve_static_dir() DATA_DIR/cathlab_static
     drop-in. New skill .claude/skills/package-distribute. @ 0b4e5d3
     (CI release v20260519-0244-0b4e5d3 — Step V verified: sha match,
     plain-language markers present, PHI/SA absent by design, zip ok).
  3b. Added 使用方法.txt (Chinese end-user guide) at repo root,
     bundled at zip root via packaging.spec datas ("使用方法.txt",".").
     3 cathlab JSONs live at app/data/static/ (gitignored, PHI);
     source mirror C:\...\每日入院名單 Claude\.
  3. Renamed exe/bundle → 行政總醫師.排班.Key班.入院 (user request).
     Release asset kept ASCII admission-app.zip (non-ASCII →
     action-gh-release "default.zip"). Updated packaging.spec,
     release.yml (zip/verify/upload/body), updater.RELEASE_ASSET_NAME,
     skill, BUILD.md, CLAUDE.md. Tests 332 green.

[Current state]
  - Branch: main. 321e95d + 0b4e5d3 pushed (CI released both).
  - The rename commit (packaging.spec/release.yml/updater/docs/memory)
    is NOT yet committed — staged, awaiting user "授權 push".
  - Tests: 332 passed.

[Next steps]
  - Commit + push the rename change (needs "授權 push") → CI emits a
    new release whose asset is admission-app.zip and whose exe is
    行政總醫師.排班.Key班.入院.exe.
  - After that CI is success: optionally re-run Step V on the new
    release to confirm exe filename + ASCII asset name.
  - Deliver 麒翔 from that release (NOT 9e0a531 zip): release link +
    service_account.json + 3 cathlab JSONs, all separately, drop into
    DATA_DIR (cathlab → DATA_DIR/cathlab_static). See skill Path A.
  - Optional follow-up: wire cathlab_static_status() into /settings as
    a drop-in card (mirror SA card). Not done.
  - Carry-over: /sched real-month solve→手調→套用重算 manual verify.

[Known issues / blockers]
  - Push to main gated — explicit user "授權 push" each time.
  - RENAME = one-time auto-update break: any pre-rename install
    (folder 每日入院名單, old updater expecting 每日入院名單.zip) can't
    auto-update across this change; needs ONE manual re-download, then
    resumes. Acceptable (麒翔 not yet delivered final).
  - Public CI release has NO SA / NO cathlab static (PHI by design);
    Step 5 needs the 3 JSONs dropped into DATA_DIR/cathlab_static.
  - "exe 無法啟動" earlier = port 8766 already bound, not a build bug.

[Don't repeat these mistakes]
  - Bundle naming: 3 files must agree (packaging.spec name=,
    release.yml zip/files, updater.RELEASE_ASSET_NAME); asset stays
    ASCII. [[bundle-naming-invariant]]
  - Never un-gitignore app/data/static (PHI). [[cathlab-static-decouple]]
  - Don't trust file mtime for build provenance — only bundled
    app/VERSION sha.
  - No engineering jargon in user-facing copy. [[no-column-letters-in-ui]]

[Relevant files]
  - packaging.spec (name=, datas app/data/static)
  - .github/workflows/release.yml (zip ASCII / verify / body)
  - app/services/updater.py (RELEASE_ASSET_NAME=admission-app.zip)
  - app/services/cathlab_service.py (_resolve_static_dir, status)
  - .claude/skills/package-distribute/SKILL.md
  - BUILD.md, CLAUDE.md (paths), app/templates/admission.html,
    app/static/app.js (Step 5 wording), tests/test_cathlab_service.py

[Important memory files]
  - project_bundle_naming_invariant.md (NEW)
  - project_cathlab_static_decouple.md
  - feedback_no_column_letters_in_ui.md (generalised 2026-05-19)
