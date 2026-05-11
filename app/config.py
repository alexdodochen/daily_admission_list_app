"""
Local user config — JSON-backed settings stored under app/data/.

Resolution order (later wins):
  1. dataclass defaults in AppConfig
  2. app/bundled/defaults.json               (shipped with .exe — non-sensitive)
  3. app/bundled/service_account.json        (only if user hasn't set their own)
  4. app/data/config.json                    (user-written, per machine)

Each user running the packaged .exe only fills:
  - LLM provider / API key / (optional) model
  - WEBCVIS creds (for Step 5)
  - LINE token + group (for Step 6)

Sheet ID, SA JSON, and base URLs arrive pre-filled from the bundle.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


def _resource_root() -> Path:
    """
    Where bundled read-only resources live.

    Dev (python -m app.run)   → the source tree's app/ directory
    PyInstaller onedir/onefile → sys._MEIPASS/app when bundled

    We prefer the sibling of this file; PyInstaller keeps the source layout
    intact when --add-data "app/bundled;app/bundled" is used.
    """
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent.parent))
    return base / "app"


APP_ROOT = _resource_root()
BUNDLED_DIR = APP_ROOT / "bundled"
BUNDLED_DEFAULTS = BUNDLED_DIR / "defaults.json"
BUNDLED_SA = BUNDLED_DIR / "service_account.json"

# User-writable data dir.
#  - Dev: app/data/ alongside source
#  - Packaged: app/data/ alongside the .exe (NOT inside _MEIPASS, so it persists)
if getattr(sys, "frozen", False):
    # PyInstaller: put user data next to the .exe, not inside the bundle
    DATA_DIR = Path(sys.executable).parent / "user_data"
else:
    DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = DATA_DIR / "config.json"


@dataclass
class AppConfig:
    # LLM
    llm_provider: str = ""          # "anthropic" | "openai" | "gemini"
    llm_api_key: str = ""
    llm_model: str = ""

    # Google Sheets
    google_creds_path: str = ""     # absolute path to service-account JSON
    sheet_id: str = ""              # admission/cathlab sheet (card 3)
    schedule_sheet_id: str = ""     # CV duty-schedule sheet (card 1)

    # EMR (optional)
    emr_base_url: str = "http://hisweb.hosp.ncku/Emrquery/"

    # WEBCVIS cathlab (optional)
    cathlab_base_url: str = "http://cardiopacs01.hosp.ncku:8080/WEBCVIS/HCO/HCO1W001.do"
    cathlab_user: str = ""
    cathlab_pass: str = ""

    # LINE push (optional)
    line_token: str = ""
    line_group_id: str = ""

    def is_ready(self) -> bool:
        """True if minimum settings for Step 1–2 are present."""
        return bool(self.llm_provider and self.llm_api_key
                    and self.google_creds_path and self.sheet_id)


_cached: Optional[AppConfig] = None

# Fields that auto-populate from bundled defaults.json when missing.
_BUNDLE_KEYS = ("sheet_id", "schedule_sheet_id", "emr_base_url", "cathlab_base_url")


def _load_bundled_defaults() -> dict:
    if not BUNDLED_DEFAULTS.exists():
        return {}
    try:
        return json.loads(BUNDLED_DEFAULTS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _apply_bundled(cfg: AppConfig, user_keys: set[str]) -> AppConfig:
    """Fill fields from the bundle for any key the user didn't explicitly set.

    `user_keys` = names present in the on-disk config.json. Values the user
    has chosen always win, even over the bundle. Dataclass defaults lose to
    the bundle, so base URLs in defaults.json take effect.
    """
    defaults = _load_bundled_defaults()
    for k in _BUNDLE_KEYS:
        if k in defaults and k not in user_keys:
            setattr(cfg, k, str(defaults[k]))
    if "google_creds_path" not in user_keys and BUNDLED_SA.exists():
        cfg.google_creds_path = str(BUNDLED_SA)
    return cfg


def bundled_flags() -> dict:
    """
    Report which fields the bundle is supplying, so the settings UI can
    pre-fill (or hide) them.
    """
    defaults = _load_bundled_defaults()
    return {
        "sheet_id":            "sheet_id" in defaults,
        "schedule_sheet_id":   "schedule_sheet_id" in defaults,
        "emr_base_url":        "emr_base_url" in defaults,
        "cathlab_base_url":    "cathlab_base_url" in defaults,
        "google_creds_path":   BUNDLED_SA.exists(),
    }


def load() -> AppConfig:
    global _cached
    if _cached is not None:
        return _cached
    cfg = AppConfig()
    user_keys: set[str] = set()
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            known = {k: v for k, v in data.items()
                     if k in AppConfig.__dataclass_fields__}
            cfg = AppConfig(**known)
            # "user set" = the key existed in the file AND had a non-empty value.
            # Blank strings shouldn't block the bundle from filling in.
            user_keys = {k for k, v in known.items()
                         if not (isinstance(v, str) and not v.strip())}
        except Exception:
            pass
    _cached = _apply_bundled(cfg, user_keys)
    return _cached


def save(cfg: AppConfig) -> None:
    global _cached
    _cached = cfg
    CONFIG_PATH.write_text(
        json.dumps(asdict(cfg), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def update(**kwargs) -> AppConfig:
    cfg = load()
    for k, v in kwargs.items():
        if k in AppConfig.__dataclass_fields__ and v is not None:
            setattr(cfg, k, v)
    save(cfg)
    return cfg
