---
name: missing-after-must-show-reason
description: "Step 5 'key in 後再查一次' table must explain WHY each patient is missing — never show bare status without a paired reason from Phase-1 add_results."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: ce6d4b16-317d-413d-acf4-d054f69112cf
---

User rule (2026-05-20, verbatim):
> "Key in 後再查一次，有2位沒寫進排程 這裡要顯示原因 不可以只顯示狀態 沒寫進去"

Root cause: `missing_after` was previously just `{chart, name, cath_date}`
with the UI rendering `<td>✗ 沒寫進去</td>` and no diagnostic. Users had
no way to know if it was a code lookup failure, a duplicate skip on
another day, or a Phase-1-success-but-vanished case without opening the
detailed log <details>.

**Fix shape:** `cathlab_service.keyin` now pairs each missing patient with
their matching Phase-1 `add_results` row (keyed by chart) and emits a
`reason` field. The UI adds a 「原因」 column. Mapping:

| Phase-1 result | Reason emitted |
|---|---|
| `error` | The Phase-1 `reason` (e.g. "主治醫師代碼未知：XXX") |
| `skip` | "WEBCVIS 已有這位（already exists on YYYY-MM-DD），未在 <cath_date> 新增" |
| `ok` | "Phase 1 顯示新增成功，但複查時找不到 → 可能 WEBCVIS 介面回退 / 同分鐘衝堂；建議手動核對" |
| (none) | "未進入建立排程流程（請看詳細執行記錄）" |

**Why:** the user is doing post-keyin reconciliation in real time; they
need to act on each missing patient (retry / manually add / accept). A
bare "✗ 沒寫進去" forces them to dig through the log and reason backwards.

**How to apply:**
- Any future "verify-after-write" surface must pair STATUS with REASON
  in the same row, sourced from the write phase's per-item result.
- Never display "沒寫進去" / "失敗" / "missing" as a standalone label.
- This is a specific case of [[diagnose-common-errors-not-raw-traces]] —
  surface actionable hints, not just status flags.
