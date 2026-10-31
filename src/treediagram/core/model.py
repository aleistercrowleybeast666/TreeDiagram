from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4


class JobState(str, Enum):
    Queued = "queued"
    Running = "running"
    Cancelling = "cancelling"
    Succeeded = "succeeded"
    Cancelled = "cancelled"
    Failed = "failed"


def Time_GetUtc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Dataset:
    name: str
    values: tuple[float, ...]


@dataclass(frozen=True)
class RunConfig:
    plugin_id: str = "demo.sine"
    parameters: dict[str, float | bool] = field(
        default_factory=lambda: {"amplitude": 1.0, "frequency": 1.0, "fail_demo": False}
    )


@dataclass(frozen=True)
class Curve:
    title: str
    x_label: str
    y_label: str
    x: tuple[float, ...]
    y: tuple[float, ...]


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    plugin_id: str
    plugin_version: str
    started_at: str
    finished_at: str
    state: JobState
    input_digest: str
    parameters: dict[str, float | bool]
    logs: tuple[str, ...]
    curve: Curve | None = None
    error: str = ""


@dataclass(frozen=True)
class Project:
    project_id: str
    name: str
    description: str
    dataset: Dataset
    config: RunConfig
    runs: tuple[RunRecord, ...] = ()
    design: dict | None = None
    flight_runs: tuple[dict, ...] = ()


def Dataset_CreateUniform(count: int = 97, start: float = 0.0, end: float = math.tau) -> Dataset:
    if type(count) is not int or not 2 <= count <= 4096:
        raise ValueError("样本数必须在 2 到 4096 之间。")
    if not math.isfinite(start) or not math.isfinite(end) or start >= end:
        raise ValueError("区间必须有限，且起点小于终点。")
    return Dataset("均匀数学样本", tuple(start + (end - start) * i / (count - 1) for i in range(count)))


def Project_Create() -> Project:
    return Project(str(uuid4()), "未命名工程", "", Dataset("未定义", ()), RunConfig("", {}))


def Input_GetDigest(dataset: Dataset, config: RunConfig) -> str:
    encoded = json.dumps(
        {"dataset": asdict(dataset), "config": asdict(config)},
        sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

