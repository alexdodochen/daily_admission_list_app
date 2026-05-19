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
- CAVEAT [[bundle-naming-invariant]]: the exe/bundle RENAME (`1f86e70`)
  breaks auto-update ONCE for any **pre-rename** install (asset-name
  mismatch) — that one time the user must manually re-download the new
  zip; afterwards 更新 works forever. Always check which version the
  recipient currently runs before telling them "just press 更新".
- New (never-installed) recipient → still give the release link + private
  files + `使用方法.txt` (skill `package-distribute` Path A).
- See [[cathlab-static-decouple]] for the loose-drop resolution.
