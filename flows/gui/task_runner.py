"""在后台线程中运行 CLI 工作流，并通过队列向 GUI 传递事件。"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from typing import Literal, Sequence


EventKind = Literal["started", "output", "finished", "error", "cancelling"]


@dataclass(frozen=True)
class TaskEvent:
    kind: EventKind
    message: str = ""
    returncode: int | None = None
    elapsed_seconds: float = 0.0


class TaskRunner:
    """保证同一时间只运行一个子进程工作流。"""

    def __init__(self) -> None:
        self.events: Queue[TaskEvent] = Queue()
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None
        self._thread: threading.Thread | None = None
        self._cancel_requested = False

    @property
    def running(self) -> bool:
        with self._lock:
            return self._process is not None or (self._thread is not None and self._thread.is_alive())

    def start(self, command: Sequence[str], cwd: Path) -> None:
        with self._lock:
            if self._process is not None or (self._thread is not None and self._thread.is_alive()):
                raise RuntimeError("已有工作流正在运行")
            self._cancel_requested = False
            self._thread = threading.Thread(
                target=self._run,
                args=(list(command), cwd),
                daemon=True,
                name="financial-track-workflow",
            )
            self._thread.start()

    def request_cancel(self) -> bool:
        """请求子进程在安全边界退出，不强制终止或删除输出。"""
        with self._lock:
            process = self._process
            thread_running = self._thread is not None and self._thread.is_alive()
            if not thread_running or (process is not None and process.poll() is not None):
                return False
            self._cancel_requested = True
        self.events.put(TaskEvent("cancelling", "正在请求任务安全取消……"))
        if process is None:
            return True
        return self._send_cancel_signal(process)

    def _send_cancel_signal(self, process: subprocess.Popen[str]) -> bool:
        try:
            if os.name == "nt":
                process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                process.send_signal(signal.SIGINT)
        except (OSError, ValueError) as exc:
            self.events.put(TaskEvent("error", f"无法发送取消信号：{exc}"))
            return False
        return True

    def _run(self, command: list[str], cwd: Path) -> None:
        started_at = time.monotonic()
        self.events.put(TaskEvent("started", "工作流已启动"))
        env = os.environ.copy()
        root_path = str(cwd)
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = root_path + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        kwargs: dict[str, object] = {}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            kwargs["start_new_session"] = True

        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                **kwargs,
            )
            with self._lock:
                self._process = process
                cancel_immediately = self._cancel_requested
            if cancel_immediately:
                self._send_cancel_signal(process)
            if process.stdout is not None:
                with process.stdout:
                    for line in process.stdout:
                        self.events.put(TaskEvent("output", line.rstrip("\r\n")))
            returncode = process.wait()
            elapsed = time.monotonic() - started_at
            with self._lock:
                cancelled = self._cancel_requested
            if cancelled:
                message = "任务已取消"
            elif returncode == 0:
                message = "任务完成"
            else:
                message = f"任务失败，退出码 {returncode}"
            self.events.put(TaskEvent("finished", message, returncode, elapsed))
        except Exception as exc:
            elapsed = time.monotonic() - started_at
            self.events.put(TaskEvent("error", f"任务启动或读取失败：{exc}", elapsed_seconds=elapsed))
            self.events.put(TaskEvent("finished", "任务失败", -1, elapsed))
        finally:
            with self._lock:
                self._process = None
                self._thread = None
