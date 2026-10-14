@echo off
rem Start TimerReminder with a console window (for troubleshooting).
rem Keep this file ASCII-only.

cd /d "%~dp0"
".venv\Scripts\python.exe" main.py --no-tray
pause
