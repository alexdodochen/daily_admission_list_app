---
name: feedback-card1-sync-source-cutover
description: "From 2026-05-18 ALL sync is with daily_admission_list_app ONLY — never pull/diff/push Key-Schedule-APP, CV-Schedulling-APP, claude-skills, or any other repo"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 8f6f0aa1-7ff3-4682-bd49-26deb4d1f986
---

User directive (2026-05-18, stated twice, broadened the second time):
> 「以後同步只需要跟 https://github.com/alexdodochen/daily_admission_list_app 不用再跟其他repo同步了」

`https://github.com/alexdodochen/daily_admission_list_app` is now the **single source of truth** for this project — code, memory, HANDOFF, and skills. The Step-5-manual-edit port (2026-05-18) was the LAST sync from `Key-Schedule-APP`.

**Stop syncing from ALL of these** (do not clone / diff / pull / push them for routine work):
- `Key-Schedule-APP` (was Card 1/2 upstream)
- `CV-Schedulling-APP` (was Card 1 reference)
- `claude-skills` (was the skills + global-memory backup)
- `daily-admission-list` (private workflow mirror)

**Why:** the project repo now carries everything (incl. `memory/` and `.claude/skills/` mirrored by `/workflow-docs`). Multi-repo reconciliation is retired — it was error-prone and the user explicitly ended it.

**How to apply:**
- `/check-previous-progress`: `git fetch` + reconcile ONLY `daily_admission_list_app` origin. Do not clone other repos.
- `/workflow-docs` Step 6: push to `daily_admission_list_app` only. Skip the old project→repo map table and the claude-skills mirror.
- Supersedes the multi-repo porting workflow in [[reference-keyin-upstream]] and [[reference-local-source-repos]] for all routine updates.
- Only revisit another repo if the user explicitly asks again, by name, in the moment.
