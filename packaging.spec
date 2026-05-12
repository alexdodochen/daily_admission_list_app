# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the daily-admission app.

Build:
    pyinstaller packaging.spec --noconfirm

Output: dist/每日入院名單/每日入院名單.exe (onedir).

Before running:
  1. Copy your real service-account JSON to app/bundled/service_account.json
  2. Verify app/bundled/defaults.json has the correct Sheet ID
  3. Install dev deps:  pip install pyinstaller

Playwright/Chromium is NOT bundled (too large). The app checks for it on
first run and prompts the user.
"""
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# ---- Bundled data ----------------------------------------------------------
datas = [
    ("app/static",      "app/static"),
    ("app/templates",   "app/templates"),
    ("app/bundled",     "app/bundled"),        # SA JSON + defaults.json
    ("app/VERSION",     "app"),
]
# gspread ships certificates + small JSON assets; include them all
datas += collect_data_files("gspread")
datas += collect_data_files("google.auth")

# ---- Bundle Playwright Chromium so recipients don't need to install ----
import os as _os
_pw_root = _os.path.join(_os.environ.get("LOCALAPPDATA", ""), "ms-playwright")
if _os.path.isdir(_pw_root):
    for _name in _os.listdir(_pw_root):
        # Bundle chromium-* (regular + headless variants) + ffmpeg-*; skip winldd
        if _name.startswith("chromium") or _name.startswith("ffmpeg"):
            _src = _os.path.join(_pw_root, _name)
            if _os.path.isdir(_src):
                datas.append((_src, _os.path.join("ms-playwright", _name)))

# ---- Hidden imports --------------------------------------------------------
# FastAPI / uvicorn / httpx pull a lot of submodules dynamically.
hiddenimports = (
    collect_submodules("uvicorn")
    + collect_submodules("fastapi")
    + collect_submodules("pydantic")
    + collect_submodules("gspread")
    + [
        "anthropic",
        "openai",
        "google.genai",
        "holidays",
    ]
)

block_cipher = None

a = Analysis(
    ["app/run.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",       # unused, big
        "pytest",        # test-only
        "IPython",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="每日入院名單",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                 # UPX often breaks signed DLLs on Windows
    console=True,              # keep console for now — easier error visibility
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="每日入院名單",
)
