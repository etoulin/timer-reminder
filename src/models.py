"""任务数据模型与下一次触发时间的计算逻辑。

本模块保持纯逻辑（不依赖 tkinter / sqlite），便于单元测试。
时间粒度统一为「分钟」，即所有时间点都精确到分钟，秒与微秒归零。
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import datetime, timedelta

# ---------------------------------------------------------------- 常量

FMT = "%Y-%m-%d %H:%M"          # 数据库中 datetime 的文本格式
FMT_DAY = "%Y-%m-%d"

KIND_ONCE = "once"              # 非周期性：指定日期时间，只提醒一次
KIND_DAILY = "daily"            # 每天
KIND_WEEKLY = "weekly"          # 每周（可多选星期）
KIND_MONTHLY = "monthly"        # 每月（指定几号）
KIND_INTERVAL = "interval"      # 每隔 N 分钟（最小粒度 1 分钟）

KIND_LABELS = {
    KIND_ONCE: "一次性",
    KIND_DAILY: "每天",
    KIND_WEEKLY: "每周",
    KIND_MONTHLY: "每月",
    KIND_INTERVAL: "间隔（分钟）",
}

WEEKDAY_LABELS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# 周期性类型集合（用于 UI 与调度分支判断）
RECURRING_KINDS = (KIND_DAILY, KIND_WEEKLY, KIND_MONTHLY, KIND_INTERVAL)


def now_minute() -> datetime:
    """当前时间，截断到分钟。"""
    return datetime.now().replace(second=0, microsecond=0)


def parse_dt(text: str | None) -> datetime | None:
    if not text:
        return None
    return datetime.strptime(text, FMT)


def fmt_dt(dt: datetime | None) -> str | None:
    return dt.strftime(FMT) if dt else None


def parse_hm(text: str | None, default: tuple[int, int] = (9, 0)) -> tuple[int, int]:
    """解析 'HH:MM'，失败时返回默认值。"""
    if not text:
        return default
    try:
        hh, mm = text.split(":")
        return int(hh), int(mm)
    except (ValueError, AttributeError):
        return default


# ---------------------------------------------------------------- 模型


@dataclass
class Task:
    id: int | None = None
    title: str = ""
    message: str = ""
    kind: str = KIND_DAILY
    enabled: bool = True
    sound: bool = True
    advance_min: int = 0             # 提前提醒分钟数（0 表示不提前）

    start_at: str | None = None      # once: 'YYYY-MM-DD HH:MM'
    time_of_day: str = "09:00"       # daily/weekly/monthly: 'HH:MM'
    weekdays: list[int] = field(default_factory=list)   # weekly: ISO 1=周一 ... 7=周日
    month_day: int = 1               # monthly: 1-31（不足时钳制到当月最后一天）
    interval_min: int = 60           # interval: 1-1440 分钟
    anchor: str | None = None        # interval: 基准时间 'YYYY-MM-DD HH:MM'

    next_run: str | None = None      # 下一次计划触发时间
    last_run: str | None = None
    run_count: int = 0
    snooze_until: str | None = None  # 「稍后提醒」的目标时间
    completed: bool = False          # 一次性任务是否已触发完成

    created_at: str | None = None
    updated_at: str | None = None

    # ------------------------------------------------------------ 展示

    @property
    def kind_label(self) -> str:
        return KIND_LABELS.get(self.kind, self.kind)

    def rule_text(self) -> str:
        """人类可读的规则描述，用于列表展示。"""
        if self.kind == KIND_ONCE:
            return f"一次性 {self.start_at or '-'}"
        if self.kind == KIND_DAILY:
            return f"每天 {self.time_of_day}"
        if self.kind == KIND_WEEKLY:
            names = "/".join(WEEKDAY_LABELS[d - 1] for d in sorted(self.weekdays)) or "未选"
            return f"每周 {names} {self.time_of_day}"
        if self.kind == KIND_MONTHLY:
            return f"每月 {self.month_day} 号 {self.time_of_day}"
        if self.kind == KIND_INTERVAL:
            n = self.interval_min
            if n % 60 == 0 and n >= 60:
                return f"每 {n // 60} 小时（从 {self.anchor or '现在'} 起）"
            return f"每 {n} 分钟（从 {self.anchor or '现在'} 起）"
        return "-"

    def status_text(self) -> str:
        if self.completed:
            return "已完成"
        if not self.enabled:
            return "已停用"
        if self.snooze_until:
            return f"已推迟至 {self.snooze_until}"
        return "运行中"

    # ------------------------------------------------------------ 调度

    def effective_time(self) -> datetime | None:
        """实际用于比较的触发时刻（含提前提醒量）。"""
        base = parse_dt(self.next_run)
        if base is None:
            return None
        return base - timedelta(minutes=max(0, self.advance_min))

    def compute_next(self, after: datetime) -> datetime | None:
        """计算严格晚于 after 的下一次触发时间；无下一次时返回 None。"""
        return compute_next(self, after)


# ---------------------------------------------------------------- 计算


def _time_of_day(task: Task) -> tuple[int, int]:
    return parse_hm(task.time_of_day)


def compute_next(task: Task, after: datetime) -> datetime | None:
    """根据任务类型计算下一次触发时间（严格 > after）。"""
    after = after.replace(second=0, microsecond=0)

    if task.kind == KIND_ONCE:
        start = parse_dt(task.start_at)
        if start is None or start <= after:
            return None
        return start

    if task.kind == KIND_DAILY:
        hh, mm = _time_of_day(task)
        cand = after.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if cand > after:
            return cand
        return cand + timedelta(days=1)

    if task.kind == KIND_WEEKLY:
        hh, mm = _time_of_day(task)
        days = sorted({d for d in task.weekdays if 1 <= d <= 7})
        if not days:
            return None
        for offset in range(0, 8):
            day = after.date() + timedelta(days=offset)
            if day.isoweekday() not in days:
                continue
            cand = datetime(day.year, day.month, day.day, hh, mm)
            if cand > after:
                return cand
        return None

    if task.kind == KIND_MONTHLY:
        hh, mm = _time_of_day(task)
        day = min(max(task.month_day, 1), 31)
        year, month = after.year, after.month
        for _ in range(0, 25):
            last = calendar.monthrange(year, month)[1]
            cand = datetime(year, month, min(day, last), hh, mm)
            if cand > after:
                return cand
            month += 1
            if month > 12:
                month = 1
                year += 1
        return None

    if task.kind == KIND_INTERVAL:
        step = max(1, int(task.interval_min or 1))
        anchor = parse_dt(task.anchor) or after
        delta = after - anchor
        elapsed = int(delta.total_seconds() // 60)
        k = elapsed // step + 1
        cand = anchor + timedelta(minutes=step * k)
        while cand <= after:
            k += 1
            cand = anchor + timedelta(minutes=step * k)
        return cand.replace(second=0, microsecond=0)

    return None


def bootstrap_next(task: Task, now: datetime | None = None) -> datetime | None:
    """初始化/重算 next_run。

    - 一次性任务：直接返回其设定时间（即使已过期，交由调度器判断是否补提醒）。
    - 周期任务：返回严格晚于 now 的下一次时间。
    """
    now = (now or now_minute()).replace(second=0, microsecond=0)
    if task.kind == KIND_ONCE:
        return parse_dt(task.start_at)
    # 周期任务：先尝试「包含当前分钟」的候选（例如 09:00 的任务在 09:00 应触发），
    # 因此以 now 前一分钟作为基准来取下一次，再修正掉早于 now 的结果。
    base = now - timedelta(minutes=1)
    cand = compute_next(task, base)
    if cand is None:
        return None
    if cand < now:
        cand = compute_next(task, now)
    return cand
