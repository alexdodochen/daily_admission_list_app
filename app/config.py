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
#  - Dev (python -m app.run): app/data/ alongside source — easy to inspect.
#  - Packaged (.exe): %LOCALAPPDATA%\admission-app\ (or ~/.config/admission-app/
#    on POSIX). Survives every exe update because the new zip extracts to a
#    different folder; user_data isn't inside the bundle.
#
# Migration: if an older .exe wrote user_data NEXT to the .exe, copy that
# config across on first launch so users don't re-fill the settings page.
if getattr(sys, "frozen", False):
    if sys.platform == "win32":
        _root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        DATA_DIR = Path(_root) / "admission-app"
    else:
        _root = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        DATA_DIR = Path(_root) / "admission-app"

    _legacy_dir = Path(sys.executable).parent / "user_data"
    _legacy_cfg = _legacy_dir / "config.json"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if _legacy_cfg.exists() and not (DATA_DIR / "config.json").exists():
        # One-time migration from old layout
        try:
            (DATA_DIR / "config.json").write_text(
                _legacy_cfg.read_text(encoding="utf-8"), encoding="utf-8"
            )
        except Exception:
            pass
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


def _looks_like_sa(path: Path) -> bool:
    """True if `path` is a Google service-account key JSON. Lets the user
    drop the file under ANY name (the original Google-generated
    `project-abc123.json`) instead of forcing an exact rename — Windows
    hides extensions so a forced rename silently produces
    `service_account.json.txt`, which used to break detection."""
    try:
        if path.suffix.lower() != ".json" or path.stat().st_size > 64 * 1024:
            return False
        data = json.loads(path.read_text(encoding="utf-8"))
        return (isinstance(data, dict)
                and data.get("type") == "service_account"
                and bool(data.get("private_key"))
                and bool(data.get("client_email")))
    except Exception:
        return False


def _scan_dir_for_sa(d: Path) -> Optional[Path]:
    """First *.json in `d` whose content is a valid SA key (sorted for
    determinism). The canonical `service_account.json` wins if present."""
    try:
        canonical = d / "service_account.json"
        if canonical.exists() and _looks_like_sa(canonical):
            return canonical
        for p in sorted(d.glob("*.json")):
            if _looks_like_sa(p):
                return p
    except Exception:
        pass
    return None


def _detect_sa() -> Optional[Path]:
    """Find a service-account JSON the user dropped in, in priority order.

    Public CI release builds ship WITHOUT a bundled credential (the SA must
    never land in a public GitHub Release). The shared SA is delivered to
    the user as a single file via a private channel; they drop it into the
    settings-page DATA_DIR (or next to the exe) UNDER ANY NAME, and we
    migrate it into the persistent DATA_DIR as `service_account.json` so it
    SURVIVES every auto-update (the exe folder is replaced wholesale).

    Order:
      1. DATA_DIR/<any valid SA *.json>   — persistent, survives updates
      2. <exe>/<any valid SA *.json>      — intuitive drop spot (frozen)
      3. <exe>/user_data/<any valid SA>   — legacy layout
      4. BUNDLED_SA                       — only in hand-built (non-CI) zips
    """
    persistent = DATA_DIR / "service_account.json"

    found = _scan_dir_for_sa(DATA_DIR)
    if found is not None:
        if found == persistent:
            return persistent
        # Normalise any-named drop-in → canonical name so it's stable.
        try:
            persistent.write_bytes(found.read_bytes())
            return persistent
        except Exception:
            return found

    search_dirs = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        search_dirs += [exe_dir, exe_dir / "user_data"]
    for d in search_dirs:
        c = _scan_dir_for_sa(d)
        if c is not None:
            # Migrate into DATA_DIR so the next auto-update keeps it.
            try:
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                persistent.write_bytes(c.read_bytes())
                return persistent
            except Exception:
                return c
    if BUNDLED_SA.exists():
        return BUNDLED_SA
    return None


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
    if "google_creds_path" not in user_keys:
        sa = _detect_sa()
        if sa is not None:
            cfg.google_creds_path = str(sa)
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
        "google_creds_path":   _detect_sa() is not None,
    }


def sa_status() -> dict:
    """For the settings page: where the SA is (if found) + the exact path
    the user should drop service_account.json into so it survives updates.
    """
    sa = _detect_sa()
    return {
        "found": sa is not None,
        "path": str(sa) if sa else "",
        "drop_dir": str(DATA_DIR),
        "drop_file": str(DATA_DIR / "service_account.json"),
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


def reset_cache() -> None:
    """Drop the cached AppConfig so the next load() re-runs bundle / SA
    detection. Call after the user drops service_account.json into DATA_DIR
    without restarting the app (the file may appear AFTER first load())."""
    global _cached
    _cached = None


def save(cfg: AppConfig) -> None:
    global _cached
    # If the caller left the creds path blank (bundled builds hide that
    # field), re-detect a dropped / bundled SA now so saving the settings
    # page doesn't blank out a perfectly good credential.
    if not (cfg.google_creds_path or "").strip():
        sa = _detect_sa()
        if sa is not None:
            cfg.google_creds_path = str(sa)
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
