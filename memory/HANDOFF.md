============================================
  HANDOFF — Last Updated: 2026-05-21 (Phase 17)
============================================

[What this session did]
  Two batches across 4 commits (e9a06f0 → 6f73d17 → b6b6b0a):

  6f73d17 — Release dead-code purge (~900 lines):
    * external/ + 2 stale .gitignore lines
    * CV_APP_INTEGRATION_HANDOFF.md (5/10 plan, integration done)
    * Reschedule feature fully removed: 4 endpoints + service (195L)
      + test (220L) + WEBCVIS DEL block in cathlab_service (112L)
      + 4 DEL-related tests in test_cathlab_enrich_plan
    * Multi-source upstream trim: sync_manifest.py (95L) + upstream.py
      461 → 354 (_sync_upstream/_run_mirror/EXTERNAL_DIR gone)
    * Kept (per memory directive): /api/step2/{run,write,context}
      legacy lottery endpoints + their 4 service funcs
    * Tests 416 → 396 (only deleted-feature tests removed)

  b6b6b0a — 3-issue field batch + skill enhancement:
    1. UI step3→step2 字眼修正: stepper was renumbered ①-⑤ in Phase 13
       but H2 headings / help text / settings legends still said
       "Step 3/4/5/6". Fixed: admission.html 5 sections + comments,
       base.html 操作說明 6-list + 3 hint lines + bug-modal placeholder,
       settings.html EMR/cathlab/LINE legends + 跳過 note, app.js diff
       confirm message.
    2. Step 1 OCR → ② EMR auto-feed: new renderStep2AutofillPreview()
       shows patient preview table (主治/姓名/病歷號) above EMR textarea
       after step1Write success AND load-existing. JSON textarea moved
       into foldable <details>. Falls back to /api/step4/subtables when
       build_subtables returned empty (already-built case).
    3. 鄭朝允 / 陳淑貞 (1555245) 無一年內門診紀錄 root cause: leftFrame
       click loop did raw `t.includes(variant)`. NCKUH EMR anchor uses
       fullwidth space 「鄭朝允　門診」 → raw substring miss → fall to
       FALLBACK (also miss) → wrong flag. Fix: NFC + strip-all-whitespace
       normalizer applied to BOTH anchor text and every variant/fallback.
       Plus diagnostic: visit_label carries the 門診 anchor texts seen
       when no match found (so future bugs of this shape show their data).

  Skill: /check-previous-progress now auto-fetches open GitHub issues
    every session start. New helper ~/.claude/skills/check-previous-
    progress/github_issues.py reads cwd's git remote, calls
    `repos/{slug}/issues?state=open`, prints one line per issue.
    SKILL.md adds Step 2 (between git fetch + HANDOFF) wiring this
    into the standard session-start summary. Skill lives ONLY on this
    machine (~/.claude/skills is not git-tracked, and sync to
    claude-skills repo is forbidden per the 2026-05-18 cutover).

[Current state]
  - Branch: main, clean, IN SYNC with origin/main @ b6b6b0a
  - Tests: 396 passed (was 416; -20 from removed reschedule + DEL
    tests; no regressions)
  - CI release: b6b6b0a is the latest deliverable. ASCII admission-app.zip
    builds automatically; 麒翔's install picks it up via 🔄 更新.

[Next steps]
  - Field-verify chart 1555245 (陳淑貞 / 鄭朝允) on 麒翔's install
    after CI completes:
      * Should now match the 鄭朝允 visit and write EMR data.
      * If it STILL misses → look at the EMR card's visit_label,
        which now prints "[查無匹配 — 看到 N 筆門診：t1｜t2｜…]" —
        forward that string to me so we can add the missing
        Unicode-sibling pair to NAME_ALIASES + normalizer.
  - Field-verify ① OCR → ② auto-feed: green "✓ 已自動帶入 N 位病人"
    banner + table preview should show above EMR textarea after Step
    1 write. JSON textarea hidden inside foldable 進階.
  - Field-verify UI step-numbering consistency: every section title
    should match the top stepper (no more "Step 3" while in ②).
  - Eyeball the GitHub Issues inbox: next time you /check-previous-
    progress in any repo, the helper auto-prints open issues. Try it
    on a repo that has open issues to confirm formatting.

[Known issues / blockers]
  - 鄭朝允 fix is heuristic (whitespace + NFC). If anchor uses an
    actual Unicode sibling code-point we don't know about yet, the
    diagnostic visit_label string will reveal it; add a NAME_ALIASES
    entry then.
  - ~/.claude/skills is not git-tracked. The github_issues.py helper
    + SKILL.md update lives on THIS MACHINE only. To use on another
    machine, copy ~/.claude/skills/check-previous-progress/ manually
    (or wait for the user to formalize a skill-sync mechanism that
    doesn't violate the 2026-05-18 cutover).
  - Pre-fix sub-tables with wrong-name data still need ONE re-fetch
    after麒翔 updates so 姓名 (col A) gets canonical EMR name via
    the preserve-existing override branch.

[Don't repeat these mistakes]
  - When the stepper gets renumbered, ALSO update every H2 heading,
    help text, settings legend, and JS user-facing message — the
    user sees the mismatch immediately and rightly calls it a bug.
  - JS substring `t.includes(v)` is unsafe across EMR anchors because
    NCKUH inserts fullwidth spaces. Always normalize via NFC + strip
    all whitespace forms before comparing names. [[visit-match-norm-unicode]]
  - When deleting "dead" code that memory says to KEEP as legacy
    (e.g. /api/step2/{run,write,context}), respect the memory directive
    — don't get aggressive just because the user said "you decide".

[Relevant files]
  - app/services/emr_service.py (fetch_raw_html click loop NFC norm
    + diagnostic seen_visits)
  - app/services/upstream.py (461 → 354 trim)
  - app/services/cathlab_service.py (WEBCVIS DEL block removed)
  - app/main.py (4 /api/reschedule/* endpoints removed, imports cleaned)
  - app/static/app.js (renderStep2AutofillPreview, diff confirm copy,
    load-existing autofeed wiring)
  - app/templates/admission.html (H2 renumber + foldable JSON textarea
    + emr-patients-preview div)
  - app/templates/base.html (操作說明 renumber)
  - app/templates/settings.html (legends renumber)
  - ~/.claude/skills/check-previous-progress/SKILL.md
  - ~/.claude/skills/check-previous-progress/github_issues.py (NEW)

[Important memory files]
  - feedback_visit_match_norm_unicode.md (NEW)
