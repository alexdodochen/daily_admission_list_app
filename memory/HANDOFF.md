============================================
  交班文件 — Last Updated: 2026-05-20 evening (Phase 18)
============================================

【本次 session 做了什麼】
  1. clone 公開 repo daily_admission_list_app 到 ALL APP Developer 目錄
  2. Phase 18 — 對齊 daily-admission-list-public 的 Sheet 格式:
     a) 子表格 H 註記 → N-V R 備註 sync (H 空時保留 R 手填)
     b) SUB_HEADER 中文標準命名 (summary → EMR摘要、入院序 → 手動設定入院序)
     c) format_check_service 新增 sub_header_wrong 偵測 + 自動修正
     d) app.js ORDER_HEADER 由 10-col 修正為 9-col N-V (刪 每日續等清單)
  3. /workflow-docs 更新 memory + CLAUDE.md + HANDOFF (本檔)

【當前狀態】
  - Working dir: C:\心臟內科總醫師\行政總醫師\ALL APP Developer\daily_admission_list_app
  - Branch: 預設 main(fresh clone) — 尚未 commit/push 本次變更
  - Tests: 289 non-cathlab passing / 37 cathlab failing(fresh clone
    缺 PHI gitignored JSONs,屬預期,非本次新增的問題)
  - 部署狀態: 未部署;exe 也未重 build
  - 對應 GitHub: https://github.com/alexdodochen/daily_admission_list_app.git

【下一步該做什麼】
  - 等使用者確認後 commit + push 本次變更到 origin/main
  - 若要上線:回 BUILD.md 流程
      cp service_account.json app/bundled/
      pyinstaller packaging.spec --noconfirm
      → release admission-app.zip
  - 或使用者直接在現有 install 按「更新」按鈕拉新版

【已知問題 / 卡關】
  - 37 cathlab tests 在 fresh clone 上 FAIL(FileNotFoundError):
    需從私有來源放入 cathlab_id_maps.json / doctor_codes.json /
    cathlab_schedule.json 才能跑(屬永久狀態,CLAUDE.md Phase 11 章節有說明)

【不要重蹈覆轍】
  - 「NU欄」這種模糊欄位簡稱要先確認 — 本次差點誤判,使用者最終澄清是
    N-V ordering area 內的 R 欄
  - 改 SUB_HEADER 要同時改 4 處:subtable_service / ocr_service / app.js /
    format_check_service.EXPECTED_SUB_HEADER。漏一個就會在某個流程顯示舊標籤
  - R 欄同步邏輯不能無腦覆蓋,要 `H if H else R`,否則使用者手填會被清掉
  - daily-admission-list-public 是 read-only 參考,別 push 改動上去

【相關檔案】
  - app/services/ordering_service.py — H→R sync 兩處
  - app/services/subtable_service.py:19-20 — SUB_HEADER
  - app/services/ocr_service.py:348-349 — SUB_HEADER
  - app/services/format_check_service.py — EXPECTED_SUB_HEADER + 新檢查
  - app/static/app.js — SUB_HEADER + ORDER_HEADER + ORDER_COLS
  - tests/test_ordering_service.py — +3 新測試
  - tests/test_format_check_service.py — +1 新測試 + _fake_read_range 更新
  - CLAUDE.md — Phase 18 段落 + SUB_HEADER 真理來源句

【重要 memory 檔】
  - feedback_subtable_h_to_r_ordering.md (新)
  - reference_format_source_of_truth.md (新)
  - project_3card_app_state.md (Phase 18 段落)
  - MEMORY.md (索引更新)
