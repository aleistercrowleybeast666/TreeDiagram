"""严格版本校验与同目录原子保存；不自动迁移或执行项目内容。"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path

from .model import Curve, Dataset, JobState, Project, RunConfig, RunRecord
from ..io import Json_Decode, MAX_BYTES
from ..design import Design_Decode


class ProjectIoResult(str, Enum):
    Success = "success"
    Invalid = "invalid"
    UnsupportedVersion = "unsupported_version"
    Conflict = "conflict"
    IoError = "io_error"


@dataclass(frozen=True)
class ProjectIoOutcome:
    result: ProjectIoResult
    message: str = ""
    project: Project | None = None
    digest: str | None = None


class _Invalid(ValueError):
    pass


class _Version(_Invalid):
    pass


def _Object_Check(value, keys: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise _Invalid("文件字段缺失或包含当前版本不支持的字段。")
    return value


def _Text_Check(value, limit: int = 500, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > limit or (not allow_empty and not value.strip()):
        raise _Invalid("文本字段为空、类型错误或过长。")
    return value


def _Numbers_Check(value, minimum: int = 2) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)) or not minimum <= len(value) <= 4096:
        raise _Invalid("数据长度不合法（最多 4096 点）。")
    if any(type(x) not in (int, float) or not math.isfinite(x) or abs(x) > 1e12 for x in value):
        raise _Invalid("数据必须是绝对值不超过 1e12 的有限数值。")
    return tuple(float(x) for x in value)


def _Parameters_Check(value) -> dict[str, float | bool]:
    if not isinstance(value, dict) or len(value) > 32:
        raise _Invalid("参数必须是最多 32 项的对象。")
    for key, item in value.items():
        _Text_Check(key, 80)
        if type(item) not in (int, float, bool) or not math.isfinite(item) or abs(item) > 1e12:
            raise _Invalid("当前参数接口只支持有限数值或布尔值。")
    return dict(value)


def _Json_ReadPairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _Invalid("JSON 存在重复字段。")
        result[key] = value
    return result


def _Project_Decode(raw: bytes) -> Project:
    if len(raw) > MAX_BYTES:
        raise _Invalid("项目超过 32 MiB 上限；请导出结果并拆分项目。")
    document = Json_Decode(raw)
    if not isinstance(document, dict) or document.get("format") != "TreeDiagramProject":
        raise _Invalid("不是 TreeDiagram 项目。")
    if type(document.get("schema_version")) is not int or document["schema_version"] not in (1, 2):
        raise _Version("不支持此 schema 版本；文件未修改，请使用兼容版本打开。")
    _Object_Check(document, {"format", "schema_version", "project"})
    keys = {"project_id", "name", "description", "dataset", "config", "runs"}
    if document["schema_version"] == 2:
        keys |= {"design", "flight_runs"}
    data = _Object_Check(document["project"], keys)
    design = data.get("design")
    if design is not None:
        Design_Decode(design)
    flight_runs = data.get("flight_runs", [])
    if not isinstance(flight_runs, list) or len(flight_runs) > 10:
        raise _Invalid("最多保留10次六自由度运行；可先导出旧结果。")
    from ..results import Run_Validate
    for flight_run in flight_runs:
        Run_Validate(flight_run)
    dataset = _Object_Check(data["dataset"], {"name", "values"})
    config = _Object_Check(data["config"], {"plugin_id", "parameters"})
    if not isinstance(data["runs"], list) or len(data["runs"]) > 100:
        raise _Invalid("运行历史最多 100 条。")
    records = []
    for item in data["runs"]:
        record = _Object_Check(item, {
            "run_id", "plugin_id", "plugin_version", "started_at", "finished_at", "state",
            "input_digest", "parameters", "logs", "curve", "error",
        })
        state = JobState(record["state"])
        if state not in (JobState.Succeeded, JobState.Cancelled, JobState.Failed):
            raise _Invalid("项目只能保存已结束的运行记录。")
        if not isinstance(record["logs"], list) or len(record["logs"]) > 200:
            raise _Invalid("单次运行日志最多 200 条。")
        curve = None
        if record["curve"] is not None:
            value = _Object_Check(record["curve"], {"title", "x_label", "y_label", "x", "y"})
            curve = Curve(
                _Text_Check(value["title"]), _Text_Check(value["x_label"]), _Text_Check(value["y_label"]),
                _Numbers_Check(value["x"]), _Numbers_Check(value["y"]),
            )
            if len(curve.x) != len(curve.y):
                raise _Invalid("结果的 x/y 长度不一致。")
        if (state == JobState.Succeeded) != (curve is not None):
            raise _Invalid("运行状态与结果数据不一致。")
        digest = _Text_Check(record["input_digest"], 64)
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise _Invalid("输入指纹不合法。")
        records.append(RunRecord(
            _Text_Check(record["run_id"], 80), _Text_Check(record["plugin_id"], 80),
            _Text_Check(record["plugin_version"], 80), _Text_Check(record["started_at"], 80),
            _Text_Check(record["finished_at"], 80), state, digest,
            _Parameters_Check(record["parameters"]),
            tuple(_Text_Check(log, 1000, True) for log in record["logs"]), curve,
            _Text_Check(record["error"], 2000, True),
        ))
    if len({record.run_id for record in records}) != len(records):
        raise _Invalid("运行记录 ID 重复。")
    return Project(
        _Text_Check(data["project_id"], 80), _Text_Check(data["name"], 120),
        _Text_Check(data["description"], 5000, True),
        Dataset(_Text_Check(dataset["name"]), _Numbers_Check(dataset["values"], minimum=0)),
        RunConfig(_Text_Check(config["plugin_id"], 80, True), _Parameters_Check(config["parameters"])),
        tuple(records), design, tuple(flight_runs),
    )


def _File_Read(path: Path) -> bytes:
    with path.open("rb") as stream:
        return stream.read(MAX_BYTES + 1)


def Project_Load(path: Path) -> ProjectIoOutcome:
    try:
        raw = _File_Read(path)
        project = _Project_Decode(raw)
        return ProjectIoOutcome(ProjectIoResult.Success, project=project, digest=hashlib.sha256(raw).hexdigest())
    except _Version as exc:
        return ProjectIoOutcome(ProjectIoResult.UnsupportedVersion, str(exc))
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError) as exc:
        return ProjectIoOutcome(ProjectIoResult.Invalid, f"项目无效：{exc}")
    except OSError as exc:
        return ProjectIoOutcome(ProjectIoResult.IoError, f"读取失败：{exc}")


def _File_Replace(path: Path, raw: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def Project_Save(project: Project, path: Path, expected_digest: str | None = None) -> ProjectIoOutcome:
    """expected_digest=None 仅允许新文件；覆盖须提供最近读取的摘要。"""
    lock_path = path.with_name(path.name + ".lock")
    locked = False
    try:
        raw = (json.dumps(
            {"format": "TreeDiagramProject", "schema_version": 2, "project": asdict(project)},
            ensure_ascii=False, allow_nan=False, indent=2,
        ) + "\n").encode("utf-8")
        _Project_Decode(raw)
        with lock_path.open("x", encoding="utf-8") as lock:
            locked = True
            lock.write(f"TreeDiagram saving; pid={os.getpid()}\n")
        if path.is_symlink():
            return ProjectIoOutcome(ProjectIoResult.Conflict, "不覆盖符号链接，请选择普通文件。")
        if path.exists():
            existing = _File_Read(path)
            if expected_digest is None or hashlib.sha256(existing).hexdigest() != expected_digest:
                return ProjectIoOutcome(ProjectIoResult.Conflict, "文件已存在或被外部修改；请重新打开或另存为新文件。")
            _Project_Decode(existing)
            _File_Replace(path.with_name(path.name + ".bak"), existing)
        elif expected_digest is not None:
            return ProjectIoOutcome(ProjectIoResult.Conflict, "原文件已被移动或删除；请另存为新文件。")
        _File_Replace(path, raw)
        return ProjectIoOutcome(ProjectIoResult.Success, project=project, digest=hashlib.sha256(raw).hexdigest())
    except FileExistsError:
        return ProjectIoOutcome(ProjectIoResult.Conflict, "项目正在保存或存在遗留 .lock 文件；请检查后重试。")
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError) as exc:
        return ProjectIoOutcome(ProjectIoResult.Invalid, f"保存前校验失败：{exc}")
    except OSError as exc:
        return ProjectIoOutcome(ProjectIoResult.IoError, f"保存失败，原项目未被替换：{exc}")
    finally:
        if locked:
            try:
                lock_path.unlink()
            except OSError:
                pass

