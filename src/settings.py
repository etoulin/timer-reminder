"""应用设置（持久化到 data/settings.json）。"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from . import config

_DEFAULTS = {
    "sound": True,            # 提示音总开关
    "toast": True,            # Windows 通知中心提醒
    "popup": True,            # 弹窗提醒
    "minimize_to_tray": True, # 最小化到托盘
    "close_to_tray": True,    # 关闭窗口时隐藏到托盘
    "miss_window": config.MISS_WINDOW_MINUTES,
    "autostart": False,
}

_LOCK = threading.RLock()
_PATH: Path = config.DATA_DIR / "settings.json"


def load() -> dict:
    with _LOCK:
        data = dict(_DEFAULTS)
        try:
            if _PATH.exists():
                loaded = json.loads(_PATH.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data.update(loaded)
        except Exception:
            pass
        return data


def save(data: dict) -> None:
    with _LOCK:
        merged = dict(load())
        merged.update(data or {})
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return merged


def get(key: str, default=None):
    return load().get(key, _DEFAULTS.get(key, default))


def set_value(key: str, value) -> None:
    save({key: value})
