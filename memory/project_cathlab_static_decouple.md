---
name: cathlab-static-decouple
description: "Cathlab 3 JSONs are gitignored PHI → resolved at runtime via DATA_DIR drop-in, never in public CI release"
metadata: 
  node_type: memory
  type: project
  originSessionId: 8fe1ad8e-642f-4be4-ae2f-d7318d5aae47
---

The 3 cathlab lookup tables — `cathlab_id_maps.json`, `doctor_codes.json`,
`cathlab_schedule.json` (in `app/data/static/`) — are `.gitignore`d for PHI
(doctor / chart-no maps must not hit the public repo). Consequence chain
discovered 2026-05-19:

- `packaging.spec` originally did NOT bundle `app/data/static` → EVERY
  shipped exe (incl. the 麒翔 9e0a531 zip) had Step 5 導管 key-in broken
  with FileNotFoundError, independent of how stale the build was.
- Fixed by mirroring the service-account decouple (commit `4acbcb8`,
  see [[card1-sync-source-cutover]] era work):
  1. `packaging.spec`: `if os.path.isdir("app/data/static"): datas.append(
     ("app/data/static","app/data/static"))` — fires only on a LOCAL
     Path-B build (dev disk has the files); the public CI checkout does
     not, by design.
  2. `cathlab_service._resolve_static_dir()` search order (updated
     2026-05-19 to match the improved SA drop-in UX):
     DATA_DIR/cathlab_static (persistent, survives auto-update) →
     **DATA_DIR loose** (the 3 files dropped directly next to
     service_account.json — the ONE folder the settings page tells users
     about; migrated into cathlab_static on hit) → frozen
     <exe>/cathlab_static|/static|/ (migrated too) → APP_ROOT/data/static
     (bundled local build / dev) → legacy STATIC_DIR. `_load_json` raises a
     FileNotFoundError naming `DATA_DIR` + "same folder as
     service_account.json" + all 3 filenames.
  3. `cathlab_service.reset_cache()` clears `_static_dir`/`_id_maps`/
     `_doctor_codes`/`_schedule`; wired into `/api/settings/test`
     (alongside appconfig/sheet/scheduling) so files dropped AFTER launch
     are picked up by pressing 測試連線 — no app restart (stale-cache
     parity with the SA fix).
  4. `cathlab_static_status()` exposes {present, source, drop_dir=DATA_DIR,
     files} for a future /settings card (NOT yet wired into the UI).

**Why:** public repo + public GitHub Releases must stay PHI-free, but
Step 5 still needs the maps. Same model as `service_account.json`:
credential/PHI rides in via a DATA_DIR drop-in that auto-update preserves,
never inside the committed/released artifact.

**How to apply:**
- Two distribution paths, see skill `package-distribute`: Path A (CI
  release, credential+PHI-free, recipient drops SA + 3 cathlab JSONs into
  DATA_DIR) vs Path B (local build bundles both, private hand-off only).
- Never un-gitignore `app/data/static` to "fix" CI — that leaks PHI.
- Verify any bundle has the 3 JSONs (or document Step 5 as drop-in) before
  delivery (skill Step V.3).
