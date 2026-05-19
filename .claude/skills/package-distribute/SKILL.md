---
name: package-distribute
description: >
  Use when packaging this app into a double-clickable .exe / .zip for another
  person (incoming 行政總醫師 / 麒翔 / a colleague). Triggers on "打包", "包成
  zip", "做安裝檔", "出版本", "交付給", "給別人用", "build exe", "release",
  "distribute". Decides CI-release vs local SA-bundled build, then runs the
  mandatory verification so a stale/incomplete bundle never ships.
---

# package-distribute — turn this project into a usable .zip for someone else

This app ships as a PyInstaller **onedir** bundle. The release asset is
`admission-app.zip` (ASCII — see naming note below); inside it is a folder
`行政總醫師.排班.Key班.入院/` containing `行政總醫師.排班.Key班.入院.exe`
+ `_internal/`. The recipient unzips anywhere and double-clicks the exe; it
serves `http://127.0.0.1:8766` and opens a browser.

**Naming invariant (do not break):** the bundle folder + exe are Chinese
(`行政總醫師.排班.Key班.入院`, set by `packaging.spec` EXE/COLLECT `name=`).
The **release-asset zip filename must stay ASCII** (`admission-app.zip`) —
`action-gh-release` mangles a non-ASCII asset name to `default.zip`, and
`updater.RELEASE_ASSET_NAME` matches the asset by exact name. Three places
must agree: `packaging.spec` (`name=`), `release.yml` "Zip distribution"
`-DestinationPath` + `files:`, and `updater.RELEASE_ASSET_NAME`.

There are **two distribution paths**. Pick with the decision table, then
ALWAYS run Step V (verification) before handing anything over.

---

## Decision: which path?

| Question | → Path |
|---|---|
| Recipient is trusted to receive a Google service account, and you want zero setup for them on the Sheet side? | **B — local SA-bundled build** |
| Public / general distribution, or auto-update must stay safe? | **A — CI release (default, recommended)** |

Default to **Path A**. Path B is only for a single trusted hand-off where
you also accept that the zip carries a real credential.

Key design fact (commit `4acbcb8`): the **CI release is intentionally
credential-free**. `app/bundled/service_account.json` is `.gitignore`d, so
CI (which checks out from git) never bundles it. The recipient drops their
own `service_account.json` into the path shown on the app's `/settings`
page (DATA_DIR), which **survives auto-update**. That is the supported
public-distribution model — do not try to sneak the SA into a public
release (the repo is public).

---

## Path A — CI release (recommended)

CI (`.github/workflows/release.yml`) runs on every push to `main`:
computes a `vYYYYMMDD-HHMM-<short>` tag, stamps `app/VERSION` from the git
sha, builds with PyInstaller, zips `dist/行政總醫師.排班.Key班.入院` →
`admission-app.zip`, and publishes a GitHub Release with that zip attached.

1. Make sure every change you want shipped is **committed and pushed to
   `main`**. (Push needs explicit user authorization — ask.)
2. Find the CI run + release for the exact HEAD sha:
   ```bash
   HEAD=$(git rev-parse HEAD)
   curl -s "https://api.github.com/repos/alexdodochen/daily_admission_list_app/actions/runs?per_page=5" \
     | grep -E '"head_sha"|"status"|"conclusion"'
   curl -s "https://api.github.com/repos/alexdodochen/daily_admission_list_app/releases?per_page=5" \
     | grep -E '"tag_name"|"published_at"|browser_download_url'
   ```
   The release whose `tag_name` ends in HEAD's 7-char short sha is the one.
   CI run for that sha must be `status: completed`, `conclusion: success`.
   If still running, wait — do NOT hand-build instead (you would ship an
   unverified, possibly credential-bundled artifact).
3. The release's `admission-app.zip` is the distributable. Give the
   recipient: (a) the release download link, (b) **separately** their
   `service_account.json` (never in the same channel as anything public),
   (c) the drop-in instruction below.
4. Run **Step V** against the released zip (download it, check the bundle).

### Recipient drop-in instructions (Path A)

A full Chinese end-user guide `使用方法.txt` is bundled at the zip root
(via `packaging.spec` `datas` `("使用方法.txt", ".")`) — tell the recipient
to read it first. Short form:

