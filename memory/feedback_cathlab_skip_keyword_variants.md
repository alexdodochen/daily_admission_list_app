---
name: cathlab-skip-keyword-variants
description: "Step 5 註記 skip keywords must cover 不排導管 / 不排程 / 不排 cath / 不做導管 variants — not just 不排程."
metadata:
  type: feedback
---

User correction (2026-05-21):
> 我有時候備註不排導管 還是會被系統抓去排導管 請檢察原因

The UI placeholder literally suggests `不排導管` as an example, but the
backend's `SKIP_KEYWORDS` was `["不排程", "檢查"]` — `不排導管` does NOT
contain `不排程` as substring, so it slipped through.

**Why:** The UI told users to type `不排導管`, but the backend silently
matched only `不排程`. The placeholder was the contract; the backend was
out of sync with it.

**How to apply:**
- `SKIP_KEYWORDS` now covers `["不排", "不做", "取消", "檢查"]` (catches 不排程,
  不排導管, 不排 cath, 不做導管, 不做 cath, 取消導管…).
- `_SKIP_NEGATIVE = ["不排除"]` prevents false-positive on `不排除做導管`.
- Single entry point: `cathlab_service.note_means_skip(note)` — never use
  raw `any(k in note for k in SKIP_KEYWORDS)` again (loses the negative-list
  protection).
- When adding a new skip pattern, update `SKIP_KEYWORDS` + the UI placeholder
  at `app.js` `noteInput()` placeholder string. Keep the two in sync.
- Tests live in `tests/test_cathlab_service.py::test_note_skip_*`.
