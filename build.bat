@echo off
chcp 65001 >nul
cd /d "%~dp0"

where pyinstaller >nul 2>nul
if errorlevel 1 (
    echo 正在安装 PyInstaller...
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q pyinstaller
)

".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name TimerReminder ^
    --hidden-import PIL --hidden-import pystray ^
    main.py

echo.
echo 打包完成：dist\TimerReminder.exe
pause
