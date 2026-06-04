---
name: project-line-push-kill-switch
description: LINE admission auto-push has a code-level kill switch (PUSH_ENABLED) in line-reminder-bot; cron-job.org "disabled 6/02" note was unreliable.
metadata:
  type: project
---

LINE 入院名單自動推播有**兩道防線**（2026-06-04）:

1. **cron-job.org** — 真正的觸發器（每日 07:50/07:55 打 Render endpoint）。在
   `alexdodochen` 的 cron-job.org 帳號裡，**只有 user 能在 dashboard 開關**。User
   於 2026-06-04 手動把這些 job 停用。
2. **程式層 kill switch** — `line-reminder-bot/line_reminder_bot/admission_push.py`
   的 `PUSH_ENABLED`（commit `3e793ee`）。預設 **False = 不推**；`push_admission_list`
   / `push_admission_weekend` 開頭即 return `[DISABLED]`，不讀 sheet、不打 LINE。
   要重開：Render env var `ADMISSION_PUSH_ENABLED=1`（或 `true`/`yes`）後重新部署。

**坑（重要）**: 2026-06-02 的 HANDOFF/CLAUDE.md 寫「cron jobs ALL DISABLED」，但
user 2026-06-04 仍收到自動推播 → 那次 cron 停用其實**沒生效/沒做完**（user 6/04 才
手動補停）。教訓：不要只信文件裡的「cron 已關」記錄；cron-job.org 是外部狀態，無法
從 code 驗證。真正可靠且可驗證的關閉手段是程式層 `PUSH_ENABLED`。相關推播設計見
[[feedback-line-quota-oa-manager-hidden-burner]]。
