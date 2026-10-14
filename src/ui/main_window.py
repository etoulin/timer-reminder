"""主窗口：任务列表、工具栏、状态栏、设置与历史记录。"""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from .. import autostart, settings, storage
from ..models import Task
from .task_dialog import ask_task

FONT = ("Microsoft YaHei UI", 10)
FONT_SMALL = ("Microsoft YaHei UI", 9)
FONT_TITLE = ("Microsoft YaHei UI", 11, "bold")


class MainWindow:
    def __init__(self, root: tk.Tk, app):
        self.root = root
        self.app = app
        self._build_menu()
        self._build_toolbar()
        self._build_table()
        self._build_status()
        self.refresh()
        self._tick_clock()

    # ------------------------------------------------------------ 菜单

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="新建提醒", command=self.new_task)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.app.quit_app)
        menubar.add_cascade(label="文件", menu=file_menu)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="刷新", command=self.refresh)
        view_menu.add_command(label="提醒历史", command=self.show_history)
        menubar.add_cascade(label="视图", menu=view_menu)

        tool_menu = tk.Menu(menubar, tearoff=0)
        tool_menu.add_command(label="选项设置", command=self.open_settings)
        menubar.add_cascade(label="工具", menu=tool_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="关于", command=self.show_about)
        menubar.add_cascade(label="帮助", menu=help_menu)

        self.root.config(menu=menubar)

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self.root, padding=(10, 8))
        bar.pack(fill="x")
        ttk.Button(bar, text="新建", style="Accent.TButton", command=self.new_task).pack(side="left")
        ttk.Button(bar, text="编辑", command=self.edit_selected).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="复制", command=self.copy_selected).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="删除", command=self.delete_selected).pack(side="left", padx=(6, 0))
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=12)
        ttk.Button(bar, text="启用/停用", command=self.toggle_selected).pack(side="left")
        ttk.Button(bar, text="立即测试", command=self.test_selected).pack(side="left", padx=(6, 0))
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=12)
        ttk.Button(bar, text="提醒历史", command=self.show_history).pack(side="left")
        ttk.Button(bar, text="选项设置", command=self.open_settings).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="刷新", command=self.refresh).pack(side="right")

    def _build_table(self) -> None:
        wrap = ttk.Frame(self.root, padding=(10, 0, 10, 6))
        wrap.pack(fill="both", expand=True)

        columns = ("title", "kind", "rule", "next", "status", "count")
        self.tree = ttk.Treeview(wrap, columns=columns, show="headings", selectmode="browse")
        headers = {
            "title": ("标题", 180),
            "kind": ("类型", 90),
            "rule": ("提醒规则", 240),
            "next": ("下次提醒", 140),
            "status": ("状态", 150),
            "count": ("已提醒", 70),
        }
        for col, (text, width) in headers.items():
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor="w" if col != "count" else "center",
                             stretch=(col in ("title", "rule")))

        scroll = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.tree.tag_configure("disabled", foreground="#9ca3af")
        self.tree.tag_configure("active", foreground="#1f2937")
        self.tree.bind("<Double-1>", lambda e: self.edit_selected())
        self.tree.bind("<Button-3>", self._popup_menu)

        self._menu = tk.Menu(self.root, tearoff=0)
        self._menu.add_command(label="编辑", command=self.edit_selected)
        self._menu.add_command(label="复制", command=self.copy_selected)
        self._menu.add_command(label="启用/停用", command=self.toggle_selected)
        self._menu.add_command(label="立即测试", command=self.test_selected)
        self._menu.add_separator()
        self._menu.add_command(label="删除", command=self.delete_selected)

        hint = ttk.Label(wrap, text="提示：双击行可编辑；关闭窗口不会退出程序，可从托盘图标重新打开。",
                         style="Muted.TLabel")
        hint.pack(fill="x", pady=(6, 0))

    def _build_status(self) -> None:
        bar = ttk.Frame(self.root, padding=(10, 6))
        bar.pack(fill="x")
        self.var_clock = tk.StringVar(value="")
        self.var_summary = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self.var_clock, style="Muted.TLabel").pack(side="left")
        ttk.Label(bar, textvariable=self.var_summary, style="Muted.TLabel").pack(side="right")

    def _popup_menu(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_set(iid)
            self._menu.tk_popup(event.x_root, event.y_root)

    # ------------------------------------------------------------ 数据

    def refresh(self) -> None:
        selected = self.tree.selection()
        prev_id = selected[0] if selected else None
        for item in self.tree.get_children():
            self.tree.delete(item)

        for task in storage.list_tasks():
            tags = ("disabled",) if (not task.enabled or task.completed) else ("active",)
            self.tree.insert(
                "", "end", iid=str(task.id),
                values=(task.title, task.kind_label, task.rule_text(),
                        task.next_run or "-", task.status_text(), task.run_count),
                tags=tags,
            )
        if prev_id and self.tree.exists(prev_id):
            self.tree.selection_set(prev_id)
        self._update_summary()

    def _update_summary(self) -> None:
        active = storage.count_active()
        nxt = storage.next_pending()
        text = f"活跃任务 {active} 个"
        if nxt:
            text += f"　|　下一次：{nxt[0]}  {nxt[1]}"
        self.var_summary.set(text)

    def _tick_clock(self) -> None:
        self.var_clock.set(datetime.now().strftime("%Y-%m-%d %H:%M:%S   %A"))
        self.root.after(1000, self._tick_clock)

    def selected_task(self) -> Task | None:
        sel = self.tree.selection()
        if not sel:
            return None
        try:
            return storage.get_task(int(sel[0]))
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------ 操作

    def new_task(self) -> None:
        task = ask_task(self.root)
        if task:
            storage.add_task(task)
            self.refresh()
            self.app.scheduler.wakeup()

    def edit_selected(self) -> None:
        task = self.selected_task()
        if not task:
            messagebox.showinfo("提示", "请先选择一个任务")
            return
        updated = ask_task(self.root, task)
        if updated:
            storage.update_task(updated)
            self.refresh()
            self.app.scheduler.wakeup()

    def copy_selected(self) -> None:
        task = self.selected_task()
        if not task:
            messagebox.showinfo("提示", "请先选择一个任务")
            return
        clone = Task(**{**task.__dict__, "id": None, "run_count": 0,
                        "last_run": None, "next_run": None, "completed": False,
                        "snooze_until": None})
        clone.title = f"{task.title} (副本)"
        storage.add_task(clone)
        self.refresh()
        self.app.scheduler.wakeup()

    def toggle_selected(self) -> None:
        task = self.selected_task()
        if not task:
            messagebox.showinfo("提示", "请先选择一个任务")
            return
        storage.set_enabled(task.id, not task.enabled)
        self.refresh()
        self.app.scheduler.wakeup()

    def delete_selected(self) -> None:
        task = self.selected_task()
        if not task:
            messagebox.showinfo("提示", "请先选择一个任务")
            return
        if messagebox.askyesno("确认删除", f"确定删除「{task.title}」？", parent=self.root):
            storage.delete_task(task.id)
            self.refresh()
            self.app.scheduler.wakeup()

    def test_selected(self) -> None:
        task = self.selected_task()
        if not task:
            messagebox.showinfo("提示", "请先选择一个任务")
            return
        self.app.fire_manual(task)

    # ------------------------------------------------------------ 窗口

    def show_history(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("提醒历史")
        win.geometry("620x420")
        win.transient(self.root)
        cols = ("fired", "title", "planned", "missed")
        tree = ttk.Treeview(win, columns=cols, show="headings")
        for col, text, w in (("fired", "实际提醒时间", 150), ("title", "标题", 200),
                             ("planned", "计划时间", 150), ("missed", "补发", 60)):
            tree.heading(col, text=text)
            tree.column(col, width=w, anchor="center" if col == "missed" else "w")
        for row in storage.recent_history(300):
            tree.insert("", "end", values=(row["fired_at"], row["title"],
                                           row["planned_at"] or "-",
                                           "是" if row["missed"] else ""))
        tree.pack(fill="both", expand=True, padx=10, pady=10)
        ttk.Button(win, text="关闭", command=win.destroy).pack(pady=(0, 10))

    def open_settings(self) -> None:
        data = settings.load()
        win = tk.Toplevel(self.root)
        win.title("选项设置")
        win.resizable(False, False)
        win.transient(self.root)
        body = ttk.Frame(win, padding=16)
        body.pack(fill="both", expand=True)

        vars_ = {}
        fields = [
            ("sound", "播放提示音"),
            ("popup", "弹出提醒窗口"),
            ("toast", "发送 Windows 通知"),
            ("minimize_to_tray", "最小化时隐藏到托盘"),
            ("close_to_tray", "关闭窗口时隐藏到托盘"),
            ("autostart", "开机自动启动"),
        ]
        for key, label in fields:
            var = tk.BooleanVar(value=bool(data.get(key, False)))
            vars_[key] = var
            ttk.Checkbutton(body, text=label, variable=var).pack(anchor="w", pady=2)

        row = ttk.Frame(body)
        row.pack(anchor="w", pady=(10, 0))
        ttk.Label(row, text="错过补发窗口（分钟）").pack(side="left")
        miss_var = tk.IntVar(value=int(data.get("miss_window", 60)))
        tk.Spinbox(row, from_=0, to=1440, width=6, textvariable=miss_var,
                   justify="center").pack(side="left", padx=(8, 0))
        ttk.Label(row, text="超出该时长则不再补发，直接跳到下一次",
                  style="Muted.TLabel").pack(side="left", padx=(8, 0))

        def save_and_close():
            payload = {k: v.get() for k, v in vars_.items()}
            payload["miss_window"] = int(miss_var.get())
            settings.save(payload)
            autostart.set_enabled(bool(payload.get("autostart")))
            self.app.apply_settings()
            win.destroy()

        btns = ttk.Frame(body)
        btns.pack(anchor="e", pady=(16, 0))
        ttk.Button(btns, text="取消", command=win.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(btns, text="保存", style="Accent.TButton",
                   command=save_and_close).pack(side="right")

    def show_about(self) -> None:
        messagebox.showinfo(
            "关于",
            "Windows 定时提醒器\n\n"
            "支持一次性提醒与周期性提醒（每天 / 每周 / 每月 / 每隔 N 分钟），\n"
            "最小时间粒度为 1 分钟。\n\n"
            "数据保存在本地 SQLite 数据库中，无需联网。",
            parent=self.root,
        )

    # ------------------------------------------------------------ 显示控制

    def show(self) -> None:
        self.root.deiconify()
        self.root.lift()
        try:
            self.root.attributes("-topmost", True)
            self.root.after(300, lambda: self.root.attributes("-topmost", False))
        except Exception:
            pass
        self.refresh()

    def hide(self) -> None:
        self.root.withdraw()
