@echo off
REM Double-click to launch the admission app.
REM Opens http://127.0.0.1:8766 in default browser.

cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo .venv not found. Run install.bat first.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

REM Open the browser after 3 seconds (gives uvicorn time to boot)
start /b cmd /c "timeout /t 3 /nobreak >nul & start http://127.0.0.1:8766/"

echo Starting admission app on http://127.0.0.1:8766 ...
echo Close this window to stop the app.
python -m app.run
