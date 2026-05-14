============================================
  交班文件 — Last Updated: 2026-05-14 (session end)
============================================

【本次 session 做了什麼】
  1. Phase 10 工作流程重新切分：Step 2 改成「生成 subtable（依主表順序）」(新 subtable_service.py)；
     Step 4 改成「抽籤 + 3 層 pin 寫入 N-V」(lottery_with_pins) — 病人 pin / 醫師 pin / E 欄內排序分三層獨立
  2. EMR 三大修：(a) frameset 改用 frame-walk + #txtChartNo/#BTQuery + FALLBACK_DOCTORS (b) 補上 sheet
     writeback (sheet_service.batch_write_cells + emr_service.write_results_to_subtables) (c) F/G 改 datalist
     combobox，custom 字串走 OTHERS_PDI / 備註
  3. UI 通用化：withBusy() 包 14 顆 async 按鈕，cache-buster ?v={timestamp}，viewer 看全部工作表，
     設定頁加 Gemini RPM/RPD/TPM 對照表

【當前狀態】
  - Branch / Worktree: main, dirty (workflow-docs 流程內 commit + push 中)
  - 部署/執行狀態: dev server (PID 19464) 跑在 127.0.0.1:8766，最新版本 cache-buster v=1778754719
  - 最新 commit: 5323350 feat: Phase 9 UI usability + sub-table auto-sync + HANDOFF
  - 本 session 變動：10 個檔（含新增 subtable_service.py），待 commit

【下一步該做什麼】
  - 使用者實機驗證：(a) Step 1 OCR → Step 2 生成 subtable → Step 3 EMR 是否 C/F/G 寫回 sheet
    (用 viewer 點該日期分頁看 sub-table C 欄有沒有 "<age> y/o <gender>\n<truncated SOAP>") (b) Step 4
    pin 三層是否如預期 — 試填病人 pin = 某人第 1 位，醫師 pin = 某醫師第 1 順位，跑「② 首次抽籤」，
    看 N-V 結果
  - 若 EMR fetch 還是抓不到 (visit_label 為空)：很可能 frame 名不是 topFrame/leftFrame/mainFrame；
    我的實作用 frame-walk 兜底，但可能找不到 #txtChartNo — 看 Playwright console 確認
  - F/G 自填走 OTHERS_PDI 的 cathlab keyin 路徑 — 還沒實機驗證過 WEBCVIS 是否真的會選 OTHERS

【已知問題 / 卡關】
  - cathlab 35 個 pytest 仍 fail (app/data/static/*.json 缺) — pre-existing，要從 `C:\Users\dr\Downloads\Y\
    每日入院名單 Claude\` copy 三個 JSON (cathlab_id_maps / doctor_codes / cathlab_schedule) 過來
  - Step 2 build_subtables 拒覆寫已存在 subtable — 若使用者想重建，得手動清掉 sub-table 區或走 Step 1
    OCR 覆寫的 diff 路徑

【不要重蹈覆轍】
  - 不要把 Step 2 改回 lottery — 使用者明確要求 Step 2 = 純結構 (build subtable)、Step 4 = 決策 (抽籤)
    [[step2-no-lottery]]
  - 不要把 F/G 改回 `<select>` 嚴格下拉 — 必須是 datalist combobox 允許自填 [[fg-combobox-not-select]]
  - 不要把三層 pin 揉成一欄 — E (within-doctor) / patient pin / doctor pin 是獨立概念 [[pin-layers-separated]]
  - 不要假設 NCKUH EMR DOM 是平的 — 永遠用 frame-walk pattern [[nckuh-emr-frameset]]
  - Step 3 endpoint 永遠要做 sheet writeback — `extract_patients` 只回 data，writeback 是 endpoint 責任
    [[step3-must-writeback]]
  - 寫 console.log 之類前端 debug 訊息看不到，因為使用者沒開 DevTools — 用 flash() 訊息或 alert()

【相關檔案】
  - app/services/subtable_service.py (NEW) — build_subtables_from_main
  - app/services/lottery_service.py — lottery_with_pins (rewritten with 3-layer pin)
  - app/services/emr_service.py — fetch_raw_html (frameset walk + FALLBACK_DOCTORS), write_results_to_subtables
  - app/services/cathlab_service.py — resolve_diag (any unresolved → OTHERS_PDI)
  - app/services/sheet_service.py — batch_write_cells
  - app/main.py — /api/step2/build_subtables, /api/step4/lottery, /api/sheet/raw, /api/options/fg, _STATIC_VERSION
  - app/static/app.js — withBusy, fgInput/Datalist, renderPinPanels, lottery handler with patient_pins+doctor_pins
  - app/static/app.css — button.busy spinner, input.fg-input, .pin-panel, .provider-table
  - app/templates/admission.html — Step 2/4 panel rewrites
  - app/templates/base.html — viewer modal (查閱 Google Sheet), cache-buster ?v={static_version}
  - app/templates/settings.html — Gemini info <details>

【重要 memory 檔】
  - project_3card_app_state.md (updated — Phase 10 列入 Delivered)
  - feedback_step2_no_lottery.md (new)
  - feedback_pin_layers_separated.md (new)
  - feedback_fg_combobox_not_select.md (new)
  - feedback_step3_must_writeback.md (new)
  - reference_nckuh_emr_frameset.md (new)
  - reference_gemini_free_tier.md (new)
  - MEMORY.md index (updated — +6 lines)
