============================================
  HANDOFF — Last Updated: 2026-05-29
============================================

[What this session did]
  Cross-project debugging — primary work in the sibling
  `line-reminder-bot` repo (C:\Users\dr\repos\line-reminder-bot),
  not this admission-app codebase.

  1. Diagnosed 5/28 LINE bot daily push failure: cron-job.org
     07:50 + 07:55 both HTTP 500. Render logs revealed
     LineBotApiError 429 "You have reached your monthly limit."
     LINE Free quota (200/month) hit 198 by 5/28.
  2. Two contributors found:
     (a) dual-source push had been pushing 2 msgs per cron call
         (private + public sheet), doubling the daily count;
     (b) OA Manager "自動回應 / AI 智慧聊天" was ON — those
         replies happen on LINE's side and never touch the
         Flask app, so they were invisible to code/logs.
  3. line-reminder-bot commit `460291f`: migrated to
     single-source (public sheet `1u2FZE6-...` only). Pushed,
     Render auto-deploy completed, /health 200 OK.
  4. User toggled OA Manager 回應設定: 聊天, 自動回應, AI
     智慧聊天, 歡迎訊息 → all OFF. Webhook stays ON.
  5. daily_admission_list_app code: NO changes this session.
     Only memory entries added (2 new + workflow note).

[Current state]
  - This repo: main, clean (no code commits this session;
    pending memory commit).
  - line-reminder-bot: main IN SYNC with origin/main @ 460291f.
  - LINE quota: 198/200 used; resets 2026-06-01.

[Next steps]
  - 2026-06-01 Mon 07:50: verify single-source push fires
    (expect exactly 1 msg, not 2).
  - 2026-06 baseline target: < 40 msgs/month.
  - If user authorizes, update
    ~/.claude/skills/admission-line-push/SKILL.md to drop the
    stale dual-source / GATE_DATE / Claude-push-blocked
    sections.

[Known issues / blockers]
  - admission-line-push SKILL.md (in ~/.claude/skills/) is
    stale: describes dual-source + GATE_DATE + "Claude push
    被硬擋" (the push block is gone, verified today).
    Edit pending user authorization.
  - cron-job.org has orphan W0X / R0X jobs returning 404
    (harmless to LINE quota); user said "先不用" leave them.
  - UptimeRobot still pinging /health (user forgot it exists);
    user said "先不用".

[Don't repeat these mistakes]
  - LINE quota issue: rule out cron + /health FIRST (those
    don't burn LINE quota), THEN look at OA Manager dashboard
    settings — auto-reply / Smart Chat replies happen on
    LINE's side, invisible to Flask code and Render logs.
  - When syncing across machines, this user ended multi-repo
    sync on 2026-05-18 — only sync with daily_admission_list_app.
    DO NOT push to claude-skills (per [[feedback-card1-sync-source-cutover]]).
  - When summarising day-of-week behavior: Saturday DOES push
    (Sunday's list via weekend trigger). Don't say
    "Saturday doesn't push" — only the daily trigger skips.

[Relevant files]
  - C:\Users\dr\repos\line-reminder-bot\line_reminder_bot\admission_push.py
  - C:\Users\dr\repos\line-reminder-bot\memory\HANDOFF.md
  - this repo: only memory/* updated, no app code changes.

[Important memory files]
  - feedback_line_quota_oa_manager_hidden_burner.md (NEW)
  - reference_line_messaging_api_free_tier_2026.md (NEW)
