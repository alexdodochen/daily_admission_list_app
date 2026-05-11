"""
規範哪些上游檔案可以「自動 mirror」進 App 的靜態資料夾，哪些是「需要開發者
手動 port」的程式碼。

設計原則：
  - auto_mirror 只放結構穩定的資料檔（JSON / TXT），不放 .py / .html。
    被 mirror 的檔案會直接覆寫 app/data/static/<dest>，所以 schema 變動會立即
    影響執行中的 App——加入 manifest 前要確定上游不會破壞性修改。
  - needs_port 純粹是給 UI 提示「上游這支檔變了，下次手動 review/port 進這
    些 App 程式碼」。不會有任何自動寫入。

mirror 路徑解析：dest 一律相對於 DATA_DIR（dev: app/data/，frozen: <exe>/user_data/）。

兩個上游 repo 的對應關係詳見上方各區塊。
"""

MANIFEST: dict[str, dict] = {

    # ----------------------------------------------------------------
    # 入院清單上游：alexdodochen/daily-admission-list-public
    # ----------------------------------------------------------------
    "admission": {
        "auto_mirror": [
            # 導管 ID 對應表（66 diag + 22 proc）。schema 是兩層 dict，多年穩定。
            # cathlab_service._load_json("cathlab_id_maps.json") 直接讀。
            ("cathlab_id_maps.json", "static/cathlab_id_maps.json"),
            # 主治醫師導管時段表 readable 版本（人讀的，docs/規則參考用）
            ("schedule_readable.txt", "static/schedule_readable.txt"),
        ],
        "needs_port": [
            # (上游檔, App 對應位置, 說明)
            ("process_emr.py",       "app/services/emr_service.py",
             "EMR 抓取 + parsing 邏輯；含 age/gender header 處理"),
            ("cathlab_keyin.py",     "app/services/cathlab_service.py",
             "WEBCVIS keyin 流程、DOCTOR_CODES、ROOM_CODES、_normalize_diag"),
            ("verify_cathlab.py",    "app/services/cathlab_service.py",
             "WEBCVIS 查漏（verify 階段）邏輯"),
            ("webcvis_del.py",       "app/services/cathlab_service.py",
             "WEBCVIS 刪除 / reschedule 用的 chk-checkbox 流程"),
            ("webcvis_query.py",     "app/services/cathlab_service.py",
             "WEBCVIS 查詢支援"),
            ("schedule_lookup.py",   "app/services/cathlab_service.py",
             "主治醫師導管時段表 lookup helper（依 weekday 解析時段+房間+第二主治）"),
            ("lottery_utils.py",     "app/services/lottery_service.py",
             "抽籤+round-robin 工具"),
            ("generate_ordering.py", "app/services/ordering_service.py",
             "Step 4 入院序整合（從子表格 F/G 合併回 N-W）"),
            ("fetch_emr.py",         "app/services/emr_service.py",
             "Playwright EMR session 帶入 + 抽 SOAP"),
            ("rebuild_date_sheet.py", "app/services/format_check_service.py",
             "日期分頁版面重建（borders / 寬度）"),
            ("backfill_emr_age_gender.py", "app/services/emr_service.py",
             "歷史資料補 age/gender 的 batch script"),
            ("emr_helpers.js",       "app/static/app.js（行內編輯/diff 用）",
             "前端 EMR 子表格 helper（contenteditable + diff）"),
            ("emr_toggle_script.js", "app/static/app.js",
             "EMR 折疊區段切換腳本"),
            ("docs/admission_workflow_dev_en.md", "docs/—",
             "入院流程開發者文件（整體規則）"),
            ("docs/webcvis_form_fields.md",       "docs/—",
             "WEBCVIS 表單欄位對應（keyin + verify 用）"),
        ],
    },

    # ----------------------------------------------------------------
    # 排班 / Key 班上游：alexdodochen/Key-Schedule-APP
    # ----------------------------------------------------------------
    "schedule": {
        "auto_mirror": [
            # 暫無：cv_solver / keyin_* 都是邏輯模組，不適合直接覆寫進 App。
        ],
        "needs_port": [
            ("cv_solver.py",          "app/services/scheduler_service.py（待新建）",
             "排班 backtracking solver（純函式模組，可直接 vendor）"),
            ("keyin_routes.py",       "app/main.py + app/services/keyin_service.py（待新建）",
             "Key 班 FastAPI routes（要拆成 main.py 路由 + service 純邏輯）"),
            ("keyin_scheduler.py",    "app/services/keyin_service.py（待新建）",
             "Key 班排程演算法"),
            ("keyin_excel_parser.py", "app/services/keyin_service.py（待新建）",
             "Key 班 Excel 匯入/輸出"),
            ("auth.py",               "(略過：本 App 走 bypass)",
             "Key-Schedule-APP 的登入；本 App 用 synthetic admin 不 port"),
            ("audit.py",              "(評估後再決定)",
             "稽核 log；本 App 暫無對應功能"),
            ("gsheet_io.py",          "app/services/sheet_service.py",
             "Google Sheet I/O wrapper（已有對應，比對差異即可）"),
            ("templates/schedule_gen.html", "app/templates/schedule.html（待新建）",
             "排班結果展示頁"),
            ("templates/keyin_index.html",  "app/templates/keyin.html（待新建）",
             "Key 班主頁"),
            ("templates/home.html",         "app/templates/index.html",
             "上游的 home cards UI 範例（3-feature scope 規劃時參考）"),
        ],
    },
}
