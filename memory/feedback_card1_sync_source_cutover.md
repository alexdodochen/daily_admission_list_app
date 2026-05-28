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

**Don't auto-sync** with any of these on routine work (no proactive clone/diff/pull/push). **Push only when the user explicitly asks** (by name, in the moment — e.g. "push to claude-skills", "請push" after I named the repo, etc.):
- `Key-Schedule-APP` (was Card 1/2 upstream)
- `CV-Schedulling-APP` (was Card 1 reference)
- `claude-skills` (skills + global-memory backup; user did authorize a one-off push 2026-05-29 for the rewritten admission-line-push SKILL.md + LINE quota memories)
- `daily-admission-list` (private workflow mirror)

**Why:** the project repo carries everything routine (incl. `memory/` and `.claude/skills/` mirrored by `/workflow-docs`). Multi-repo reconciliation is retired for routine flows — it was error-prone and the user explicitly ended it. But when a change genuinely belongs in a global store (e.g. a globally-installed skill at `~/.claude/skills/`, not a project-scoped one), the user can lift the freeze on demand.

**How to apply:**
- `/check-previous-progress`: `git fetch` + reconcile ONLY `daily_admission_list_app` origin by default. Do not clone other repos preemptively.
- `/workflow-docs` Step 6: push to `daily_admission_list_app` (and `line-reminder-bot` when work touched it) by default. Skip the claude-skills mirror UNLESS the user explicitly asks this turn.
- If the user says "push" after Claude has named a repo (e.g. "the SKILL.md is at ~/.claude/skills/, won't be pushed") → that counts as explicit authorization for that one push, even though no repo name was repeated verbatim.
- Supersedes the multi-repo porting workflow in [[reference-keyin-upstream]] and [[reference-local-source-repos]] for all routine updates.
