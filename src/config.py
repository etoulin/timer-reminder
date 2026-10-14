"""全局路径与常量配置。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Timer 定时提醒器"
APP_ID = "TimerReminder"

# 项目根目录（src 的上一级）
BASE_DIR = Path(__file__).resolve().parent.parent

# 数据目录：优先使用 %LOCALAPPDATA%，保证打包成 exe 后也能正常写入
def _data_dir() -> Path:
    if getattr(sys, "frozen", False):          # PyInstaller 打包后的情形
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_ID
    else:
        base = BASE_DIR / "data"
    base.mkdir(parents=True, exist_ok=True)
    return base


DATA_DIR: Path = _data_dir()
DB_PATH: Path = DATA_DIR / "timer.db"
LOG_PATH: Path = DATA_DIR / "timer.log"
ICON_PATH: Path = BASE_DIR / "assets" / "icon.ico"

# ------------------------------------------------------------------ 行为常量

TICK_SECONDS = 1.0            # 调度器轮询间隔（秒）
MISS_WINDOW_MINUTES = 60      # 错过提醒的补发窗口：超出则跳过本次
DEFAULT_SNOOZE_MINUTES = (5, 10, 30, 60)
MAX_SOUND_REPEAT = 3          # 提示音重复次数
