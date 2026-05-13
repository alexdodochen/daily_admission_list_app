@echo off
REM First-time setup for the admission app (Windows).
REM Run once after cloning. Creates .venv, installs deps, downloads Chromium.

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Install Python 3.11+ from https://www.python.org/ and re-run this file.
    pause
    exit /b 1
)

if not exist ".venv\" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] venv creation failed.
        pause
        exit /b 1
    )
)

call .venv\Scripts\activate.bat

echo.
echo Installing Python dependencies (this may take a few minutes)...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
)

echo.
echo Installing Chromium browser for Playwright (about 200 MB, one-time)...
python -m playwright install chromium
if errorlevel 1 (
    echo [WARN] Chromium install failed. Step 3 (EMR) and Step 5 (cathlab) will not work.
    echo You can re-run this script later.
)

echo.
echo ============================================================
echo  Setup complete. Double-click start.bat to launch the app.
echo ============================================================
pause
