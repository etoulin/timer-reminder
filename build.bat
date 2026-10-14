@echo off
rem Build TimerReminder into a standalone exe (PyInstaller).
rem Keep this file ASCII-only: cmd may parse it with a legacy codepage.

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [!] venv not found. Run run.bat first to create it.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo Installing PyInstaller...
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q pyinstaller
    if errorlevel 1 (
        echo [!] Failed to install PyInstaller.
        pause
        exit /b 1
    )
)

".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name TimerReminder ^
    --hidden-import PIL --hidden-import pystray ^
    main.py

if errorlevel 1 (
    echo [!] Build failed.
    pause
    exit /b 1
)

echo.
echo Done: dist\TimerReminder.exe
pause
