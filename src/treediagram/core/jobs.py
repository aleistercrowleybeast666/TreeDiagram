from __future__ import annotations

import copy
import math
import threading
from collections import deque
from dataclasses import dataclass
from enum import Enum
from uuid import uuid4

from .model import Curve, Dataset, Input_GetDigest, JobState, RunConfig, RunRecord, Time_GetUtc
from .plugins import PluginCheckResult, SimulationPlugin


class JobStartResult(str, Enum):
    Started = "started"
    AlreadyStarted = "already_started"


class JobCancelResult(str, Enum):
    Requested = "requested"
    NotRunning = "not_running"


class _Cancelled(Exception):
    pass


@dataclass(frozen=True)
class JobSnapshot:
    state: JobState
    progress: int
    logs: tuple[str, ...]
    record: RunRecord | None
    alive: bool


class BackgroundJob:
    """单个协作式后台线程。工作线程只写自身状态；GUI 通过快照轮询。"""
    def __init__(self, plugin: SimulationPlugin, dataset: Dataset, config: RunConfig):
        self._plugin = plugin
        self._dataset = copy.deepcopy(dataset)
        self._config = copy.deepcopy(config)
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._state = JobState.Queued
        self._progress = 0
        self._logs: deque[str] = deque(maxlen=200)
        self._record: RunRecord | None = None
        self._started_at = ""

    def Job_Start(self) -> JobStartResult:
        with self._lock:
            if self._state != JobState.Queued:
                return JobStartResult.AlreadyStarted
            self._started_at = Time_GetUtc()
            self._state = JobState.Running
            self._thread = threading.Thread(target=self._Job_Run, name="TreeDiagram-job", daemon=False)
            self._thread.start()
            return JobStartResult.Started

    def Job_Cancel(self) -> JobCancelResult:
        with self._lock:
            if self._state not in (JobState.Running, JobState.Cancelling):
                return JobCancelResult.NotRunning
            if not self._cancel.is_set():
                self.Job_Log("已请求取消，等待插件安全退出。")
            self._cancel.set()
            self._state = JobState.Cancelling
            return JobCancelResult.Requested

    def Job_GetSnapshot(self) -> JobSnapshot:
        with self._lock:
            return JobSnapshot(
                self._state, self._progress, tuple(self._logs), self._record,
                self._thread is not None and self._thread.is_alive(),
            )

    def Job_Join(self, timeout: float = 5.0) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def Job_CheckCancellation(self) -> None:
        if self._cancel.is_set():
            raise _Cancelled()

    def Job_Wait(self, seconds: float) -> None:
        if self._cancel.wait(seconds):
            raise _Cancelled()

    def Job_ReportProgress(self, percent: int) -> None:
        with self._lock:
            self._progress = max(self._progress, min(99, max(0, int(percent))))

    def Job_Log(self, message: str) -> None:
        with self._lock:
            self._logs.append(f"{Time_GetUtc()[11:19]}  {str(message)[:950]}")

    def _Curve_Check(self, curve: Curve) -> None:
        if not isinstance(curve, Curve) or not 2 <= len(curve.x) <= 4096 or len(curve.x) != len(curve.y):
            raise ValueError("插件返回了无效曲线。")
        if any(type(x) not in (int, float) or not math.isfinite(x) or abs(x) > 1e12 for x in (*curve.x, *curve.y)):
            raise ValueError("插件结果包含无效数值。")
        if any(not isinstance(s, str) or not s.strip() or len(s) > 500 for s in (curve.title, curve.x_label, curve.y_label)):
            raise ValueError("插件结果标签无效。")

    def _Job_Run(self) -> None:
        curve, error = None, ""
        state = JobState.Failed
        digest = "0" * 64
        try:
            digest = Input_GetDigest(self._dataset, self._config)
            if self._config.plugin_id != self._plugin.plugin_id:
                raise ValueError("运行配置与插件 ID 不一致。")
            check = self._plugin.Plugin_Validate(self._dataset, self._config.parameters)
            if check.result != PluginCheckResult.Valid:
                raise ValueError(check.message)
            self.Job_CheckCancellation()
            curve = self._plugin.Plugin_Run(self._dataset, self._config.parameters, self)
            self._Curve_Check(curve)
            self.Job_CheckCancellation()
            state = JobState.Succeeded
        except _Cancelled:
            state, curve = JobState.Cancelled, None
        except Exception as exc:
            state, curve, error = JobState.Failed, None, f"{type(exc).__name__}: {exc}"[:2000]
        finally:
            with self._lock:
                if self._cancel.is_set():
                    state, curve, error = JobState.Cancelled, None, ""
                self._state = state
                if state == JobState.Succeeded:
                    self._progress = 100
                self.Job_Log({
                    JobState.Succeeded: "任务成功。", JobState.Cancelled: "任务已取消，未生成结果。",
                    JobState.Failed: f"任务失败：{error}",
                }[state])
                self._record = RunRecord(
                    str(uuid4()), self._plugin.plugin_id, self._plugin.version, self._started_at,
                    Time_GetUtc(), state, digest, dict(self._config.parameters), tuple(self._logs), curve, error,
                )

