@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\prepare-demo-start.ps1"
if errorlevel 1 (
    echo Demo startup preparation failed.
    pause
    exit /b 1
)
echo Starting DIP / DRG Demo. Keep this window open and press Ctrl+C to stop.
python server.py --host 127.0.0.1 --port 8765
if errorlevel 1 pause
