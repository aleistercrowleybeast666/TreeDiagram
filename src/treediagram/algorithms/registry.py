"""Installed software capabilities; design files cannot register executable code."""
from dataclasses import dataclass
import json

from .native import Sdk_Path
from .navigation import KINDS


@dataclass(frozen=True)
class AlgorithmDescriptor:
    key: str
    plugin_id: str
    version: str
    arithmetic: str
    outputs: tuple[str, ...]
    observations: tuple[str, ...]
    measurement_timing: str
    source: str
    lifecycle: tuple[str, ...] = ("Start", "Reset", "Stop")
    target_hardware_verified: bool = False


def AlgorithmRegistry_Get() -> tuple[AlgorithmDescriptor, ...]:
    root = Sdk_Path()
    result = []
    for key in KINDS:
        folder = "silverstar_algorithm_ins_coning2_sculling2" if key == "ins" else "silverstar_algorithm_estimator_" + key
        manifest = json.loads((root/folder/"plugin.json").read_text(encoding="utf-8"))
        observations = () if key == "ins" else ("gnss_position", "gnss_velocity")
        if key in ("kf6", "sf6", "eskf15"):
            observations += ("barometer_altitude",)
        if key in ("eskf20", "inekf20"):
            observations += ("magnetometer_sensor_field",)
        result.append(AlgorithmDescriptor(key,manifest["id"],manifest["version"],
            "float64 state/covariance; float32 quaternion bridge output" if key in ("eskf20","inekf15","inekf20") else "float32",
            ("position_enu_m","velocity_enu_mps","q_nb_from_ins" if key in ("sf6","kf6") else "q_nb"),
            observations,"current-state-on-arrival, actual age retained" if key in ("sf6","kf6") else "strict co-timed",
            "pinned SilverStar C mathematical core; sdk/manifest.json"))
    return tuple(result)
