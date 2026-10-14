"""调度引擎：后台线程，分钟粒度轮询并触发到期任务。

设计要点
--------
1. 所有时间点截断到分钟，秒/微秒归零 —— 满足「最小粒度为分钟」的要求。
2. 每分钟边界（分钟数变化）执行一次全量扫描；其余时间休眠，开销可忽略。
3. 到期判定使用 ``next_run - advance_min``，即提前提醒量只影响触发时刻，
   不影响下一次计划的推进。
4. 错过补发：若程序未运行导致错过，且错过时长在补发窗口内（默认 60 分钟），
   则立即补提醒并标注；超出窗口则静默跳过并推进到下一次。
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta

from . import config, storage
from .models import FMT, KIND_ONCE, Task, bootstrap_next, now_minute, parse_dt


class Scheduler(threading.Thread):
    """后台调度线程。

    :param on_fire: 触发回调 ``on_fire(task, planned_at: str, missed: bool)``。
                    该回调在调度线程内被调用，实现方需自行切回 UI 线程。
    """

    def __init__(self, on_fire, miss_window_minutes: int | None = None,
                 tick_seconds: float | None = None):
        super().__init__(name="Scheduler", daemon=True)
        self.on_fire = on_fire
        self.miss_window = timedelta(
            minutes=miss_window_minutes or config.MISS_WINDOW_MINUTES
        )
        self.tick_seconds = tick_seconds or config.TICK_SECONDS
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._lock = threading.RLock()
        self._last_minute: datetime | None = None

    # ------------------------------------------------------------ 生命周期

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def wakeup(self) -> None:
        """请求立即执行一次扫描（UI 变更任务后调用）。"""
        self._wake.set()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                now = now_minute()
                forced = self._wake.is_set()
                if forced or self._last_minute is None or now != self._last_minute:
                    self._wake.clear()
                    self._last_minute = now
                    self.tick(now)
                self._wake.wait(self.tick_seconds)
            except Exception:                                   # 调度线程不应因异常退出
                time.sleep(self.tick_seconds)

    # ------------------------------------------------------------ 扫描

    def tick(self, now: datetime | None = None) -> None:
        now = now or now_minute()
        with self._lock:
            for task in storage.list_tasks():
                if self._stop.is_set():
                    return
                self._handle(task, now)

    def _handle(self, task: Task, now: datetime) -> None:
        if not task.enabled or task.completed:
            return

        # 1) 「稍后提醒」优先：到点立即提醒，但不推进既定计划
        if task.snooze_until:
            snooze_at = parse_dt(task.snooze_until)
            if snooze_at is None or now < snooze_at:
                return
            self._emit(task, task.next_run or task.snooze_until, missed=False)
            storage.touch_run(
                task.id, last_run=now.strftime(FMT), next_run=task.next_run,
                snooze_until=None,
            )
            return

        # 2) 没有计划时间则先重算
        if not task.next_run:
            nxt = bootstrap_next(task, now)
            if nxt is None:
                if task.kind == KIND_ONCE:
                    storage.touch_run(task.id, last_run=task.last_run or "",
                                      next_run=None, completed=True)
                return
            storage.touch_run(task.id, last_run=task.last_run or "",
                              next_run=nxt.strftime(FMT))
            task.next_run = nxt.strftime(FMT)
            return

        # 3) 推进所有已到期（含提前量）的时间点；
        #    只真正提醒最近的一次，避免程序长时间未运行时连环补发。
        due: datetime | None = None
        for _ in range(500):
            planned = parse_dt(task.next_run)
            if planned is None:
                return
            effective = planned - timedelta(minutes=max(0, task.advance_min or 0))
            if effective > now:
                break
            due = planned
            if task.kind == KIND_ONCE:
                break
            nxt = task.compute_next(planned)
            next_text = nxt.strftime(FMT) if nxt else None
            task.next_run = next_text
            if next_text is None:
                break

        if due is None:
            return

        missed = due < now
        if (not missed) or ((now - due) <= self.miss_window):
            self._emit(task, due.strftime(FMT), missed)

        if task.kind == KIND_ONCE:
            storage.touch_run(task.id, last_run=now.strftime(FMT),
                              next_run=None, completed=True)
        else:
            storage.touch_run(task.id, last_run=now.strftime(FMT), next_run=task.next_run)

    # ------------------------------------------------------------ 触发

    def _emit(self, task: Task, planned_at: str | None, missed: bool) -> None:
        try:
            storage.add_history(
                task.id, task.title, now_minute().strftime(FMT), planned_at, missed
            )
        except Exception:
            pass
        snapshot = Task(**{**task.__dict__})       # 拷贝，避免回调期间对象被改动
        try:
            self.on_fire(snapshot, planned_at or now_minute().strftime(FMT), missed)
        except Exception:
            pass
