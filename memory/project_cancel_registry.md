---
name: cancel-registry
description: "Cooperative cancellation pattern for long-running ops (Step 3 EMR batch, Step 5 cathlab keyin). New ops MUST integrate via cancel_registry."
metadata:
  type: project
---

User correction (2026-05-21):
> 所有功能都要新增取消鍵 就是已經跑到一半了 你要讓我可以取消

**Why:** Step 3 EMR + Step 5 cathlab keyin can run several minutes per batch.
Before this fix, the user had no way to stop mid-batch — clicking refresh
left the browser orphaned and partial results stranded.

**Pattern:**
1. Endpoint creates `op_id` (e.g. `step3_{date}` / `step5_{date}`) and calls
   `cancel_registry.start(op_id, meta)` at entry. In `finally` calls
   `cancel_registry.finish(op_id)`.
2. Long-running async function accepts `op_id` kwarg, polls
   `cancel_registry.is_canceled(op_id)` at safe checkpoints (between
   iterations, before each WEBCVIS write), breaks out on True.
3. New endpoint `POST /api/op/cancel` (with `op_id` form param) calls
   `cancel_registry.request_cancel(op_id)`.
4. UI: shows a red ✕ 取消 button while busy. Click → POST /api/op/cancel.
   Wait for the next checkpoint; partial results returned to caller.

**Where to put checkpoints:**
- Between iterations of any `for patient in patients` loop.
- Between phases (e.g., Step 5 has Phase 1 ADD + Phase 2 UPT — check before each).
- NOT inside Playwright sub-actions like clicking a button — let those
  complete to avoid leaving the WEBCVIS page in a partial state.
- NOT inside a single Sheets `batch_write_cells` — Sheets atomically commits
  or doesn't.

**Result contract:**
- Endpoint returns 200 with partial results + `canceled: bool` field.
- UI distinguishes canceled-vs-normal-completion in the flash message.
- Already-completed writes (WEBCVIS rows, Sheets cells) are NOT rolled back.

**What's wired:**
- `/api/step3/run` → `emr_service.extract_patients(op_id=...)`
- `/api/step5/keyin` → `cathlab_service.keyin(op_id=...)` (dry_run skips registration)
- `/keyin/api/*` (Card 2) — already had its own cancel via WebSocket; not migrated.

**Don't:**
- Don't switch to `asyncio.Task.cancel()` — partial Playwright cleanup is
  unreliable when CancelledError fires mid-await. Cooperative checkpoints
  give us deterministic close-browser + return-partial.
- Don't use a different op_id format than `step{N}_{date}` — UI hardcodes this.
- Don't try to cancel a `dry_run` operation — those don't register an op_id.
