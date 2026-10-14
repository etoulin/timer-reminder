"""SQLite 数据访问层。

每个线程使用独立连接（check_same_thread 限制），因此这里用 threading.local
保存连接；写入操作通过一把全局锁串行化，避免并发写冲突。
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from typing import Iterable

from . import config
from .models import FMT, Task, bootstrap_next, now_minute

_LOCAL = threading.local()
_WRITE_LOCK = threading.RLock()


# ------------------------------------------------------------------ 连接


def connect() -> sqlite3.Connection:
    conn = getattr(_LOCAL, "conn", None)
    if conn is None:
        conn = sqlite3.connect(str(config.DB_PATH), timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _LOCAL.conn = conn
    return conn


def init_db() -> None:
    with _WRITE_LOCK:
        conn = connect()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                title        TEXT    NOT NULL,
                message      TEXT    DEFAULT '',
                kind         TEXT    NOT NULL,
                enabled      INTEGER NOT NULL DEFAULT 1,
                sound        INTEGER NOT NULL DEFAULT 1,
                advance_min  INTEGER NOT NULL DEFAULT 0,
                start_at     TEXT,
                time_of_day  TEXT    DEFAULT '09:00',
                weekdays     TEXT    DEFAULT '',
                month_day    INTEGER DEFAULT 1,
                interval_min INTEGER DEFAULT 60,
                anchor       TEXT,
                next_run     TEXT,
                last_run     TEXT,
                run_count    INTEGER NOT NULL DEFAULT 0,
                snooze_until TEXT,
                completed    INTEGER NOT NULL DEFAULT 0,
                created_at   TEXT,
                updated_at   TEXT
            );
            CREATE TABLE IF NOT EXISTS history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id    INTEGER,
                title      TEXT,
                fired_at   TEXT,
                planned_at TEXT,
                missed     INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_history_task ON history(task_id);
            """
        )
        conn.commit()


# ------------------------------------------------------------------ 行 <-> 对象


