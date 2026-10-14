"""提醒弹窗：屏幕右下角堆叠显示，支持「知道了」与「稍后提醒」。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from .. import config
from ..models import Task

BG = "#ffffff"
FG = "#1f2937"
ACCENT = "#2563eb"
MUTED = "#6b7280"
BORDER = "#e5e7eb"


class AlertWindow(tk.Toplevel):
    WIDTH = 400

    def __init__(self, master, task: Task, planned_at: str, missed: bool,
                 on_snooze: Callable[[int, int], None],
                 on_open_main: Callable[[], None],
                 on_close: Callable[["AlertWindow"], None],
                 index: int = 0, snooze_options=config.DEFAULT_SNOOZE_MINUTES):
        super().__init__(master)
        self.task = task
        self.on_snooze = on_snooze
        self.on_open_main = on_open_main
        self.on_close = on_close
        self._index = index
        self._missed = bool(missed)
        self.planned_at = planned_at

        self.title("提醒")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self._acknowledge)
        self.bind("<Escape>", lambda e: self._acknowledge())
        self.bind("<Return>", lambda e: self._acknowledge())

        self._build()
        self._place(index)

    # ------------------------------------------------------------ 构建

    def _build(self) -> None:
        wrap = tk.Frame(self, bg=BG, padx=16, pady=12)
        wrap.pack(fill="both", expand=True)

        # 顶部：类型 + 状态
        head = tk.Frame(wrap, bg=BG)
        head.pack(fill="x")
        ttk.Label(head, text=self.task.kind_label, style="Accent.TLabel").pack(side="left")
        if self.task.completed:
            ttk.Label(head, text="已完成", style="Muted.TLabel").pack(side="right")

        tk.Label(wrap, text=self.task.title or "（无标题）", bg=BG, fg=FG,
                 font=("Microsoft YaHei UI", 13, "bold"),
                 wraplength=self.WIDTH - 40, justify="left", anchor="w").pack(
            fill="x", pady=(8, 4))

        if self.task.message:
            tk.Label(wrap, text=self.task.message, bg=BG, fg=FG,
                     font=("Microsoft YaHei UI", 10),
                     wraplength=self.WIDTH - 40, justify="left", anchor="w").pack(
                fill="x", pady=(0, 8))

        meta = f"计划时间 {self.planned_at}"
        if self._missed:
            meta += "（错过后补发）"
        tk.Label(wrap, text=meta, bg=BG, fg=MUTED,
                 font=("Microsoft YaHei UI", 9), anchor="w").pack(fill="x", pady=(0, 10))

        bar = tk.Frame(wrap, bg=BG)
        bar.pack(fill="x")

        ttk.Button(bar, text="知道了", style="Accent.TButton",
                   command=self._acknowledge).pack(side="right")

        if not self.task.completed:
            frm = tk.Frame(bar, bg=BG)
            frm.pack(side="left")
            self.snooze_var = tk.StringVar(value=str(config.DEFAULT_SNOOZE_MINUTES[1]))
            cb = ttk.Combobox(frm, width=4, state="readonly", textvariable=self.snooze_var,
                              values=[str(x) for x in config.DEFAULT_SNOOZE_MINUTES])
            cb.pack(side="left")
            tk.Label(frm, text="分钟后", bg=BG, fg=MUTED,
                     font=("Microsoft YaHei UI", 9)).pack(side="left", padx=(4, 8))
            ttk.Button(frm, text="稍后提醒", command=self._snooze).pack(side="left")

        ttk.Button(bar, text="打开主窗口", command=self._open_main).pack(side="right", padx=(0, 8))

    # ------------------------------------------------------------ 布局

    def _place(self, index: int) -> None:
        self.update_idletasks()
        h = self.winfo_reqheight()
        margin = 16
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x = sw - self.WIDTH - margin
        y = sh - h - margin - index * (h + 8)
        y = max(margin, y)
        self.geometry(f"{self.WIDTH}x{h}+{x}+{y}")

    def set_index(self, index: int) -> None:
        self._index = index
        self._place(index)

    # ------------------------------------------------------------ 行为

    def _acknowledge(self) -> None:
        self.on_close(self)
        self.destroy()

    def _snooze(self) -> None:
        try:
            minutes = int(self.snooze_var.get())
        except (ValueError, AttributeError):
            minutes = 10
        if self.task.id is not None:
            self.on_snooze(self.task.id, minutes)
        self.on_close(self)
        self.destroy()

    def _open_main(self) -> None:
        self.on_open_main()
        self._acknowledge()


class AlertManager:
    """管理多个提醒弹窗的堆叠与生命周期。"""

    def __init__(self, root, on_snooze: Callable[[int, int], None],
                 on_open_main: Callable[[], None]):
        self.root = root
        self.on_snooze = on_snooze
        self.on_open_main = on_open_main
        self.windows: list[AlertWindow] = []

    def show(self, task: Task, planned_at: str, missed: bool) -> None:
        win = AlertWindow(
            self.root, task, planned_at, missed,
            on_snooze=self.on_snooze,
            on_open_main=self.on_open_main,
            on_close=self._remove,
            index=len(self.windows),
        )
        self.windows.append(win)
        self._relayout()

    def _remove(self, win: AlertWindow) -> None:
        if win in self.windows:
            self.windows.remove(win)
        self._relayout()

    def _relayout(self) -> None:
        for i, win in enumerate(self.windows):
            try:
                win.set_index(i)
            except Exception:
                pass

    def close_all(self) -> None:
        for win in list(self.windows):
            try:
                win.destroy()
            except Exception:
                pass
        self.windows.clear()
