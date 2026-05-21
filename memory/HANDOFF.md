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
  - TODO (deferred to a `gh`-equipped machine, per user 2026-05-21):
    close GitHub issues #2-#7. All fixed by d7b3450. `gh` is NOT
    installed on the current machine and credential extraction is
    sandbox-blocked, so this was deferred. On a machine with `gh`
    (gh auth login done), run these 6 commands verbatim:

      gh issue close 2 --repo alexdodochen/daily_admission_list_app --comment "已修 d7b3450 (Phase 19)：(1) 首次抽籤會把子表 H 註記帶入入院序 R 欄；(2) 入院序姓名去除 OCR「?」並用 EMR 校正後的子表名字；(3) 入院序結果「備註(住服)」可點擊編輯並同步回 Sheet；(4) 回報問題按鈕改深色實心（原白字白底看不到）。"
      gh issue close 3 --repo alexdodochen/daily_admission_list_app --comment "已查證目前 5/24 Sheet，子表格解析正確（許春芳在許志新底下），無法重現，研判為當時編輯中途的暫態。相關「主表/子表/入院序數量不符」已隨 d7b3450 修正：重新上傳截圖時主表↔子表會以病歷號自動對帳並補齊。"
      gh issue close 4 --repo alexdodochen/daily_admission_list_app --comment "已修 d7b3450 (Phase 19)：/api/sheet/read 把入院序 N-V 區塊長度誤綁在主表最後一列，N-V 比主表長時尾列(序號10)被切。改成獨立計算 N-V 範圍；③ 整合也會把子表有、入院序卻沒有的病人補進。"
      gh issue close 5 --repo alexdodochen/daily_admission_list_app --comment "與 #4 重複，已於 d7b3450 一併修正，關閉。"
      gh issue close 6 --repo alexdodochen/daily_admission_list_app --comment "已修 d7b3450 (Phase 19)：「與現有排程對照」之前完全不讀預覽表的「排」勾選。verify 現在跟 key in 一樣接收 override，取消勾選的病人不再進入對照與排程。"
      gh issue close 7 --repo alexdodochen/daily_admission_list_app --comment "與 #6 重複，已於 d7b3450 一併修正，關閉。"

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
