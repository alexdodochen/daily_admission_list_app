---
name: 格式真理來源 daily-admission-list-public
description: Google Sheet 欄位佈局、SUB_HEADER 命名、N-V 寫入規則的 canonical 來源 repo
type: reference
---

當需要確認 Google Sheet 格式(headers、子表格欄位、N-V 同步邏輯)時,
唯一真理來源是公開的 reference repo:

  https://github.com/alexdodochen/daily-admission-list-public

**讀什麼:**
- `CLAUDE.md` ── 完整欄位佈局 + Rule 1..N + 子表格→N-V 對照表
- `gsheet_utils.py` ── 實際寫入函式(`write_doctor_table`、TEXT format 等)
- `generate_ordering.py` ── N-V 區寫入規則
  注意:`generate_ordering.py` 用的是 6-col 舊佈局(N-S),但 CLAUDE.md
  與 `feedback_subtable_H_to_R_ordering.md` 用 9-col(N-V)。**以 9-col 為準**。
- `memory/feedback_*.md` ── 規則 + 為什麼(歷史踩坑)

**不要混淆的兩個 repo:**
- `daily-admission-list-public` ── 公開,canonical 格式來源(本檔)
- `daily-admission-list` ── 私有,workflow 開發者 memory(HANDOFF.md 提到的)
- 本專案 `daily_admission_list_app` ── 公開,實際打包成 exe 的 UI app

**How to apply:**
- 任何 format 對齊任務(SUB_HEADER 文字、欄位順序、自動修正規則)→ 先讀
  `daily-admission-list-public` 的 CLAUDE.md
- 別寫 code 改 `daily-admission-list-public`,它是唯讀參考
- 2026-05-20:依此來源完成 Phase 18 對齊(H→R sync + SUB_HEADER 中文標準命名)
