"""任务新增/编辑对话框。

按「提醒类型」动态切换参数面板：
- 一次性：日期 + 时间
- 每天：时间
- 每周：星期多选 + 时间
- 每月：几号 + 时间
- 间隔：每 N 分钟（最小 1 分钟）+ 起始基准时间
"""

from __future__ import annotations

import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox, ttk

from ..models import (FMT, FMT_DAY, KIND_DAILY, KIND_INTERVAL, KIND_MONTHLY,
                      KIND_ONCE, KIND_WEEKLY, WEEKDAY_LABELS, Task,
                      bootstrap_next, now_minute, parse_dt)

HOURS = tuple(f"{h:02d}" for h in range(24))
MINUTES = tuple(f"{m:02d}" for m in range(60))
FONT = ("Microsoft YaHei UI", 10)
FONT_SMALL = ("Microsoft YaHei UI", 9)


def _time_picker(parent, hour_var: tk.StringVar, minute_var: tk.StringVar) -> tk.Frame:
    frm = tk.Frame(parent)
    h = tk.Spinbox(frm, values=HOURS, width=3, justify="center", state="readonly",
                   textvariable=hour_var, wrap=True, font=FONT)
    m = tk.Spinbox(frm, values=MINUTES, width=3, justify="center", state="readonly",
                   textvariable=minute_var, wrap=True, font=FONT)
    h.pack(side="left")
    tk.Label(frm, text=":", font=FONT).pack(side="left")
    m.pack(side="left")
    return frm