> 1. 解壓 `admission-app.zip`，先讀根目錄的 `使用方法.txt`。
> 2. 雙擊 `行政總醫師.排班.Key班.入院.exe`。
> 3. 把另外私下給的 `service_account.json` 放進 `%LOCALAPPDATA%\
>    admission-app\`；3 個 cathlab JSON 放進其下的 `cathlab_static\`
>    子資料夾。重開程式 → 設定頁顯示「系統預設 ✓」。
> 4. 填自己的 LLM 金鑰 / WEBCVIS 帳密 / LINE token。

When updating `使用方法.txt`, keep names in sync with
[[bundle-naming-invariant]] (asset `admission-app.zip`, exe
`行政總醫師.排班.Key班.入院.exe`).

---

## Path B — local build with SA bundled (trusted hand-off only)

Follow `BUILD.md`. Summary:

1. `cp <real-SA>.json app/bundled/service_account.json` (gitignored; gets
   baked into the exe by PyInstaller).
2. Verify `app/bundled/defaults.json` `sheet_id` is the intended Sheet.
3. (Optional) the local build's `app/VERSION` is whatever is on disk — for
   a traceable build, stamp it like CI does (tag/sha/short/built_at).
4. `pyinstaller packaging.spec --noconfirm` →
   `dist/行政總醫師.排班.Key班.入院/`.
5. Zip the **whole** `dist/行政總醫師.排班.Key班.入院/` folder to an ASCII
   filename (PowerShell: `Compress-Archive -Path
   "dist/行政總醫師.排班.Key班.入院" -DestinationPath admission-app.zip
   -Force`).
6. Run **Step V**. This zip contains a live credential → deliver only
   through a private channel, never a public location, never a GitHub
   release. Note its larger size (Chromium bundled, ~380 MB).

---

## Step V — verification (MANDATORY, both paths)

Never hand over a bundle without these checks. Extract the bundled files
(use Python `zipfile`; the top folder name is mojibake-encoded Chinese, so
match on suffix `.../​_internal/app/...`).

1. **Version matches HEAD.** Read bundled `_internal/app/VERSION`. Its
   `sha`/`short` MUST equal `git rev-parse HEAD`. A mismatch = stale bundle
   (this is exactly how the 9e0a531 `麒翔.zip` slipped — built from an old
   commit, file mtime looked fresh because it was only re-zipped later).
2. **Feature markers present.** Grep the bundled `app/static/app.js` and
   `app/templates/admission.html` for a string unique to the change you
   intend to ship (e.g. `cleanName` / a new button label). Absent = stale.
3. **Cathlab static data present.** Confirm
   `_internal/app/data/static/cathlab_id_maps.json` (+ `doctor_codes.json`,
   `cathlab_schedule.json`) exist in the bundle. `cathlab_service.py` loads
   them from `<app>/data/static/` at module level; if missing, **Step 5
   導管 key-in throws FileNotFoundError at runtime**. KNOWN GAP: current
   `packaging.spec` `datas` does NOT include `app/data/static`, and
   `app/data/` is `.gitignore`d (PHI: doctor/chart-no maps must not hit a
   public repo). Consequences:
   - **Local build (Path B):** still broken unless `packaging.spec` is
     fixed to add `("app/data/static", "app/data/static")` to `datas`
     (the files exist on the dev disk).
   - **CI build (Path A):** the files are not even in the git checkout, so
     the public release can never contain them. Step 5 needs the same
     drop-in treatment as the SA (a DATA_DIR fallback in
     `cathlab_service.STATIC_DIR`). Until that exists, a Path-A recipient
     must be sent the 3 JSONs privately and told where to place them, OR
     Step 5 is documented as unavailable in the public build.
   Surface this to the user; do not silently ship a Step-5-broken exe.
4. **Zip integrity.** The zip opens and the exe is non-zero size.

If any check fails → report which, do not deliver, fix root cause.

---

## Common pitfalls (don't repeat)

- **"exe 無法啟動" + `WinError 10048` on bind 8766** = an instance is
  already running, NOT a build bug. Tell the user to open
  `http://127.0.0.1:8766` or kill the existing
  `行政總醫師.排班.Key班.入院.exe`.
- **Stale `dist/` / hand-zip.** File mtime ≠ build provenance. Trust only
  bundled `app/VERSION` sha (Step V.1).
- **Never hand-rebuild to "save time" while CI is still running** — you
  risk shipping a credential-bundled or unverified artifact when the
  correct credential-free release was seconds away.
- **`app/data/static` PHI.** Keep it `.gitignore`d. Fixing the spec to
  bundle it makes Path B work but must not be paired with un-gitignoring
  (that would leak doctor/chart maps into the public repo).
- **Push gating.** Pushing to `main` (which triggers the CI release) needs
  explicit user authorization each time.

---

## Quick reference

- Repo: `https://github.com/alexdodochen/daily_admission_list_app`
- CI: `.github/workflows/release.yml` (push:main → build+zip+release)
- Local build doc: `BUILD.md`; spec: `packaging.spec`
- Asset: `admission-app.zip`; bundle layout inside:
  `行政總醫師.排班.Key班.入院/行政總醫師.排班.Key班.入院.exe` + `_internal/`
- VERSION truth: `_internal/app/VERSION` (`sha` field)
- Port: `127.0.0.1:8766`
- Credential drop-in (Path A): `service_account.json` → DATA_DIR shown on
  `/settings` (survives auto-update; design from commit `4acbcb8`)
