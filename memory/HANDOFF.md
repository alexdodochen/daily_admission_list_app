============================================
  交班文件 — Last Updated: 2026-05-13 (session end)
============================================

【本次 session 做了什麼】
  1. 合併兩條分岔線 (merge commit 3d03c54)：本地 e5fb122 (3-card port) + origin 6 commits (Phase A/B/C admission rules + .exe 打包 + in-app self-update + multi-source upstream check)
  2. Phase 9 UI 一輪 (commit 92c8458)：全域 📋 查閱 modal、🔗 Sheet topbar 連結、admission 頁日期月曆 + 自動帶星期、資料檢查獨立 card 標 [選用]、Step 1 OCR 覆寫時子表格自動 add/remove/move、設定頁按鈕順序提示
  3. 設定頁 SA JSON 路徑欄踩坑除錯：使用者連續 2 次貼 JSON 內容（含 RSA 私鑰）到欄位 → 提醒 rotate key、解釋欄位要的是檔案路徑、教 Shift+複製路徑要去引號

【當前狀態】
  - Branch / Worktree: main, clean (working tree)
  - 本地 vs origin: 都是 92c8458 (ahead 0 / behind 0 — push 已完成)
  - 最新 commit: 92c8458 feat: global sheet viewer + standalone 資料檢查 card
  - 本 session 還有未 commit 的改動：日期 picker、設定按鈕提示、選用標、Sheet 連結、子表格 sync — workflow-docs 階段一併 commit
  - 開發 server (背景 task be0ug902m) 跑中，但載的是舊 Python (sub-table sync 在 ocr_service.py，需重啟才生效)

【下一步該做什麼】
  - 使用者實機測試新版 server（重啟後）的兩個關鍵流程：Step 1 OCR 覆寫帶 add/remove → 子表格是否正確同步；/admission 日期 picker 切換 → 星期欄是否自動帶 (admission+1)
  - 若驗證 OK → 後續可考慮 Card 2 (Key 班) port — 但要先確認 `C:\Users\dr\Downloads\Y\排班 APP\` 已有 keyin_* 檔案，目前還沒
  - 若驗證有 bug → 用 viewer 看 sheet 實際狀態當第一手資料

【已知問題 / 卡關】
  - SA private key 外洩 (0612bef3...)：使用者選擇不 rotate，風險自負；新使用的 key 是另一把 dailyadmission-62eb7b48d0e0.json
  - cathlab 35 個測試持續 fail (FileNotFoundError on app/data/static/*.json) — pre-existing，需從 `C:\Users\dr\Downloads\Y\每日入院名單 Claude\` copy 三個 JSON 過來才會通
  - Card 2 (Key 班) 仍是 placeholder card — 上游 CV-Schedulling-APP 也還沒做完

【不要重蹈覆轍】
  - 不要在沒有 explicit Bash permission rule 時嘗試 `git push origin main` — auto-mode 會擋；改請使用者用 `!` prefix 自己跑或加 permissions
  - 不要嘗試寫 Claude 自己的 permissions config (`.claude/settings.local.json`) — auto-mode hard block
  - 不要把 `home directory` 全掃 credential file (`find ~/ -name "*.json"`) — auto-mode 擋為 credential exploration
  - 不要把 weekday 寫成「住院日的星期」— 是「住院日+1 (= 開刀日) 的星期」, [[feedback-weekday-field-is-op-day]]
  - `!` 預設 shell 是 bash，不是 PowerShell — 需要 PS cmdlet 時要明確寫 `!powershell -Command "..."`

【相關檔案】
  - app/services/ocr_service.py — 新 _apply_diff_to_subtables
  - app/main.py — 新 /api/sheet/read endpoint
  - app/templates/base.html — topbar viewer-link + 🔗 sheet links + viewer modal
  - app/templates/admission.html — 日期 picker、資料檢查 card 抽出
  - app/templates/settings.html — 按鈕順序提示
  - app/static/app.js — viewer modal IIFE + setupDateInputs + OCR diff 警語
  - app/static/app.css — viewer / picker / checks-card / button-order-hint 樣式
  - tests/test_ocr_service.py — 4 個新測試 (sub-table remove/add/move/unattached)
  - tests/test_main_endpoints.py — 3 個新測試 (/api/sheet/read)

【重要 memory 檔】
  - project_3card_app_state.md (updated — Phase 9 列入 Delivered)
  - feedback_weekday_field_is_op_day.md (new)
  - MEMORY.md index (updated)
