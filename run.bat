@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo [!] 未找到虚拟环境，正在创建并安装依赖...
    C:\Python314\python.exe -m venv .venv
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
)

start "" ".venv\Scripts\pythonw.exe" main.py
