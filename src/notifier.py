"""提醒呈现：提示音、Windows 系统通知（Toast）、弹窗调度。

- 提示音与 Toast 走独立线程/子进程，不阻塞 UI。
- 弹窗必须在主线程创建（tkinter 限制），由 :class:`AlertDispatcher` 统一派发。
"""

from __future__ import annotations

import os
import queue
import subprocess
import tempfile
import threading
import time
import winsound
from typing import Callable

from . import config
from .models import Task

# ------------------------------------------------------------------ 提示音


def play_sound(repeat: int | None = None) -> None:
    """播放系统提示音（非阻塞）。"""
    repeat = repeat or config.MAX_SOUND_REPEAT

    def _run():
        for i in range(max(1, repeat)):
            try:
                winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS)
            except Exception:
                try:
                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                except Exception:
                    return
            time.sleep(0.5)

    threading.Thread(target=_run, name="Sound", daemon=True).start()


# ------------------------------------------------------------------ Toast 通知

_TOAST_SCRIPT = r"""
param([string]$Title, [string]$Message)
try {
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
    $t = [Security.SecurityElement]::Escape($Title)
    $m = [Security.SecurityElement]::Escape($Message)
    $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
    $xml.LoadXml("<toast scenario='reminder'><visual><binding template='ToastText02'><text id='1'>$t</text><text id='2'>$m</text></binding></visual></toast>")
    $toast = New-Object Windows.UI.Notifications.ToastNotification $xml
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier().Show($toast)
} catch {
    exit 1
}
"""


def show_toast(title: str, message: str) -> None:
    """发送 Windows 通知中心提醒；失败时静默忽略。"""

    def _run():
        path = None
        try:
            fd, path = tempfile.mkstemp(suffix=".ps1")
            with os.fdopen(fd, "w", encoding="utf-8-sig") as f:
                f.write(_TOAST_SCRIPT)
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive",
                 "-ExecutionPolicy", "Bypass", "-File", path,
                 "-Title", title, "-Message", message],
                timeout=20,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            pass
        finally:
            if path:
                try:
                    os.unlink(path)
                except Exception:
                    pass

    threading.Thread(target=_run, name="Toast", daemon=True).start()


# ------------------------------------------------------------------ 弹窗派发


class AlertDispatcher:
    """把来自调度线程的事件安全地转移到 tkinter 主线程。

    使用方式（主线程）：
        dispatcher = AlertDispatcher(root, handler)
        dispatcher.start()          # 启动轮询
    后台线程调用 :meth:`post`，handler 会在主线程执行。
    """

    def __init__(self, root, handler: Callable[[Task, str, bool], None]):
        self.root = root
        self.handler = handler
        self._queue: "queue.Queue[tuple[Task, str, bool]]" = queue.Queue()
        self._running = False

    def post(self, task: Task, planned_at: str, missed: bool) -> None:
        self._queue.put((task, planned_at, missed))

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._poll()

    def _poll(self) -> None:
        try:
            while True:
                task, planned_at, missed = self._queue.get_nowait()
                try:
                    self.handler(task, planned_at, missed)
                except Exception:
                    pass
        except queue.Empty:
            pass
        self.root.after(300, self._poll)
