---
name: line-quota-oa-manager-hidden-burner
description: When LINE monthly push quota inexplicably exceeds expected count from app code, check OA Manager auto-reply / Smart Chat — they push without going through Flask
type: feedback
---

When `line-reminder-bot` LINE 月推播額度爆掉 (5/28/2026: 198/200 from expected ~30), the deficit is almost never in the Flask app's code path. The hidden burner is the **LINE Official Account Manager** dashboard settings (manager.line.biz):

- **回應設定 → 聊天** — if ON, every group message can trigger an OA-side response
- **回應設定 → 自動回應訊息** — keyword-matched replies, OA-side, each counts as 1 push
- **回應設定 → AI 智慧聊天 (Smart Chat)** — auto-replies driven by LINE's AI, each counts as 1 push
- **加入好友的歡迎訊息** — friend-add welcome msg counts as 1 push per new friend

These reply paths run **inside LINE's infrastructure**, NOT through the Flask `app.py`. The bot's `/webhook-admission` only receives + logs events; it does NOT call `push_message` or `reply_message` in code. So scanning the deployed code or Render logs will not show them.

**Why:** 5/28 burn rate diagnosis: expected ~30/month (1 daily group push × 30 days), saw 198/month. Cron jobs + /health were ruled out, dual-source push only added ~30. Remaining ~100 traced to OA Manager auto-reply being ON (the channel was provisioned with default-on response settings and never explicitly turned off).

**How to apply:** First debug step for "LINE quota exceeded but cron job count looks low" — open https://manager.line.biz/ → 該 OA → 設定 → 回應設定. Confirm 聊天 / 自動回應 / AI 智慧聊天 / 歡迎訊息 are all OFF (only Webhook should be ON for cron-triggered bots). The LINE OA Manager dashboard shows aggregate-only push count under 分析 → 訊息 → 傳送; per-message breakdown is not surfaced, so debugging must work backwards from suspected sources.

Related: [[reference-line-messaging-api-free-tier-2026]]
