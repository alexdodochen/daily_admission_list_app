---
name: reference-line-messaging-api-free-tier-2026
description: LINE Messaging API monthly push quotas as of 2026 — Free 200, Light 4,000, Standard 25,000
type: reference
---

LINE Messaging API plans (Taiwan, 2026 pricing):

| Plan | Monthly push limit | Monthly fee |
|---|---|---|
| **Free (溝通方案)** | **200 messages** | NT$0 |
| Light (輕用量方案) | 4,000 | NT$590 |
| Standard (標準方案) | 25,000 | NT$1,750 |

Counting unit = one `push_message` / `reply_message` / `broadcast` call per recipient. Group message → 1 unit regardless of group size. HTTP keep-alive endpoints (`/health`) do NOT count.

**View usage**: LINE Official Account Manager (`manager.line.biz`) → channel → 分析 → 訊息 → 傳送. Shows monthly aggregate. Per-message detail is not exposed in the dashboard.

**Where this matters in our cardiology stack**: `line-reminder-bot` runs on Free tier (200/month). Daily admission push + Sat weekend push ≈ 30-35/month at baseline. With OA Manager auto-reply ON or dual-source push enabled, burn rate can hit 150-200/month and trigger 429 on the 28th-29th of a month.

Related: [[line-quota-oa-manager-hidden-burner]] [[admission-line-push]]
