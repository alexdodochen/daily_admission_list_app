---
name: fg-combobox-not-select
description: "F/G fields in Step 4 are comboboxes (datalist), NOT strict dropdowns. Custom text flows downstream to Cathlab keyin (OTHERS / 備註)."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 202e121c-0c8f-4e62-891f-fd58ee1476b3
---

User correction (2026-05-14):
> 術前診斷(F) 點擊編輯 預計心導管(G) 點擊編輯 應該要是下拉選單
> [+] 如果我手 key 術前診斷 那你就要去 Webvis 選 OTHERS 然後 keyin
> [+] 如果預計心導管選單沒有那就寫在 webvis 的備註

F/G must be HTML5 `<input list="...">` (datalist) — user can pick from canonical
list OR type free text. Free text MUST survive through to Cathlab keyin (Step 5).

**Canonical options** live in `emr_service.DIAG_RULES` / `CATH_RULES`. Endpoint
`GET /api/options/fg` exposes them as JSON arrays. Frontend builds `<datalist>`
once per page render.

**Free-text downstream routing:**

| Input | Cathlab keyin behavior |
|-------|----------------------|
| F custom (not in DIAG_RULES) | `cathlab_service.resolve_diag` returns `("Others:<text>", OTHERS_PDI)`. WEBCVIS selects "OTHERS" in the diagnosis dropdown and types the label as free text. |
| G custom (not in CATH_RULES) | `cathlab_service.resolve_proc` returns `("", "")`. Existing logic in `attach_cathlab_metadata` appends the unresolved cath text to `note_out`, which becomes the WEBCVIS 備註 field. |

**Implementation notes:**
- The `OTHERS_PDI = "PDI20090908120008"` constant lives in
  `cathlab_service.py`. Don't change without confirming with WEBCVIS schema.
- `resolve_diag` accepts ANY non-empty unresolved text — prefix `Others:`
  automatically if user didn't supply it. Avoids requiring users to type the
  awkward prefix.
- Datalist option order matters: the rendered `<datalist>` simply lists all
  options; browsers may filter as user types. Order = `DIAG_RULES` /
  `CATH_RULES` declaration order (specific-first per module convention).

**How to apply:**
- Never replace F/G UI with a `<select>` (strict dropdown). Free-text path is
  mandatory.
- When adding a new canonical diagnosis: add to `DIAG_RULES` + a corresponding
  entry in `cathlab_id_maps.json` (if it has a real WEBCVIS PDI). If the new
  label is for "Others:" category only, no map entry needed.
