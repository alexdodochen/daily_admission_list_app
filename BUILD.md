# Building the .exe for annual handoff

Target: a double-clickable `.exe` for each new 行政總醫師, with the shared
Sheet + service account already wired in. Users only enter their own LLM
API key, WEBCVIS login, and LINE token.

## One-time developer setup

```bash
# In the project venv
pip install pyinstaller
```

## Before each build

1. Copy the real service-account JSON into the bundle:
   ```bash
   cp <your-sa>.json app/bundled/service_account.json
   ```
   `app/bundled/service_account.json` is in `.gitignore` — it will **not**
   be committed. But it **will** be included in the `.exe` by PyInstaller.

2. Verify `app/bundled/defaults.json` has the correct Sheet ID.

3. Bump `app/VERSION` if shipping a new release.

## Build

```bash
pyinstaller packaging.spec --noconfirm
```

Output: `dist/行政總醫師.排班.Key班.入院/行政總醫師.排班.Key班.入院.exe`
(onedir — a folder with the exe + an `_internal/` directory of DLLs).
The bundle folder + exe are Chinese (set by `packaging.spec` EXE/COLLECT
`name=`); the release-asset zip is ASCII `admission-app.zip` (a non-ASCII
asset name gets mangled to `default.zip` by `action-gh-release`).

To test:
```bash
"dist/行政總醫師.排班.Key班.入院/行政總醫師.排班.Key班.入院.exe"
```

The app opens `http://127.0.0.1:8766` in a browser. User config persists in
`%LOCALAPPDATA%\admission-app\config.json` (DATA_DIR), not the bundle, so
auto-update / rebuild doesn't wipe the user's settings.

## Distribution

Copy the end-user guide to the bundle ROOT (it can't ride in via
`packaging.spec` datas — PyInstaller 6.x onedir forces datas into
`_internal/`), then zip the folder to an ASCII filename:
```powershell
Copy-Item "使用方法.txt" "dist/行政總醫師.排班.Key班.入院/使用方法.txt" -Force
Compress-Archive -Path "dist/行政總醫師.排班.Key班.入院" `
  -DestinationPath admission-app.zip -Force
```
They unzip anywhere and double-click `行政總醫師.排班.Key班.入院.exe`.
(CI does this automatically — prefer the GitHub Release `admission-app.zip`;
see skill `package-distribute`.)

## First-run: Chromium

Playwright's Chromium is **not** bundled (would add ~200 MB). On first run
the user needs:

```bash
"<exe-folder>/行政總醫師.排班.Key班.入院.exe" --install-browsers
```

or the app detects it and shows a "下載瀏覽器" button. (TODO: implement the
detection in `app/main.py` — today it's a manual step.)

## Handoff checklist

- [ ] `app/bundled/service_account.json` copied to target machine's bundle
- [ ] `app/bundled/defaults.json` → sheet_id is correct
- [ ] Service account has editor access on that Sheet (Google Drive share)
- [ ] Test run on a fresh Windows machine — settings page shows
      "系統預設 ✓" for Sheet + SA
- [ ] User fills in their own LLM key + WEBCVIS + LINE
- [ ] Run each step (1–6) end-to-end with a test date

## Rotating credentials (end of year)

When the 行政總醫師 rotates:
1. Disable the old SA key in GCP Console (revokes every shipped `.exe`)
2. Generate a new SA key → replace `app/bundled/service_account.json`
3. Rebuild the `.exe`
4. Share the new `.exe` with the new user

Old users' `user_data/config.json` (their LLM key etc.) is preserved as
long as they keep their existing exe folder; only the SA rotates.