class TaskDialog(tk.Toplevel):
    def __init__(self, master, initial: Task | None = None):
        super().__init__(master)
        self.initial = initial
        self.result: Task | None = None

        self.title("编辑提醒任务" if initial else "新建提醒任务")
        self.configure(bg="#ffffff")
        self.resizable(False, False)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda e: self._cancel())

        self._init_vars()
        self._build()
        self._update_preview()

        self.grab_set()
        self.center_on_master()
        self.entry_title.focus_set()

    # ------------------------------------------------------------ 变量

    def _init_vars(self) -> None:
        t = self.initial
        now = now_minute()
        default_time = now + timedelta(minutes=5)

        self.var_title = tk.StringVar(value=(t.title if t else ""))
        self.var_kind = tk.StringVar(value=(t.kind if t else KIND_DAILY))

        # 一次性
        start = parse_dt(t.start_at) if (t and t.start_at) else default_time
        self.var_once_date = tk.StringVar(value=start.strftime(FMT_DAY))

        hh, mm = (t.time_of_day.split(":") if (t and t.time_of_day) else
                  (f"{default_time.hour:02d}", f"{default_time.minute:02d}"))
        self.var_hour = tk.StringVar(value=hh)
        self.var_minute = tk.StringVar(value=mm)

        # 每周
        self.var_weekdays = [tk.BooleanVar(value=(d in (t.weekdays if t else [now.isoweekday()])))
                             for d in range(1, 8)]

        # 每月
        self.var_month_day = tk.IntVar(value=(t.month_day if t else min(now.day, 28)))

        # 间隔
        self.var_interval = tk.IntVar(value=(t.interval_min if t else 60))
        anchor = parse_dt(t.anchor) if (t and t.anchor) else now
        self.var_anchor = tk.StringVar(value=anchor.strftime(FMT))

        # 选项
        self.var_enabled = tk.BooleanVar(value=(t.enabled if t else True))
        self.var_sound = tk.BooleanVar(value=(t.sound if t else True))
        self.var_advance = tk.IntVar(value=(t.advance_min if t else 0))

    # ------------------------------------------------------------ 界面

    def _build(self) -> None:
        body = tk.Frame(self, bg="#ffffff", padx=16, pady=12)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="标题", font=FONT, bg="#ffffff", anchor="w").grid(
            row=0, column=0, sticky="w", pady=(0, 4))
        self.entry_title = ttk.Entry(body, textvariable=self.var_title, width=44)
        self.entry_title.grid(row=0, column=1, columnspan=3, sticky="we", pady=(0, 8))

        tk.Label(body, text="内容", font=FONT, bg="#ffffff", anchor="w").grid(
            row=1, column=0, sticky="nw", pady=(0, 4))
        self.text_message = tk.Text(body, width=34, height=4, font=FONT,
                                    relief="solid", borderwidth=1, wrap="word")
        self.text_message.grid(row=1, column=1, columnspan=3, sticky="we", pady=(0, 8))
        if self.initial and self.initial.message:
            self.text_message.insert("1.0", self.initial.message)

        ttk.Separator(body, orient="horizontal").grid(
            row=2, column=0, columnspan=4, sticky="we", pady=8)

        tk.Label(body, text="提醒类型", font=FONT, bg="#ffffff", anchor="w").grid(
            row=3, column=0, sticky="nw")
        kinds = tk.Frame(body, bg="#ffffff")
        kinds.grid(row=3, column=1, columnspan=3, sticky="w")
        for key, label in ((KIND_ONCE, "一次性"), (KIND_DAILY, "每天"),
                           (KIND_WEEKLY, "每周"), (KIND_MONTHLY, "每月"),
                           (KIND_INTERVAL, "间隔(分钟)")):
            ttk.Radiobutton(kinds, text=label, value=key, variable=self.var_kind,
                            command=self._on_kind_change).pack(side="left", padx=(0, 10))

        self.panel = tk.Frame(body, bg="#ffffff")
        self.panel.grid(row=4, column=0, columnspan=4, sticky="we", pady=(10, 4))
        self._panels: dict[str, tk.Frame] = {}
        self._build_panels()

        ttk.Separator(body, orient="horizontal").grid(
            row=5, column=0, columnspan=4, sticky="we", pady=8)

        # 高级选项
        opts = tk.Frame(body, bg="#ffffff")
        opts.grid(row=6, column=0, columnspan=4, sticky="w")
        ttk.Checkbutton(opts, text="启用", variable=self.var_enabled).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(opts, text="提示音", variable=self.var_sound).pack(side="left", padx=(0, 12))
        tk.Label(opts, text="提前", font=FONT_SMALL, bg="#ffffff").pack(side="left")
        tk.Spinbox(opts, from_=0, to=120, width=4, textvariable=self.var_advance,
                   font=FONT_SMALL, justify="center").pack(side="left", padx=(4, 2))
        tk.Label(opts, text="分钟提醒", font=FONT_SMALL, bg="#ffffff").pack(side="left")

        self.label_preview = tk.Label(body, text="", font=FONT_SMALL, fg="#2563eb",
                                      bg="#ffffff", anchor="w")
        self.label_preview.grid(row=7, column=0, columnspan=4, sticky="w", pady=(10, 0))

        self._on_kind_change()      # 需在 label_preview 创建之后调用

        btns = tk.Frame(body, bg="#ffffff")
        btns.grid(row=8, column=0, columnspan=4, sticky="e", pady=(12, 0))
        ttk.Button(btns, text="取消", command=self._cancel).pack(side="right", padx=(8, 0))
        ttk.Button(btns, text="保存", style="Accent.TButton",
                   command=self._save).pack(side="right")

        for var in (self.var_title, self.var_hour, self.var_minute, self.var_once_date,
                    self.var_anchor):
            var.trace_add("write", lambda *_: self._update_preview())
        for var in self.var_weekdays:
            var.trace_add("write", lambda *_: self._update_preview())
        self.var_month_day.trace_add("write", lambda *_: self._update_preview())
        self.var_interval.trace_add("write", lambda *_: self._update_preview())

    def _build_panels(self) -> None:
        # --- 一次性
        p = tk.Frame(self.panel, bg="#ffffff")
        tk.Label(p, text="日期", font=FONT, bg="#ffffff").pack(side="left")
        e = ttk.Entry(p, textvariable=self.var_once_date, width=12)
        e.pack(side="left", padx=(6, 4))
        tk.Label(p, text="(YYYY-MM-DD)", font=FONT_SMALL, fg="#6b7280",
                 bg="#ffffff").pack(side="left", padx=(0, 8))
        ttk.Button(p, text="今天", width=6,
                   command=lambda: self.var_once_date.set(datetime.now().strftime(FMT_DAY))
                   ).pack(side="left", padx=(0, 4))
        ttk.Button(p, text="明天", width=6,
                   command=lambda: self.var_once_date.set(
                       (datetime.now() + timedelta(days=1)).strftime(FMT_DAY))
                   ).pack(side="left", padx=(0, 12))
        tk.Label(p, text="时间", font=FONT, bg="#ffffff").pack(side="left")
        _time_picker(p, self.var_hour, self.var_minute).pack(side="left", padx=(6, 0))
        self._panels[KIND_ONCE] = p

        # --- 每天
        p = tk.Frame(self.panel, bg="#ffffff")
        tk.Label(p, text="时间", font=FONT, bg="#ffffff").pack(side="left")
        _time_picker(p, self.var_hour, self.var_minute).pack(side="left", padx=(6, 0))
        self._panels[KIND_DAILY] = p

        # --- 每周
        p = tk.Frame(self.panel, bg="#ffffff")
        for i, var in enumerate(self.var_weekdays):
            ttk.Checkbutton(p, text=WEEKDAY_LABELS[i], variable=var).pack(
                side="left", padx=(0, 4))
        sub = tk.Frame(p, bg="#ffffff")
        sub.pack(side="left", padx=(12, 0))
        tk.Label(sub, text="时间", font=FONT, bg="#ffffff").pack(side="left")
        _time_picker(sub, self.var_hour, self.var_minute).pack(side="left", padx=(6, 0))
        self._panels[KIND_WEEKLY] = p

        # --- 每月
        p = tk.Frame(self.panel, bg="#ffffff")
        tk.Label(p, text="每月", font=FONT, bg="#ffffff").pack(side="left")
        tk.Spinbox(p, from_=1, to=31, width=4, textvariable=self.var_month_day,
                   font=FONT, justify="center", wrap=True).pack(side="left", padx=(6, 2))
        tk.Label(p, text="号", font=FONT, bg="#ffffff").pack(side="left", padx=(0, 12))
        tk.Label(p, text="时间", font=FONT, bg="#ffffff").pack(side="left")
        _time_picker(p, self.var_hour, self.var_minute).pack(side="left", padx=(6, 0))
        self._panels[KIND_MONTHLY] = p

        # --- 间隔
        p = tk.Frame(self.panel, bg="#ffffff")
        tk.Label(p, text="每隔", font=FONT, bg="#ffffff").pack(side="left")
        tk.Spinbox(p, from_=1, to=1440, width=6, textvariable=self.var_interval,
                   font=FONT, justify="center", wrap=True).pack(side="left", padx=(6, 2))
        tk.Label(p, text="分钟（最小 1 分钟）", font=FONT_SMALL, fg="#6b7280",
                 bg="#ffffff").pack(side="left", padx=(0, 12))
        row2 = tk.Frame(p, bg="#ffffff")
        row2.pack(fill="x", pady=(6, 0))
        tk.Label(row2, text="起始时间", font=FONT, bg="#ffffff").pack(side="left")
        ttk.Entry(row2, textvariable=self.var_anchor, width=18).pack(side="left", padx=(6, 4))
        ttk.Button(row2, text="现在", width=6,
                   command=lambda: self.var_anchor.set(now_minute().strftime(FMT))
                   ).pack(side="left")
        tk.Label(row2, text="(YYYY-MM-DD HH:MM)", font=FONT_SMALL, fg="#6b7280",
                 bg="#ffffff").pack(side="left", padx=(6, 0))
        self._panels[KIND_INTERVAL] = p

    # ------------------------------------------------------------ 行为

    def _on_kind_change(self) -> None:
        kind = self.var_kind.get()
        for key, frame in self._panels.items():
            if key == kind:
                frame.pack(fill="x", anchor="w")
            else:
                frame.pack_forget()
        self._update_preview()

    def center_on_master(self) -> None:
        self.update_idletasks()
        try:
            mx, my = self.master.winfo_rootx(), self.master.winfo_rooty()
            mw, mh = self.master.winfo_width(), self.master.winfo_height()
        except Exception:
            mx, my, mw, mh = 0, 0, 800, 600
        w, h = self.winfo_width(), self.winfo_height()
        x = mx + max(0, (mw - w) // 2)
        y = my + max(0, (mh - h) // 2)
        self.geometry(f"+{x}+{y}")

    def _collect(self) -> Task:
        kind = self.var_kind.get()
        t = Task(
            id=self.initial.id if self.initial else None,
            title=self.var_title.get().strip(),
            message=self.text_message.get("1.0", "end").strip(),
            kind=kind,
            enabled=self.var_enabled.get(),
            sound=self.var_sound.get(),
            advance_min=self.var_advance.get(),
            time_of_day=f"{self.var_hour.get()}:{self.var_minute.get()}",
            weekdays=[d for d, var in enumerate(self.var_weekdays, start=1) if var.get()],
            month_day=self.var_month_day.get(),
            interval_min=self.var_interval.get(),
            anchor=self.var_anchor.get().strip(),
            created_at=self.initial.created_at if self.initial else None,
        )
        if kind == KIND_ONCE:
            t.start_at = f"{self.var_once_date.get().strip()} {t.time_of_day}"
        return t

    def _update_preview(self) -> None:
        try:
            task = self._collect()
        except Exception:
            return
        if task.kind == KIND_ONCE:
            dt = parse_dt(task.start_at)
            if dt is None:
                self.label_preview.config(text="日期格式应为 YYYY-MM-DD", fg="#dc2626")
                return
            if dt <= now_minute():
                self.label_preview.config(text="该时间已过去，保存后将不会触发", fg="#d97706")
                return
            self.label_preview.config(text=f"将在 {task.start_at} 提醒一次", fg="#2563eb")
            return
        nxt = bootstrap_next(task)
        if nxt is None:
            self.label_preview.config(text="当前设置无法计算出下一次时间", fg="#dc2626")
            return
        self.label_preview.config(
            text=f"下一次提醒：{nxt.strftime(FMT)}（{task.rule_text()}）", fg="#2563eb")

    def _validate(self) -> str | None:
        if not self.var_title.get().strip():
            return "请填写提醒标题"
        kind = self.var_kind.get()
        if kind == KIND_ONCE:
            dt = parse_dt(f"{self.var_once_date.get().strip()} "
                          f"{self.var_hour.get()}:{self.var_minute.get()}")
            if dt is None:
                return "日期格式应为 YYYY-MM-DD"
            if dt <= now_minute() and not (self.initial and self.initial.id):
                return "一次性提醒的时间必须晚于当前时间"
        if kind == KIND_WEEKLY and not any(v.get() for v in self.var_weekdays):
            return "请至少选择一个星期"
        if kind == KIND_INTERVAL:
            try:
                n = int(self.var_interval.get())
            except (TypeError, ValueError):
                return "间隔分钟数无效"
            if n < 1 or n > 1440:
                return "间隔分钟数应在 1 - 1440 之间"
            if parse_dt(self.var_anchor.get().strip()) is None:
                return "起始时间格式应为 YYYY-MM-DD HH:MM"
        if kind == KIND_MONTHLY:
            if not 1 <= int(self.var_month_day.get()) <= 31:
                return "日期应在 1 - 31 之间"
        return None

    def _save(self) -> None:
        err = self._validate()
        if err:
            messagebox.showwarning("请检查输入", err, parent=self)
            return
        self.result = self._collect()
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


def ask_task(master, initial: Task | None = None) -> Task | None:
    """模态打开编辑对话框，返回 Task（取消返回 None）。"""
    dlg = TaskDialog(master, initial)
    master.wait_window(dlg)
    return dlg.result
