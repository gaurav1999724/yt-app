@echo off
cd /d "%~dp0"
echo Starting YouTube Pipeline UI at http://127.0.0.1:8765
python -m ui
pause
