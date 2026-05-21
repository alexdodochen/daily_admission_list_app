============================================
  HANDOFF — Last Updated: 2026-05-21 (Phase 19)
============================================

[What this session did]
  1. Fixed a 6-issue field-bug batch (GitHub #2-#7) from the 5/24 field
     test. Commit d7b3450, pushed to origin/main.
  2. Root cause for #4/#5 ("入院序少一位"): /api/sheet/read sliced the
     N-V ordering block by main_end (main A-L's last row) — when N-V is
     longer than main A-L the trailing 序號 row was truncated.
  3. main↔sub-table reconcile rewrite: _apply_diff_to_subtables now
     reconciles by 病歷號 against the FULL new main list — no duplicate,
     self-heals a drifted sheet.

[Current state]
  - Branch: main, clean (after the docs-sync commit).
  - Latest code commit: d7b3450 (fix batch) — pushed. CI release pending.
  - Tests: 409 passing (was 400).
  - Deploy: pushed to main; recipients pull via in-app 更新 once CI
    publishes the release.

[Next steps]
  - Close GitHub issues #2-#7 — BLOCKED: `gh` not installed locally and
    credential extraction is sandbox-blocked. User must close them
    manually (fix text was provided in chat) OR install `gh`
    (winget install --id GitHub.cli) + `gh auth login` so a future
    session can run `gh issue close`.
  - User's own 5/24 sheet is still desynced (main A-L 9 / sub-table 10,
    許春芳 missing from main). Fix: re-upload the 5/24 screenshot — the
    new reconcile logic repairs it (adds 許春芳 to main, no sub-table dup).

[Known issues / blockers]
  - GitHub issue close is blocked on tooling (see Next steps).
  - #3 (許春芳 mis-attributed to 黃鼎鈞) could not be reproduced — the
    current 5/24 sheet parses correctly. Treated as a transient state.

[Don't repeat these mistakes]
  - N-V ordering extent and main A-L extent are INDEPENDENT — never
    bound one block's row range by the other's last row.
  - When syncing sub-tables on OCR re-upload, dedup by chart_no before
    appending — appending diff.added blindly duplicates rows on a
    desynced sheet.
  - Membership (add/remove) is decided by 病歷號 ONLY — never 姓名/年齡
    (OCR misreads them).

[Relevant files]
  - app/main.py — /api/sheet/read ordering extent; /api/step5/verify overrides
  - app/services/ordering_service.py — clean_name, integrate append + name refresh
  - app/services/lottery_service.py — note → R 備註
  - app/services/ocr_service.py — _apply_diff_to_subtables chart_no reconcile
  - app/services/cathlab_service.py — verify() accepts overrides
  - app/static/app.js — renderOrderResult editable 備註(住服); verify sends overrides
  - app/static/app.css — bug-actions buttons dark; .ord-q-edit states

[Important memory files]
  - feedback_ocr_reupload_membership_only.md (updated — chart_no-only + reconcile)
  - project_3card_app_state.md (Phase 19 entry)
  - MEMORY.md (index updated)
