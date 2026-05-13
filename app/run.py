"""
Launcher: start uvicorn + open the browser.
    python -m app.run
"""
from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser

HOST = os.environ.get("ADMISSION_APP_HOST", "127.0.0.1")
PORT = int(os.environ.get("ADMISSION_APP_PORT", "8766"))


def _point_playwright_at_bundle() -> None:
    """When running from a PyInstaller bundle, redirect Playwright's browser
    lookup to the `ms-playwright/` folder shipped inside the bundle.

    sys.frozen + sys._MEIPASS are set by PyInstaller. In dev mode we leave
    PLAYWRIGHT_BROWSERS_PATH alone so the user's normal cache is used.
    """
    if not getattr(sys, "frozen", False):
        return
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return
    bundled = os.path.join(base, "ms-playwright")
    if os.path.isdir(bundled):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = bundled


_point_playwright_at_bundle()


def _open_browser():
    time.sleep(1.0)
    webbrowser.open(f"http://{HOST}:{PORT}/")


def main():
    try:
        import uvicorn
    except ImportError:
        print("請先安裝套件： pip install -r app/requirements.txt", file=sys.stderr)
        sys.exit(1)

    # Import the app object directly. Passing the import string
    # "app.main:app" works under `python -m app.run` but breaks in a
    # PyInstaller frozen bundle where uvicorn's importlib lookup can't
    # see the embedded `app` package.
    from app.main import app as fastapi_app

    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(fastapi_app, host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    main()
