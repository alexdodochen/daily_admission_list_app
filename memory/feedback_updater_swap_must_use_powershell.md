---
name: updater-swap-must-use-powershell
description: "Windows in-place updater for Chinese-path installs must drive the post-restart swap via PowerShell .ps1, NEVER cmd .bat with Chinese paths. tasklist|find parsing is unreliable."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 9db9da1c-30f7-4824-888b-4b74c6d0cfaa
---

The self-updater's "wait for old exe to die, rename folder, relaunch new
exe" step must be written as a PowerShell `.ps1` invoked from a tiny
ASCII `.bat` shim. Never embed Chinese paths or `tasklist`/`find` parsing
inside a `.bat`.

**Why:** on 2026-05-20 three consecutive .bat-based implementations
bricked installs:

1. `a68c3da` — UTF-8 `.bat` + `chcp 65001` + `find /I "<IMAGENAME>"`.
   cmd.exe parses .bat in the OEM codepage (CP950 on TW Windows) BEFORE
   chcp takes effect → Chinese exe name became mojibake (鈞蝮虜揮…) →
   find never matched → wait loop forever.
2. `4eae323` — OEM-encoded .bat + `tasklist /FI "PID eq N" | find " N "`.
   Still bricked: tasklist output formatting + PID column alignment
   varies, so `find " N "` was unreliable. User saw cmd window cycling
   `find:23168` forever (PID 23168 was the dead exe).
3. `0e3501b` — **stable**. Generate `.ps1` (UTF-8 BOM, PowerShell reads
   natively), wait with `Get-Process -Id $oldPid` (real Win32 API, no
   string parsing), 60s hard timeout, `Stop-Process -Force` fallback,
   rename retried 20×500ms for file-lock release. `.bat` is now a
   pure-ASCII shim that just invokes the PS1.

**2026-05-30 — field bug #8 (GitHub issue): silent brick + lost data.**
A frozen install on `23d4100` (which HAS the stable PS1 swap) clicked
更新, page died, never updated — with NO diagnostic trail. Two defects:

1. **Swap was unobservable.** It runs `DETACHED_PROCESS` (no console),
   so every `Write-Host` is discarded and the failure-branch
   `Read-Host 'Press Enter'` can't run console-less → it errored and
   exited, leaving zero trace. Could not determine whether
   rename / move / relaunch failed. Most likely sub-cause: antivirus
   locking the freshly-downloaded unsigned `.exe` during
   `Rename-Item` / `Move-Item`.
2. **`user_data` was not migrated.** `config.json` +
   `service_account.json` + 3 cathlab JSONs live in
   `install_dir/user_data`, which the swap renames to `.old`. The fresh
   bundle ships an empty `user_data`, so a *successful* swap would have
   wiped all settings + the SA key — fixing defect 1 alone would make
   things worse.

Fix (commit pending): swap PS1 now writes `__update_swap__.log` via a
`Log()` helper, copies `.old/user_data/*` into the new bundle before
deleting `.old`, replaces `Read-Host` with a `Log` + ASCII breadcrumb
file `UPDATE_FAILED_see_log.txt` (which also tells the user the manual
zip-recovery steps). Verified: 3 new tests + full suite + real
PowerShell `Parser::ParseFile` syntax check. NOT verifiable on a
non-Windows / non-frozen dev box — the actual rename/move/relaunch only
runs in a real shipped build. **A bricked install can't auto-update, so
this fix only protects FUTURE updates; already-bricked users must
recover manually once** (download `admission-app.zip`, copy old
`user_data\` into the new folder, run new exe).

**How to apply:** any future change to the swap logic must:

- Keep all Chinese path operations (`Rename-Item`, `Move-Item`,
  `Start-Process`) inside the `.ps1`, never the `.bat`.
- Use `Get-Process -Id $oldPid` for process-alive checks, never
  `tasklist | find`.
- Keep the hard timeout (currently 60s) and the `Stop-Process -Force`
  fallback — without those an unexpected exit failure spins forever and
  bricks the install (this was the root failure mode in v1 and v2).
- The `.bat` shim must remain ASCII-only — assertable via
  `bat_path.read_bytes().decode('ascii')` in tests.
- Save the `.ps1` as **UTF-8 BOM** (`encoding='utf-8-sig'`). PowerShell
  needs the BOM to detect UTF-8 reliably on Windows.
- **Always write the swap log** (`__update_swap__.log`) — a detached
  swap with no log is undiagnosable when it fails.
- **Never `Read-Host`** (or any blocking prompt) in the swap — the
  process has no console; drop a breadcrumb file instead.
- **Always migrate `user_data`** from `.old` to the new bundle before
  deleting `.old`, or every update wipes the user's settings + SA key.

Related: [[delivery-protocol-inapp-update]] still holds, but for any
install on a commit between `a68c3da` and `4eae323` inclusive the in-app
更新 button cannot self-recover — recipients must manually download the
latest release zip ONCE; thereafter PS1-based updater is robust.

See: `app/services/updater.py` `_write_swap_bat`; tests in
`tests/test_updater.py` (`test_swap_*`).
