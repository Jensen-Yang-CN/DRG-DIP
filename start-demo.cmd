@echo off
cd /d "%~dp0"
echo DIP Demo: http://127.0.0.1:8765/
echo Keep this window open while using the demo. Press Ctrl+C to stop.
python server.py --host 127.0.0.1 --port 8765
