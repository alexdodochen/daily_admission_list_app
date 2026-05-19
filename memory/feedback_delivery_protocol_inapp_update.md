---
name: delivery-protocol-inapp-update
description: "Delivering updates to an existing install = push→CI release + recipient clicks in-app 更新 button; never re-ship a zip; SA+cathlab handed over privately as DATA_DIR drop-ins"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 8f6f0aa1
---

User-confirmed delivery protocol (2026-05-19) for recipients who ALREADY
have the app installed (e.g. 麒翔):

1. Ship code by **push to main → CI auto-builds the GitHub Release**
   (`.github/workflows/release.yml`). That release is the single source.
2. The recipient does **NOT** receive a re-zipped bundle. They press the
   in-app **更新** button; `updater.py` pulls the release and swaps files.
3. `service_account.json` + the 3 cathlab JSONs are delivered **privately,
   separately** (PHI / credential — never in the public release) and the
   recipient drops ALL 4 files **loose into the one folder**
   `%LOCALAPPDATA%\admission-app\` (no `cathlab_static` subfolder; SA
   filename unrestricted), then presses 設定頁「測試連線」(no restart).
4. **Step V still mandatory** — verify the RELEASE the 更新 button will
   fetch (bundled `app/VERSION` sha == HEAD, feature markers, zip ok),
   NOT a hand-built zip.

**Why:** Path A (credential-free CI release + private drop-in) is the
standing model; for an existing install the auto-updater is the delivery
channel, so re-sending a zip is wrong/redundant.

**How to apply:**
- Don't hand-build or re-send zips to existing users — push + tell them
  to click 更新.
- CAVEAT 1 — UPDATER WAS BROKEN before 2026-05-19: the topbar 更新
  button calls `/api/update/sync/self` → `upstream._sync_self`, which
  was **git-only** and dead-ended on every .exe with "只支援 git
  checkout" (the working zip-swap `updater._apply_frozen` existed but
  was never wired here). ALSO `updater.schedule_restart()` did
  `os.execv` the frozen exe → swap .bat dead-lock. Both fixed this
  session (upstream._sync_self frozen→updater.apply; schedule_restart
  frozen→os._exit). IMPLICATION: anyone whose installed build PREDATES
  this fix CANNOT use 更新 at all — they must MANUALLY download the
  new zip ONCE; from that build onward 更新 works. (麒翔's current
  build is pre-fix → he needs the one manual download regardless of
  the rename caveat below.)
- CAVEAT 2 [[bundle-naming-invariant]]: the exe/bundle RENAME
  (`1f86e70`) ALSO breaks auto-update once for any **pre-rename**
  install. Net: a pre-fix OR pre-rename install = one manual
  re-download; after that the in-app 更新 works forever.
- Playwright: CI cached the chromium browser under a HARDCODED key
  (`chromium-1208`) with install gated on cache-miss → stale browser
  bundled while a bumped Playwright lib demanded chromium-1223 at
  runtime ("Executable doesn't exist"). Fixed: cache key now tracks
  the resolved Playwright version + a build-time presence guard.
  Recipient gets a working browser only from a build AFTER this fix.
- New (never-installed) recipient → still give the release link + private
  files + `使用方法.txt` (skill `package-distribute` Path A).
- See [[cathlab-static-decouple]] for the loose-drop resolution.
