"""调度逻辑单元测试（不依赖 GUI）。

运行： .venv\\Scripts\\python.exe -m unittest discover -s tests
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config, storage  # noqa: E402
from src.models import (FMT, KIND_DAILY, KIND_INTERVAL, KIND_MONTHLY,  # noqa: E402
                        KIND_ONCE, KIND_WEEKLY, Task, bootstrap_next,
                        compute_next, now_minute)


def T(**kw) -> Task:
    return Task(**kw)


class TestComputeNext(unittest.TestCase):
    def test_once(self):
        t = T(kind=KIND_ONCE, start_at="2030-01-01 09:00")
        self.assertEqual(compute_next(t, datetime(2029, 1, 1, 0, 0)),
                         datetime(2030, 1, 1, 9, 0))
        # 已过期的一次性任务没有下一次
        self.assertIsNone(compute_next(t, datetime(2031, 1, 1, 0, 0)))

    def test_daily(self):
        t = T(kind=KIND_DAILY, time_of_day="09:30")
        self.assertEqual(compute_next(t, datetime(2026, 5, 1, 8, 0)),
                         datetime(2026, 5, 1, 9, 30))
        self.assertEqual(compute_next(t, datetime(2026, 5, 1, 9, 30)),
                         datetime(2026, 5, 2, 9, 30))
        self.assertEqual(compute_next(t, datetime(2026, 5, 1, 23, 59)),
                         datetime(2026, 5, 2, 9, 30))

    def test_weekly(self):
        # 2026-10-14 是周三（isoweekday=3）
        t = T(kind=KIND_WEEKLY, time_of_day="08:00", weekdays=[3])
        self.assertEqual(compute_next(t, datetime(2026, 10, 14, 7, 0)),
                         datetime(2026, 10, 14, 8, 0))
        self.assertEqual(compute_next(t, datetime(2026, 10, 14, 9, 0)),
                         datetime(2026, 10, 21, 8, 0))

        t2 = T(kind=KIND_WEEKLY, time_of_day="08:00", weekdays=[1, 5])
        self.assertEqual(compute_next(t2, datetime(2026, 10, 14, 9, 0)),
                         datetime(2026, 10, 16, 8, 0))     # 周五

    def test_monthly_clamp(self):
        t = T(kind=KIND_MONTHLY, time_of_day="10:00", month_day=31)
        # 2026-02 只有 28 天，应钳制到 28 号
        self.assertEqual(compute_next(t, datetime(2026, 1, 31, 11, 0)),
                         datetime(2026, 2, 28, 10, 0))
        self.assertEqual(compute_next(t, datetime(2026, 2, 28, 11, 0)),
                         datetime(2026, 3, 31, 10, 0))

    def test_interval_minute_granularity(self):
        anchor = datetime(2026, 10, 14, 10, 0)
        t = T(kind=KIND_INTERVAL, interval_min=1, anchor=anchor.strftime(FMT))
        self.assertEqual(compute_next(t, datetime(2026, 10, 14, 10, 0)),
                         datetime(2026, 10, 14, 10, 1))

        t5 = T(kind=KIND_INTERVAL, interval_min=5, anchor=anchor.strftime(FMT))
        self.assertEqual(compute_next(t5, datetime(2026, 10, 14, 10, 1)),
                         datetime(2026, 10, 14, 10, 5))
        self.assertEqual(compute_next(t5, datetime(2026, 10, 14, 10, 5)),
                         datetime(2026, 10, 14, 10, 10))
        # 跨越较长时间后仍与基准对齐
        self.assertEqual(compute_next(t5, datetime(2026, 10, 14, 13, 33)),
                         datetime(2026, 10, 14, 13, 35))

    def test_interval_never_goes_backwards(self):
        anchor = "2026-10-14 00:00"
        t = T(kind=KIND_INTERVAL, interval_min=30, anchor=anchor)
        cur = datetime(2026, 10, 14, 0, 0)
        for _ in range(100):
            nxt = compute_next(t, cur)
            self.assertGreater(nxt, cur)
            cur = nxt


class TestBootstrap(unittest.TestCase):
    def test_bootstrap_includes_current_minute(self):
        now = datetime(2026, 10, 14, 9, 0)
        t = T(kind=KIND_DAILY, time_of_day="09:00")
        self.assertEqual(bootstrap_next(t, now), datetime(2026, 10, 14, 9, 0))

    def test_bootstrap_after_current_minute(self):
        now = datetime(2026, 10, 14, 9, 1)
        t = T(kind=KIND_DAILY, time_of_day="09:00")
        self.assertEqual(bootstrap_next(t, now), datetime(2026, 10, 15, 9, 0))


class TestStorage(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        config.DATA_DIR = Path(self._tmp.name)
        config.DB_PATH = config.DATA_DIR / "test.db"
        self.addCleanup(self._close_and_cleanup)
        storage._LOCAL = __import__("threading").local()
        storage.init_db()

    def _close_and_cleanup(self):
        import threading
        try:
            conn = getattr(storage._LOCAL, "conn", None)
            if conn is not None:
                conn.close()
        except Exception:
            pass
        storage._LOCAL = threading.local()
        self._tmp.cleanup()

    def test_add_and_list(self):
        t = Task(title="喝水", kind=KIND_INTERVAL, interval_min=30,
                 anchor="2026-10-14 09:00")
        tid = storage.add_task(t)
        got = storage.get_task(tid)
        self.assertEqual(got.title, "喝水")
        self.assertIsNotNone(got.next_run)
        self.assertEqual(storage.count_active(), 1)

    def test_delete(self):
        tid = storage.add_task(Task(title="x", kind=KIND_DAILY, time_of_day="10:00"))
        storage.delete_task(tid)
        self.assertIsNone(storage.get_task(tid))


if __name__ == "__main__":
    unittest.main(verbosity=2)
