============================================
  HANDOFF — Last Updated: 2026-05-21 (Phase 19 + 20)
============================================

[What this session did]
  1. Phase 19 — fixed a 6-issue field-bug batch (GitHub #2-#7) from the
     5/24 field test. Commit d7b3450.
  2. Phase 20 — 🐞 bug-report screenshot upload (aca3050); 查閱 viewer
     batch-delete date tabs + live N-V↔sub-table field mirror (dfaa7ab).
  3. Synced docs/memory/handoff (f1adea1, e0e50b1).

[Current state]
  - Branch: main, clean.
  - Latest commit: dfaa7ab (viewer delete + field mirror) — pushed.
  - Tests: 420 passing (was 400 at session start).
  - Deploy: all pushed to main; CI release runs on push. Recipients
    pull via in-app 更新.

[Next steps]
  - TODO (deferred to a gh-equipped machine, per user 2026-05-21):
    close GitHub issues #2-#7 (all fixed by d7b3450). `gh` is NOT on
    this machine. On a machine with `gh` (after `gh auth login`) run:

      gh issue close 2 --repo alexdodochen/daily_admission_list_app --comment "已修 d7b3450 (Phase 19)：(1) 首次抽籤會把子表 H 註記帶入入院序 R 欄；(2) 入院序姓名去除 OCR「?」並用 EMR 校正後的子表名字；(3) 入院序結果「備註(住服)」可點擊編輯並同步回 Sheet；(4) 回報問題按鈕改深色實心。"
      gh issue close 3 --repo alexdodochen/daily_admission_list_app --comment "已查證目前 5/24 Sheet，子表格解析正確，無法重現，研判為編輯中途暫態。相關數量不符已隨 d7b3450 修正（重新上傳截圖會以病歷號自動對帳）。"
      gh issue close 4 --repo alexdodochen/daily_admission_list_app --comment "已修 d7b3450 (Phase 19)：/api/sheet/read 把入院序 N-V 區塊長度誤綁主表最後一列，改成獨立計算；③ 整合也會補進子表有、入院序沒有的病人。"
      gh issue close 5 --repo alexdodochen/daily_admission_list_app --comment "與 #4 重複，已於 d7b3450 一併修正，關閉。"
      gh issue close 6 --repo alexdodochen/daily_admission_list_app --comment "已修 d7b3450 (Phase 19)：「與現有排程對照」現在會接收預覽表的「不排」勾選，取消勾選的病人不再進入對照與排程。"
      gh issue close 7 --repo alexdodochen/daily_admission_list_app --comment "與 #6 重複，已於 d7b3450 一併修正，關閉。"

  - User's own 5/24 sheet was desynced (main 9 / sub-table 10). Fix:
    re-upload the 5/24 screenshot — the chart_no reconcile repairs it.

[Known issues / blockers]
  - GitHub issue close blocked on tooling (no gh, credential extraction
    sandbox-blocked). Deferred to user's gh machine.

[Don't repeat these mistakes]
  - Never `git add -A` here — it grabbed the embedded repo 成大EMR爬蟲
    (now in .gitignore). Stage explicit paths: `git add app/ tests/`.
  - A stale dev server can hold port 8766 → next `python -m app.run`
    fails to bind. Kill via Get-NetTCPConnection -LocalPort 8766.
  - N-V ordering extent ≠ main A-L extent — never bound one by the other.
  - Sub-table F/G/H = cols 6/7/8 collide with main 姓名/性別/年齡 — any
    col-based logic must validate the row against real block row maps.
  - Screenshots can't be PHI-scrubbed → private zip only, never public.

[Relevant files]
  - app/main.py — /api/sheet/delete, propagate calls in cell endpoints
  - app/services/ordering_service.py — propagate_field_edit, clean_name
  - app/services/bug_report.py — write_report_bundle, MAX_IMAGES
  - app/services/ocr_service.py — _apply_diff_to_subtables chart_no reconcile
  - app/static/app.js — viewer delete panel, commitCell mirror, bug images
  - app/static/app.css — del-*, bug-thumb, ord-q-edit styles
  - app/templates/base.html — bug image picker, viewer delete button

[Important memory files]
  - feedback_corresponding_fields_must_mirror.md (new)
  - feedback_ocr_reupload_membership_only.md (chart_no-only + reconcile)
  - project_bug_report_feature.md (screenshot upload)
  - project_3card_app_state.md (Phase 19 + 20)
  - MEMORY.md (index updated)
