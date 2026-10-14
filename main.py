"""Windows 定时提醒器 —— 程序入口。

启动方式：
    .venv\\Scripts\\pythonw.exe main.py      # 无控制台窗口
    .venv\\Scripts\\python.exe  main.py      # 带控制台（便于排查）

命令行参数：
    --no-tray        不显示托盘图标
    --show           启动时显示主窗口
"""

from __future__ import annotations

import argparse
import sys
import tkinter as tk
from datetime import timedelta
from pathlib import Path
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import config, notifier, settings, storage  # noqa: E402
from src.icon import create_image  # noqa: E402
from src.models import FMT, Task, now_minute  # noqa: E402
from src.scheduler import Scheduler  # noqa: E402
from src.tray import TrayIcon  # noqa: E402
from src.ui.alert_window import AlertManager  # noqa: E402
from src.ui.main_window import MainWindow  # noqa: E402

FONT = ("Microsoft YaHei UI", 10)
FONT_SMALL = ("Microsoft YaHei UI", 9)


class App:
    def __init__(self, show_window: bool = True, use_tray: bool = True):
        storage.init_db()
        storage.refresh_all_next_runs()
        self.cfg = settings.load()

        self.root = tk.Tk()
        self.root.title("定时提醒器")
        self.root.geometry("920x600")
        self.root.minsize(760, 460)
        self._setup_style()
        self._setup_icon()

        self.scheduler = Scheduler(
            on_fire=self._on_fire,
            miss_window_minutes=int(self.cfg.get("miss_window", config.MISS_WINDOW_MINUTES)),
        )
        self.alerts = AlertManager(self.root,
                                   on_snooze=self.snooze,
                                   on_open_main=lambda: self.window.show())
        self.dispatcher = notifier.AlertDispatcher(self.root, self._handle_alert)
        self.window = MainWindow(self.root, self)
        self.tray = TrayIcon(self)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Unmap>", self._on_unmap)

        if use_tray and self.tray.available:
            self.tray.start()
            self.root.after(1000, self.tray.refresh_title)
        if not show_window:
            self.root.withdraw()

    # ------------------------------------------------------------ 初始化

    def _setup_style(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(".", font=FONT, background="#ffffff", foreground="#1f2937")
        style.configure("TFrame", background="#ffffff")
        style.configure("TLabel", background="#ffffff", foreground="#1f2937")
        style.configure("Muted.TLabel", background="#ffffff", foreground="#6b7280",
                        font=FONT_SMALL)
        style.configure("Accent.TLabel", background="#ffffff", foreground="#2563eb",
                        font=FONT_SMALL)
        style.configure("TButton", padding=(12, 5), background="#f3f4f6")
        style.map("TButton", background=[("active", "#e5e7eb")])
        style.configure("Accent.TButton", background="#2563eb", foreground="#ffffff",
                        padding=(12, 5), borderwidth=0)
        style.map("Accent.TButton", background=[("active", "#1d4ed8")])
        style.configure("TCheckbutton", background="#ffffff")
        style.configure("TRadiobutton", background="#ffffff")
        style.configure("Treeview", background="#ffffff", fieldbackground="#ffffff",
                        rowheight=28, borderwidth=1, relief="solid")
        style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"),
                        background="#f3f4f6", relief="flat")
        style.map("Treeview", background=[("selected", "#dbeafe")],
                  foreground=[("selected", "#111827")])
        self.root.configure(bg="#ffffff")

    def _setup_icon(self) -> None:
        try:
            from PIL import ImageTk
            photo = ImageTk.PhotoImage(create_image(64))
            self.root.iconphoto(True, photo)
            self._icon_photo = photo          # 防止被 GC
        except Exception:
            pass

    # ------------------------------------------------------------ 运行

    def run(self) -> None:
        self.scheduler.start()
        self.dispatcher.start()
        try:
            self.root.mainloop()
        finally:
            self.scheduler.stop()
            self.tray.stop()

    def apply_settings(self) -> None:
        """设置变更后重新生效。"""
        self.cfg = settings.load()
        self.scheduler.miss_window = timedelta(
            minutes=int(self.cfg.get("miss_window", config.MISS_WINDOW_MINUTES))
        )
        self.scheduler.wakeup()
        self.tray.refresh_title()

    def quit_app(self) -> None:
        self.alerts.close_all()
        self.scheduler.stop()
        self.tray.stop()
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass

    # ------------------------------------------------------------ 提醒

    def _on_fire(self, task: Task, planned_at: str, missed: bool) -> None:
        """调度线程回调 —— 只做线程安全投递。"""
        self.dispatcher.post(task, planned_at, missed)

    def _handle_alert(self, task: Task, planned_at: str, missed: bool) -> None:
        """主线程执行实际的提醒呈现。"""
        cfg = self.cfg
        if task.sound and cfg.get("sound", True):
            notifier.play_sound()
        if cfg.get("popup", True):
            self.alerts.show(task, planned_at, missed)
        if cfg.get("toast", True):
            extra = "（补发）" if missed else ""
            notifier.show_toast(
                f"{task.title}",
                f"{planned_at} {extra}\n{task.message or task.rule_text()}",
            )
        self.window.refresh()
        self.tray.refresh_title()

    def fire_manual(self, task: Task) -> None:
        """立即测试：不写入历史，不推进计划。"""
        self._handle_alert(task, now_minute().strftime(FMT), missed=False)

    def snooze(self, task_id: int, minutes: int) -> None:
        task = storage.get_task(task_id)
        if not task:
            return
        target = now_minute() + timedelta(minutes=max(1, minutes))
        storage.touch_run(task_id, last_run=task.last_run or "",
                          next_run=task.next_run, snooze_until=target.strftime(FMT))
        self.scheduler.wakeup()
        self.window.refresh()

    def show_next_toast(self) -> None:
        pending = storage.next_pending()
        if pending:
            notifier.show_toast("下一次提醒", f"{pending[0]}　{pending[1]}")
        else:
            notifier.show_toast("下一次提醒", "暂无待提醒任务")

    # ------------------------------------------------------------ 窗口事件

    def _on_close(self) -> None:
        if self.cfg.get("close_to_tray", True) and self.tray.available:
            self.window.hide()
            self.tray.refresh_title()
        else:
            self.quit_app()

    def _on_unmap(self, event) -> None:
        """最小化到托盘（可选）。"""
        if event.widget is not self.root:
            return
        if not self.cfg.get("minimize_to_tray", True):
            return
        try:
            if self.root.state() == "iconic":
                self.root.withdraw()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Windows 定时提醒器")
    parser.add_argument("--no-tray", action="store_true", help="不显示托盘图标")
    parser.add_argument("--hide", action="store_true", help="启动后隐藏主窗口")
    args = parser.parse_args()

    app = App(show_window=not args.hide, use_tray=not args.no_tray)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
