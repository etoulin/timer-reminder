"""GUI 冒烟测试：真启动窗口与调度线程，验证「任务 -> 触发 -> 弹窗 -> 推迟」链路。

运行： .venv\\Scripts\\python.exe tests\\smoke_gui.py
"""

from __future__ import annotations

import sys
import time
import tkinter as tk
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import storage                                    # noqa: E402
from src.models import FMT, KIND_INTERVAL, Task, now_minute  # noqa: E402

from main import App                                       # noqa: E402


def pump(app, seconds: float = 0.3, step: float = 0.05):
    end = time.time() + seconds
    while time.time() < end:
        app.root.update()
        time.sleep(step)


def main() -> int:
    app = App(show_window=False, use_tray=True)
    app.scheduler.start()
    app.dispatcher.start()          # 正常情况下由 app.run() 启动
    pump(app, 0.3)

    now = now_minute()
    task = Task(
        title="冒烟测试任务",
        message="这是一条用于验证的提醒",
        kind=KIND_INTERVAL,
        interval_min=5,
        anchor=(now - timedelta(minutes=5)).strftime(FMT),
    )
    tid = storage.add_task(task)
    print(f"[1] 已创建任务 id={tid}, next_run={storage.get_task(tid).next_run}")

    # 把 next_run 调整到「已到期」，验证调度器立即触发
    past = (now - timedelta(minutes=1)).strftime(FMT)
    storage.touch_run(tid, last_run="", next_run=past)
    app.scheduler.wakeup()
    pump(app, 1.5)

    fired = storage.recent_history(5)
    print(f"[2] 历史记录条数={len(fired)}，最近一条={dict(fired[0]) if fired else None}")
    print(f"[3] 弹窗数量={len(app.alerts.windows)}")
    assert len(app.alerts.windows) >= 1, "提醒弹窗未弹出"
    assert fired, "未写入提醒历史"

    # 稍后提醒
    app.snooze(tid, 10)
    t2 = storage.get_task(tid)
    print(f"[4] 推迟后 snooze_until={t2.snooze_until}, next_run={t2.next_run}")
    assert t2.snooze_until is not None, "稍后提醒未生效"

    # 主窗口列表
    app.window.show()
    pump(app, 0.5)
    rows = app.window.tree.get_children()
    print(f"[5] 主窗口任务行数={len(rows)}")
    assert rows, "主窗口未渲染任务"

    # 编辑对话框（只构建不交互）
    from src.ui.task_dialog import TaskDialog
    dlg = TaskDialog(app.window.root, storage.get_task(tid))
    pump(app, 0.3)
    print(f"[6] 对话框预览={dlg.label_preview.cget('text')}")
    dlg.destroy()

    # 设置窗口
    app.window.open_settings()
    pump(app, 0.3)
    toplevels = [w for w in app.root.winfo_children() if isinstance(w, tk.Toplevel)]
    print(f"[7] 设置窗口构建 OK（顶层窗口 {len(toplevels)} 个）")
    assert toplevels, "设置窗口未构建"
    for w in toplevels:
        w.destroy()

    app.alerts.close_all()
    storage.delete_task(tid)
    print("[8] 清理完成，冒烟测试通过")
    app.quit_app()
    import os
    os._exit(0)                     # 直接结束，避免残留的托盘线程阻塞退出
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
