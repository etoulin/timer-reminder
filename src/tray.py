"""系统托盘图标（基于 pystray；依赖缺失时自动降级为不显示托盘）。"""

from __future__ import annotations

from . import icon as icon_mod
from . import storage


class TrayIcon:
    def __init__(self, app):
        self.app = app
        self.icon = None
        self._available = False
        try:
            import pystray                                    # noqa: F401
            self._available = True
        except Exception:
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    # ------------------------------------------------------------ 生命周期

    def start(self) -> None:
        if not self._available:
            return
        import pystray

        menu = pystray.Menu(
            pystray.MenuItem("打开主窗口", self._on_open, default=True),
            pystray.MenuItem("新建提醒", self._on_new),
            pystray.MenuItem("下次提醒", self._on_next),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", self._on_quit),
        )
        self.icon = pystray.Icon("TimerReminder", icon_mod.create_image(64),
                                 "定时提醒器", menu)
        try:
            self.icon.run_detached()
        except Exception:
            self._available = False

    def stop(self) -> None:
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass

    def refresh_title(self) -> None:
        """更新托盘气泡提示中的「下次提醒」信息。"""
        if not self.icon:
            return
        try:
            pending = storage.next_pending()
            title = "定时提醒器"
            if pending:
                title = f"定时提醒器\n下一次：{pending[0]}  {pending[1]}"
            self.icon.title = title
        except Exception:
            pass

    # ------------------------------------------------------------ 回调

    def _on_open(self, *_):
        self.app.root.after(0, self.app.window.show)

    def _on_new(self, *_):
        self.app.root.after(0, self.app.window.new_task)

    def _on_next(self, *_):
        self.app.root.after(0, self.app.show_next_toast)

    def _on_quit(self, *_):
        self.app.root.after(0, self.app.quit_app)
