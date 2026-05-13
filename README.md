# 每日入院名單 — 本地版 App

讓每位使用者在**自己的電腦**跑這個工作流程，用**自己的 LLM 帳號**（Claude / Gemini / ChatGPT 任選）當大腦。所有資料、API key、Google 憑證都存在本機 `app/data/config.json`，不上傳任何地方。

> 這是 repo 主工作流的**互動式封裝**。背後仍然使用 `gspread` 對使用者自己的 Google Sheet 寫入，和 Playwright 驅動 EMR / WEBCVIS。

## 1. 安裝

```bash
# 建議用乾淨的 venv
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt

# 如果要用 Step 3 EMR 擷取 / Step 5 導管排程，再裝 Playwright browser
playwright install chromium
```

## 2. 準備自己的帳號

| 項目 | 怎麼拿 |
| --- | --- |
| **LLM API key**（擇一） | Claude：https://console.anthropic.com/ / ChatGPT：https://platform.openai.com/api-keys / Gemini：https://aistudio.google.com/app/apikey（有免費 tier） |
| **Google Service Account JSON** | [Google Cloud Console → IAM → 服務帳戶 → 建立金鑰（JSON）](https://console.cloud.google.com/iam-admin/serviceaccounts) |
| **Spreadsheet ID** | 你的 Google Sheet 網址 `docs.google.com/spreadsheets/d/<這段>/edit` |

> 把服務帳號 email 加入該試算表的「編輯者」權限。

## 3. 啟動

```bash
python -m app.run
```

瀏覽器會自動開到 `http://127.0.0.1:8766/`。第一次會進**設定頁**，填完按「儲存」→「測試連線」→ 兩個都 ✓ 就可以回首頁開始用。

## 4. 六步驟工作流

| 步驟 | 做什麼 |
| --- | --- |
| ① **匯入名單** | 拖曳住院名單截圖 → LLM 辨識成 A-L 欄表格 → 檢視/修正病歷號 → 寫入 Sheet |
| ② **抽籤排序** | 讀主資料 + 抽籤表 → 設定每位醫師籤數 → Round-robin → 寫 N-S |
| ③ **EMR 摘要** | 自己登入 EMR 後貼 session URL → Playwright 帶 session 抓 SOAP → LLM 產 4 段摘要 |
| ④ **入院序整合** | 讀醫師子表格 F/G → 合併回 N-W（保留 V/W 手動標記）；F/G 欄可在頁面直接點擊修改 |
| ⑤ **導管排程** | `plan`（dry-run）/`verify`（登入 WEBCVIS 查漏）/`keyin`（Phase 1 ADD + Phase 2 UPT）；自動帶入時段、房間、第二主治醫師（葉立浩優先） |
| ⑥ **LINE 推播** | 讀 N-Q 四欄 → 預覽 → 推到 LINE group（用自己的 Messaging API token） |

## 4.5 自動更新（多源 upstream check）

App 啟動時背景檢查 3 個 GitHub repo：

| 來源 key | repo | 對應功能 |
| --- | --- | --- |
| `self`      | `alexdodochen/daily_admission_list_app`  | 本 App 自身 |
| `admission` | `alexdodochen/daily-admission-list-public` | 每日入院清單功能源頭 |
| `schedule`  | `alexdodochen/Key-Schedule-APP`          | 排班 + Key 班功能源頭 |

任一來源有新 commit，topbar 右上會顯示「🔔 N 個來源有更新」。點開展開三列，逐源同步：

- `self` → `git pull --ff-only` + 自動重啟（原行為，需要 git checkout 安裝）
- `admission` / `schedule` → `git clone` 或 `git pull` 到 `external/<repo>/`，再依 `app/services/sync_manifest.py` 把白名單裡的「資料型」檔案（如 `cathlab_id_maps.json`、`schedule_readable.txt`）mirror 進 `app/data/static/`

Python / HTML 程式碼變動**不會自動覆寫**——manifest 把它們標 `needs_port`，UI 會列出哪些檔案需要下次手動 port 進對應的 service。

API: `GET /api/update/check_all`、`POST /api/update/sync/{name}`（name = `self|admission|schedule`）。同步狀態存在 `app/data/integration_state.json`。

## 5. 檔案結構

```
app/
  main.py           # FastAPI 路由
  run.py            # 啟動器
  config.py         # 設定 I/O（JSON 存 app/data/）
  llm/
    __init__.py     # get_llm() 工廠 + 三家 provider metadata
    base.py         # LLMClient 抽象 + extract_json
    anthropic_provider.py / openai_provider.py / gemini_provider.py
  services/
    sheet_service.py    # 用使用者的服務帳號 + Sheet ID
    ocr_service.py      # Step 1
    lottery_service.py  # Step 2
    emr_service.py      # Step 3
    ordering_service.py # Step 4
    cathlab_service.py  # Step 5（plan/verify/keyin + schedule/id mapping）
    line_service.py     # Step 6
    updater.py          # 客戶端自動更新
  data/
    static/           # 醫院專屬靜態表（schedule / id maps / doctor codes）
    config.json       # 你的 API key / Sheet ID（gitignore）
  templates/        # Jinja2 HTML
  static/           # CSS + 前端 JS（無框架）
```

## 開發者

```bash
# 執行 pytest（42 個純邏輯測試）
python -m pytest tests/ -v
```

CI 會在 push / PR 時自動跑 pytest（見 `.github/workflows/pytest.yml`）。

## 6. 常見問題

**Q: 我不想用 Claude，只想用免費的 Gemini**
在設定頁選「Gemini (Google)」→ 貼 AIza 開頭的 API key。程式碼自動切換。

**Q: EMR 網址每家醫院不一樣怎麼辦**
`app/services/emr_service.py` 的 `fetch_raw_html()` 是預設用 NCKUH EMR pattern。別的機構請自己改 `page.fill(...)` 的 selector；我們只抽取 `div.small` 內容。

**Q: 可以多人共用一個 Google Sheet 嗎？**
可以。每個人的服務帳號各自加到試算表就行，操作互不干擾（FastAPI 是單人用，不做併發鎖）。

**Q: 我的 API key 會被傳到哪裡？**
只在本機 `app/data/config.json`（純文字 JSON）。要保護請檔案加密或放在 OS keychain，這版沒做。
