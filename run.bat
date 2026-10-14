@echo off
rem Start TimerReminder (no console window). Keep this file ASCII-only.

cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo [!] venv not found. Creating it and installing dependencies...
    C:\Python314\python.exe -m venv .venv
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
)

start "" ".venv\Scripts\pythonw.exe" main.py
