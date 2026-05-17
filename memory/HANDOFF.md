============================================
  交班文件 — Last Updated: 2026-05-17 (session end, machine B)
============================================

【本次 session 做了什麼】
  1. 接續 5/14 session：把 machine B 的 test fix (resolve_diag OTHERS_PDI
     對齊) rebase 到 origin 之上。origin 這 3 天已前進 Phase 11/12/13。
  2. Rebase 衝突解法：origin 的 Phase 11-13 已獨立修好同一個 resolve_diag
     測試 (test_resolve_diag_unknown_falls_back_to_others_pdi)，採用 origin
     版本（命名/註解較佳），只保留 machine B 獨有的 test_resolve_diag_empty
     ("" / 空白 → ("", "")) 補洞。rebased commit 縮成 +5 行。
  3. 把散落 D:\public_daily_admission_app_stage 搬進
     CV ALL APP\archive\ (5/14 做的，沿用)。

【當前狀態】
  - Branch / Worktree: main, ahead 1 (60338a9 待 push)
  - 最新 origin commit: 1570ac2 feat: Phase 13 — F/G UX overhaul,
    plan-section detect, Card 1 alignment, drafts
  - 本機 HEAD: 60338a9 test: align resolve_diag tests (rebased on 1570ac2)
  - 測試: pytest tests/ 全綠 (332 passed) — 比 5/14 的 289 多 43 個
    (Phase 11-13 帶進來的)
  - dev server: 未啟動

【Phase 11/12/13 摘要 (這 3 天 machine A 做的，本 session 只 rebase 沒改)】
  - Phase 11 (e677302): Card 2 (Key 班) 已 port — 之前最後一張 pending
    card 完成；N-V auto-sync；auto sub-table
  - Phase 12 (a2429fa): chart-no 強制 TEXT format；EMR 只走 mainFrame；
    viewer 可編輯；topbar 統一
  - Phase 13 (1570ac2): F/G UX 大改；plan-section 偵測；Card 1 對齊；drafts

【下一步該做什麼】
  1. push 60338a9 到 origin/main (本 session 已授權，等 auto-mode 過 /
     使用者用 ! 跑)
  2. 使用者實機驗證 Phase 11-13 三張 card：
     - Card 2 (Key 班) port 後第一次跑 — 確認 keyin 流程能動
     - Phase 12 EMR mainFrame-only 改動後，Step 3 還能不能抓到 SOAP
     - Phase 13 F/G UX 改版後，Step 4 datalist + plan-section 是否正常
  3. Phase 10 既有待驗 (Step 1→2→3 writeback、Step 4 三層 pin) 仍未實機驗

【已知問題 / 卡關】
  - cathlab 靜態 JSON 在 _public_repo/app/data/static/ **本機已存在**，
    332 passed 已證明。任何 HANDOFF 提到「從 C:\Users\dr\Downloads\Y\
    每日入院名單 Claude\ copy 三個 JSON」= machine A 路徑，machine B 不適用。
  - SA private key (0612bef3...) 之前外洩，使用者選不 rotate；用的是
    dailyadmission-62eb7b48d0e0.json
  - _public_repo stash@{0} (pre-rebase-2026-05-13) — 已驗證和 origin 重複，
    可 drop (使用者 5/14 已授權 cleanup)

【不要重蹈覆轍】
  - 不要把 Step 2 改回 lottery [[step2-no-lottery]]
  - 不要把 F/G 改回 `<select>` [[fg-combobox-not-select]]
  - 不要把三層 pin 揉成一欄 [[pin-layers-separated]]
  - 不要假設 NCKUH EMR DOM 是平的，永遠 frame-walk [[nckuh-emr-frameset]]
  - Step 3 endpoint 永遠要 sheet writeback [[step3-must-writeback]]
  - 跨機器讀 HANDOFF 不要直接信路徑 — C:\Users\dr\ (A) vs C:\Users\user\
    (B)；先 ls + pytest 確認
  - 不要把 auto-memory mirror 進 _public_repo — 是 PUBLIC repo，auto-memory
    有姊妹專案的病歷號/姓名
  - rebase 前一定 git fetch — origin 3 天可前進好幾個 Phase；diverged 時
    優先採 origin 版本，只保留本機獨有的補洞

【相關檔案】
  - tests/test_cathlab_service.py (rebased：保留 test_resolve_diag_empty)
  - tests/test_cathlab_enrich_plan.py (rebased：採 origin 版本)
  - app/ — Phase 11-13 大量改動 (Card 2 keyin、EMR mainFrame、F/G UX)；
    本 session 未改 app code，僅 rebase

【重要 memory 檔】
  - machine B auto-memory: project_cv_all_app.md (本 session 更新 — Phase
    11-13 + card 2 done + 332 passed)
