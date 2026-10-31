from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from .model import Curve, Dataset


class PluginCheckResult(str, Enum):
    Valid = "valid"
    Invalid = "invalid"
    Duplicate = "duplicate"


@dataclass(frozen=True)
class PluginCheckOutcome:
    result: PluginCheckResult
    message: str = ""


@dataclass(frozen=True)
class ParameterSpec:
    key: str
    label: str
    default: float | bool
    minimum: float = 0.0
    maximum: float = 1.0


class JobContext(Protocol):
    def Job_CheckCancellation(self) -> None: ...
    def Job_Wait(self, seconds: float) -> None: ...
    def Job_ReportProgress(self, percent: int) -> None: ...
    def Job_Log(self, message: str) -> None: ...


class SimulationPlugin(Protocol):
    plugin_id: str
    title: str
    version: str
    description: str
    parameters: tuple[ParameterSpec, ...]

    def Plugin_Validate(self, dataset: Dataset, parameters: dict) -> PluginCheckOutcome: ...
    def Plugin_Run(self, dataset: Dataset, parameters: dict, context: JobContext) -> Curve: ...


class PluginRegistry:
    """显式注册可信 Python 对象；项目文件不能导入代码或指定模块路径。"""
    def __init__(self):
        self._plugins: dict[str, SimulationPlugin] = {}

    def Plugin_Register(self, plugin: SimulationPlugin) -> PluginCheckOutcome:
        if plugin.plugin_id in self._plugins:
            return PluginCheckOutcome(PluginCheckResult.Duplicate, "插件 ID 已注册。")
        if not plugin.plugin_id or not plugin.version or not callable(plugin.Plugin_Run):
            return PluginCheckOutcome(PluginCheckResult.Invalid, "插件接口不完整。")
        self._plugins[plugin.plugin_id] = plugin
        return PluginCheckOutcome(PluginCheckResult.Valid)

    def Plugin_Get(self, plugin_id: str) -> SimulationPlugin | None:
        return self._plugins.get(plugin_id)

    def Plugin_List(self) -> tuple[SimulationPlugin, ...]:
        return tuple(self._plugins.values())


class SineDemoPlugin:
    plugin_id = "demo.sine"
    title = "正弦曲线 · 纯数学示例"
    version = "1.0.0"
    description = "y = A × sin(f × x)。仅用于测试数据、任务与曲线接口，不代表任何物理仿真。"
    parameters = (
        ParameterSpec("amplitude", "幅值 A（无量纲）", 1.0, -1000.0, 1000.0),
        ParameterSpec("frequency", "系数 f（无量纲）", 1.0, 0.01, 100.0),
        ParameterSpec("fail_demo", "注入示例故障（测试失败流程）", False),
    )

    def Plugin_Validate(self, dataset: Dataset, parameters: dict) -> PluginCheckOutcome:
        if set(parameters) != {spec.key for spec in self.parameters}:
            return PluginCheckOutcome(PluginCheckResult.Invalid, "示例参数字段不完整或存在未知字段。")
        for spec in self.parameters:
            value = parameters[spec.key]
            if type(spec.default) is bool:
                valid = type(value) is bool
            else:
                valid = type(value) in (int, float) and math.isfinite(value) and spec.minimum <= value <= spec.maximum
            if not valid:
                return PluginCheckOutcome(PluginCheckResult.Invalid, f"参数不合法：{spec.label}")
        if not 2 <= len(dataset.values) <= 4096 or any(
            type(x) not in (int, float) or not math.isfinite(x) or abs(x) > 1e12 for x in dataset.values
        ):
            return PluginCheckOutcome(PluginCheckResult.Invalid, "输入必须为 2～4096 个有限数值。")
        return PluginCheckOutcome(PluginCheckResult.Valid)

    def Plugin_Run(self, dataset: Dataset, parameters: dict, context: JobContext) -> Curve:
        context.Job_Log("纯数学示例开始；延时仅用于展示后台任务生命周期。")
        output = []
        for index, value in enumerate(dataset.values):
            context.Job_CheckCancellation()
            if parameters["fail_demo"] and index >= len(dataset.values) // 2:
                raise RuntimeError("已注入示例故障，用于验证失败处理。")
            output.append(parameters["amplitude"] * math.sin(parameters["frequency"] * value))
            context.Job_ReportProgress(int(100 * (index + 1) / len(dataset.values)))
            context.Job_Wait(min(0.025, 2.0 / len(dataset.values)))
        context.Job_Log(f"计算完成：{len(output)} 个数据点。")
        return Curve("正弦曲线（纯数学示例）", "x（无量纲）", "y（无量纲）", dataset.values, tuple(output))


def Registry_CreateDefault() -> PluginRegistry:
    registry = PluginRegistry()
    registry.Plugin_Register(SineDemoPlugin())
    return registry

