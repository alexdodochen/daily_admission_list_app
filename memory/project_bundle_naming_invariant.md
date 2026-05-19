---
name: bundle-naming-invariant
description: Exe/folder = Chinese 行政總醫師.排班.Key班.入院; release asset MUST be ASCII admission-app.zip; 3 files must agree
metadata: 
  node_type: memory
  type: project
  originSessionId: 8fe1ad8e-642f-4be4-ae2f-d7318d5aae47
---

Decided 2026-05-19 (user: 「我要把EXE的檔案格式叫做 行政總醫師.排班.Key班.入院」).

- Bundle folder + exe name = **`行政總醫師.排班.Key班.入院`** (Chinese),
  set by `packaging.spec` EXE `name=` AND COLLECT `name=`.
- Release-asset zip filename = **`admission-app.zip`** (ASCII, MUST stay
  ASCII). `action-gh-release` mangles any non-ASCII asset name to
  `default.zip`; `updater.latest_release()` matches the asset by exact
  `RELEASE_ASSET_NAME`. The Chinese folder/exe live INSIDE the zip.

**Three places must agree** (change together or auto-update silently
breaks):
1. `packaging.spec` — EXE/COLLECT `name="行政總醫師.排班.Key班.入院"`
2. `.github/workflows/release.yml` "Zip distribution" `Compress-Archive
   -Path "行政總醫師.排班.Key班.入院" -DestinationPath "admission-app.zip"`
   + the "Verify build" path + `files: dist/admission-app.zip`
3. `app/services/updater.py` `RELEASE_ASSET_NAME = "admission-app.zip"`

`updater._write_swap_bat` derives `exe_name = install_dir.name + ".exe"`
and `pending_inner = extract_dir / install_dir.name`, so the exe basename
is dynamic — it only works because the zip's inner folder name == the
installed folder name. Keep COLLECT name == what users unzip.

**Why:** user wants a self-describing Chinese exe; GitHub asset naming
forces ASCII. Decoupling the two satisfies both.

**One-time consequence:** an OLD install (folder `每日入院名單`, old
updater expecting `每日入院名單.zip`) CANNOT auto-update across this
rename — the new release only has `admission-app.zip`, so `latest_release`
finds no asset and skips. Acceptable here (麒翔 not yet delivered final;
dev dist disposable). Anyone on a pre-rename build needs ONE manual
re-download of the new zip; auto-update resumes (new→new) after that.

See skill `package-distribute` (naming invariant section) and
[[cathlab-static-decouple]].