def _row_to_task(row: sqlite3.Row) -> Task:
    weekdays = [int(x) for x in (row["weekdays"] or "").split(",") if x.strip()]
    return Task(
        id=row["id"],
        title=row["title"],
        message=row["message"] or "",
        kind=row["kind"],
        enabled=bool(row["enabled"]),
        sound=bool(row["sound"]),
        advance_min=row["advance_min"] or 0,
        start_at=row["start_at"],
        time_of_day=row["time_of_day"] or "09:00",
        weekdays=weekdays,
        month_day=row["month_day"] or 1,
        interval_min=row["interval_min"] or 60,
        anchor=row["anchor"],
        next_run=row["next_run"],
        last_run=row["last_run"],
        run_count=row["run_count"] or 0,
        snooze_until=row["snooze_until"],
        completed=bool(row["completed"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _task_to_values(t: Task, *, include_pk: bool = False) -> tuple:
    stamp = datetime.now().strftime(FMT)
    values = (
        t.title,
        t.message,
        t.kind,
        int(t.enabled),
        int(t.sound),
        max(0, int(t.advance_min or 0)),
        t.start_at,
        t.time_of_day,
        ",".join(str(d) for d in sorted(set(t.weekdays))),
        t.month_day,
        t.interval_min,
        t.anchor,
        t.next_run,
        t.last_run,
        int(t.run_count or 0),
        t.snooze_until,
        int(t.completed),
        t.updated_at or stamp,
    )
    if include_pk:
        values = values + (t.id,)
    return values


_COLUMNS = (
    "title, message, kind, enabled, sound, advance_min, start_at, time_of_day, "
    "weekdays, month_day, interval_min, anchor, next_run, last_run, run_count, "
    "snooze_until, completed, updated_at"
)


# ------------------------------------------------------------------ CRUD


def list_tasks(include_disabled: bool = True) -> list[Task]:
    conn = connect()
    sql = "SELECT * FROM tasks"
    if not include_disabled:
        sql += " WHERE enabled=1 AND completed=0"
    sql += " ORDER BY (next_run IS NULL), next_run, id"
    rows = conn.execute(sql).fetchall()
    return [_row_to_task(r) for r in rows]


def get_task(task_id: int) -> Task | None:
    conn = connect()
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    return _row_to_task(row) if row else None


def add_task(task: Task) -> int:
    """插入任务，并自动初始化 next_run，返回新 id。"""
    stamp = datetime.now().strftime(FMT)
    task.created_at = task.created_at or stamp
    task.updated_at = stamp
    if task.kind == "interval" and not task.anchor:
        task.anchor = now_minute().strftime(FMT)
    task.next_run = (
        task.next_run
        or (lambda d: d.strftime(FMT) if d else None)(bootstrap_next(task))
    )
    with _WRITE_LOCK:
        conn = connect()
        cur = conn.execute(
            f"INSERT INTO tasks ({_COLUMNS}, created_at) "
            f"VALUES ({', '.join('?' * 18)}, ?)",
            _task_to_values(task) + (task.created_at,),
        )
        conn.commit()
        return int(cur.lastrowid)


def update_task(task: Task, *, recalc: bool = True) -> None:
    """更新任务；recalc=True 时同时重算 next_run。"""
    task.updated_at = datetime.now().strftime(FMT)
    if recalc and not task.completed:
        nxt = bootstrap_next(task)
        task.next_run = nxt.strftime(FMT) if nxt else None
    with _WRITE_LOCK:
        conn = connect()
        conn.execute(
            f"UPDATE tasks SET {_COLUMNS} WHERE id=?",
            _task_to_values(task, include_pk=True),
        )
        conn.commit()


def delete_task(task_id: int) -> None:
    with _WRITE_LOCK:
        conn = connect()
        conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        conn.execute("DELETE FROM history WHERE task_id=?", (task_id,))
        conn.commit()


def set_enabled(task_id: int, enabled: bool) -> None:
    with _WRITE_LOCK:
        conn = connect()
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return
        task = _row_to_task(row)
        task.enabled = enabled
        task.snooze_until = None
        if enabled:
            nxt = bootstrap_next(task)
            task.next_run = nxt.strftime(FMT) if nxt else None
            task.updated_at = datetime.now().strftime(FMT)
            conn.execute(
                "UPDATE tasks SET enabled=1, next_run=?, snooze_until=NULL, updated_at=? WHERE id=?",
                (task.next_run, task.updated_at, task_id),
            )
        else:
            conn.execute(
                "UPDATE tasks SET enabled=0, snooze_until=NULL, updated_at=? WHERE id=?",
                (datetime.now().strftime(FMT), task_id),
            )
        conn.commit()


def touch_run(task_id: int, *, last_run: str, next_run: str | None,
              completed: bool = False, snooze_until: str | None = None) -> None:
    """触发或推迟后更新任务状态。"""
    with _WRITE_LOCK:
        conn = connect()
        conn.execute(
            "UPDATE tasks SET last_run=?, next_run=?, run_count=run_count+1, "
            "completed=?, snooze_until=?, updated_at=? WHERE id=?",
            (last_run, next_run, int(completed), snooze_until,
             datetime.now().strftime(FMT), task_id),
        )
        conn.commit()


def add_history(task_id: int | None, title: str, fired_at: str,
                planned_at: str | None, missed: bool) -> None:
    with _WRITE_LOCK:
        conn = connect()
        conn.execute(
            "INSERT INTO history (task_id, title, fired_at, planned_at, missed) VALUES (?,?,?,?,?)",
            (task_id, title, fired_at, planned_at, int(missed)),
        )
        conn.commit()


def recent_history(limit: int = 200) -> list[sqlite3.Row]:
    conn = connect()
    return conn.execute(
        "SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()


def refresh_all_next_runs() -> None:
    """启动时重算所有未完成任务的 next_run。"""
    for task in list_tasks():
        if task.completed or not task.enabled:
            continue
        nxt = bootstrap_next(task)
        new_value = nxt.strftime(FMT) if nxt else None
        if new_value != task.next_run:
            with _WRITE_LOCK:
                conn = connect()
                conn.execute("UPDATE tasks SET next_run=? WHERE id=?", (new_value, task.id))
                conn.commit()


def count_active() -> int:
    conn = connect()
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM tasks WHERE enabled=1 AND completed=0"
    ).fetchone()
    return int(row["c"])


def next_pending() -> tuple[str, str] | None:
    """返回下一个待触发的 (时间, 标题)。"""
    conn = connect()
    row = conn.execute(
        "SELECT next_run, title FROM tasks WHERE enabled=1 AND completed=0 "
        "AND next_run IS NOT NULL ORDER BY next_run LIMIT 1"
    ).fetchone()
    return (row["next_run"], row["title"]) if row else None


def iter_tasks() -> Iterable[Task]:
    return list_tasks()
