"""Versioned assembly and scenario. Body +Z points toward the nose; ENU world."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, fields
from typing import Any
from uuid import uuid4

import numpy as np

from .geometry import Inertia_Check, Inertia_Shift, Quaternion_Matrix, Vector_Check
from .io import Json_Digest

PART_KINDS = ("nose", "tube", "transition", "fins", "mass", "motor", "sensor", "actuator")
ACTUATORS = ("gimbal", "fin", "wheel", "rcs")


def Number_Check(value, path: str, minimum: float, maximum: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{path}: expected finite number in [{minimum}, {maximum}]")
    return float(value)


@dataclass(frozen=True)
class Part:
    id: str
    name: str
    kind: str
    parent_id: str | None = None
    position_m: tuple = (0., 0., 0.)
    rotation_wxyz: tuple = (1., 0., 0., 0.)
    mass_kg: float | None = None
    length_m: float = 0.1
    radius_m: float = 0.02
    inner_radius_m: float = 0.
    inertia_kg_m2: tuple | None = None
    # Each part mass is its own contribution, never a total including children.
    mass_basis: str = "own_part"
    provenance: str = "user input"


@dataclass(frozen=True)
class Motor:
    time_s: tuple
    thrust_n: tuple
    propellant_mass_kg: float | None
    dry_mass_kg: float | None
    position_m: tuple = (0., 0., -0.45)
    length_m: float = 0.2
    radius_m: float = 0.025
    ignition_s: float = 0.
    mass_model: str = "impulse_fraction_uniform_cylinder"
    gimbal_capable: bool = False
    source: dict = field(default_factory=dict)
    rotation_bm_wxyz: tuple = (1., 0., 0., 0.)


@dataclass(frozen=True)
class Scenario:
    duration_s: float = 18.
    step_us: int = 5000
    output_us: int = 20000
    seed: int = 42
    rail_length_m: float = 1.
    launch_tilt_deg: float = 3.
    wind_enu_mps: tuple = (2., 0., 0.)
    wind_shear_per_s: tuple = (0., 0., 0.)
    wind_gust_mps: float = 0.
    gravity_mps2: float = 9.80665
    reference_area_m2: float = 0.005027
    reference_length_m: float = 1.2
    drag_coefficient: float = 0.45
    normal_slope_per_rad: float = 2.0
    damping_coefficient: float = 0.1
    cp_body_m: tuple = (0., 0., -0.25)
    aero_max_angle_deg: float = 20.
    aero_max_mach: float = 0.7
    # No implicit aerodynamics inferred from an imported mesh/ORK.
    aero_provenance: str = "explicit user engineering coefficient approximation"


@dataclass(frozen=True)
class SensorConfig:
    imu_us: int = 10000
    imu_delay_us: int = 0
    gnss_us: int = 200000
    gnss_delay_us: int = 100000
    auxiliary_us: int = 100000
    auxiliary_delay_us: int = 10000
    pressure_std_pa: float = 1.
    magnetic_std_t: float = 0.00000005
    accel_noise_std_mps2: float = 0.03
    gyro_noise_std_radps: float = 0.0005
    accel_bias_mps2: tuple = (0., 0., 0.)
    gyro_bias_radps: tuple = (0., 0., 0.)
    position_std_m: float = 0.4
    velocity_std_mps: float = 0.08
    accel_limit_mps2: float = 156.9064
    gyro_limit_radps: float = 10.
    quantization_mps2: float = 0.0001
    rotation_bs_wxyz: tuple = (1., 0., 0., 0.)
    outage_start_s: float = 5.
    outage_end_s: float = 7.


@dataclass(frozen=True)
class ControlConfig:
    estimator: str = "none"
    controller: str = "none"
    actuator: str = "gimbal"
    period_us: int = 20000
    start_phase: str = "powered"
    end_phase: str = "coast"
    kp: float = 1.5
    ki: float = 0.15
    kd: float = 0.35
    torque_limit_nm: float = 0.4
    angle_limit_rad: float = 0.12
    rate_limit_radps: float = 2.
    response_s: float = 0.03
    wheel_inertia_kg_m2: float = 0.0002
    wheel_speed_limit_radps: float = 500.
    rcs_force_n: float = 1.
    rcs_propellant_kg: float = 0.015
    rcs_isp_s: float = 50.
    minimum_pulse_s: float = 0.04
    lqr_q_angle: float = 5.
    lqr_q_rate: float = 1.
    lqr_r: float = 1.
    actuator_position_m: tuple = (0., 0., -0.45)
    fin_area_m2: float = 0.003
    fin_slope_per_rad: float = 2.


@dataclass(frozen=True)
class Design:
    id: str
    name: str
    parts: tuple[Part, ...]
    motor: Motor | None
    scenario: Scenario = field(default_factory=Scenario)
    sensors: SensorConfig = field(default_factory=SensorConfig)
    control: ControlConfig = field(default_factory=ControlConfig)
    assumptions: tuple[str, ...] = ()
    import_issues: tuple[str, ...] = ()
    schema: str = "treediagram.design/1"


def _Decode(cls, value):
    if not isinstance(value, dict) or set(value) - {f.name for f in fields(cls)}:
        raise ValueError(f"{cls.__name__}: unknown fields or wrong object type")
    try:
        return cls(**value)
    except TypeError as exc:
        raise ValueError(f"{cls.__name__}: missing or invalid fields") from exc


def Design_Decode(value: dict) -> Design:
    if not isinstance(value, dict) or value.get("schema") != "treediagram.design/1":
        raise ValueError("unsupported design schema")
    data = dict(value)
    if not isinstance(data.get("parts"), (list, tuple)) or len(data["parts"]) > 256:
        raise ValueError("parts: maximum 256")
    data["parts"] = tuple(_Decode(Part, p) for p in data["parts"])
    data["motor"] = _Decode(Motor, data["motor"]) if data.get("motor") is not None else None
    for key, cls in (("scenario", Scenario), ("sensors", SensorConfig), ("control", ControlConfig)):
        data[key] = _Decode(cls, data.get(key, {}))
    design = _Decode(Design, data)
    Design_Validate(design, runnable=False)
    return design


def Design_Digest(design: Design) -> str:
    return Json_Digest(asdict(design))


def Design_Validate(design: Design, runnable: bool = True) -> tuple[str, ...]:
    """Reject malformed content, return explicit physical readiness deficiencies."""
    for name in ("assumptions","import_issues"):
        values=getattr(design,name)
        if not isinstance(values,(tuple,list)) or len(values)>4096 or any(not isinstance(v,str) or len(v)>4096 for v in values):
            raise ValueError(name+": bounded text array required")
    issues = list(design.import_issues)
    if design.schema != "treediagram.design/1" or not isinstance(design.name, str) or not design.name.strip():
        raise ValueError("design name/schema invalid")
    if not design.parts or len(design.parts) > 256:
        raise ValueError("parts: expected 1..256 objects")
    if not isinstance(design.id,str) or not design.id or len(design.id)>128:
        raise ValueError("design.id: bounded stable ID required")
    if any(not isinstance(p.id,str) or not p.id or len(p.id)>128 or not isinstance(p.name,str)
           or (p.parent_id is not None and not isinstance(p.parent_id,str)) for p in design.parts):
        raise ValueError("parts: invalid ID/name/parent")
    ids = {p.id for p in design.parts}
    if len(ids) != len(design.parts) or any(not isinstance(i, str) or not i for i in ids):
        raise ValueError("parts: duplicate or empty stable ID")
    parents = {p.id: p.parent_id for p in design.parts}
    for p in design.parts:
        if p.kind not in PART_KINDS or p.mass_basis != "own_part":
            raise ValueError(f"{p.id}: unsupported kind or recursive mass override")
        Vector_Check(p.position_m, 3, p.id + ".position_m")
        q = Vector_Check(p.rotation_wxyz, 4, p.id + ".rotation")
        if abs(np.linalg.norm(q) - 1) > 1e-6:
            raise ValueError(f"{p.id}: assembly quaternion must be unit length")
        chain, parent = {p.id}, p.parent_id
        for _ in range(len(ids)):
            if parent is None:
                break
            if parent not in ids or parent in chain:
                raise ValueError(f"{p.id}: dangling parent or assembly cycle")
            chain.add(parent)
            parent = parents[parent]
        for key in ("length_m", "radius_m"):
            Number_Check(getattr(p, key), p.id + "." + key, 1e-6, 1000)
        Number_Check(p.inner_radius_m, p.id + ".inner_radius_m", 0, p.radius_m)
        if p.mass_kg is None:
            issues.append(f"{p.id}: 请补充零件自身质量 kg")
        else:
            Number_Check(p.mass_kg, p.id + ".mass_kg", 1e-9, 1e6)
        if p.inertia_kg_m2 is not None:
            Inertia_Check(p.inertia_kg_m2, p.id + ".inertia_kg_m2", allow_zero=True)
    if design.motor is None:
        issues.append("motor: 请导入推力曲线并补充质量模型")
    else:
        if any(p.kind == "motor" for p in design.parts):
            issues.append("motor: 主发动机干质量由推进模型计入；不能再用motor零件重复计质量")
        m = design.motor
        if not isinstance(m.source,dict):
            raise ValueError("motor.source: expected declarative object")
        if "package" in m.source:
            from .vendor_motor.contract import MotorPackage_Validate
            MotorPackage_Validate(m.source["package"])
        if not 2 <= len(m.time_s) <= 200000 or len(m.time_s) != len(m.thrust_n):
            raise ValueError("motor: invalid array lengths")
        t = Vector_Check(m.time_s, len(m.time_s), "motor.time_s")
        thrust = Vector_Check(m.thrust_n, len(m.thrust_n), "motor.thrust_n")
        if np.any(np.diff(t) <= 0):
            raise ValueError("motor.time_s: strictly increasing samples required")
        if t[0]<0 or t[-1]>600:
            issues.append("motor.time_s: 证据保留原时间；运行曲线需明确派生为点火相对0..600 s范围")
        if np.any(thrust < 0):
            issues.append("motor: 证据含负推力；需显式派生策略，不能直接运行")
        if np.trapezoid(thrust, t) <= 0:
            issues.append("motor: 总冲必须为正")
        for key in ("propellant_mass_kg", "dry_mass_kg"):
            if getattr(m, key) is None:
                issues.append(f"motor.{key}: 请补充已声明质量")
            else:
                Number_Check(getattr(m, key), "motor." + key, 1e-9, 1e6)
        if m.mass_model != "impulse_fraction_uniform_cylinder":
            raise ValueError("motor.mass_model: unsupported mass consumption law")
        Vector_Check(m.position_m, 3, "motor.position_m")
        rotation=Vector_Check(m.rotation_bm_wxyz,4,"motor.rotation_bm_wxyz")
        if abs(np.linalg.norm(rotation)-1)>1e-6:
            raise ValueError("motor.rotation_bm_wxyz: unit quaternion required")
        if type(m.gimbal_capable) is not bool:
            raise ValueError("motor.gimbal_capable: expected boolean")
        Number_Check(m.ignition_s, "motor.ignition_s", 0, 600)
        Number_Check(m.length_m, "motor.length_m", 1e-6, 1000)
        Number_Check(m.radius_m, "motor.radius_m", 1e-6, 1000)
    s, sensors, c = design.scenario, design.sensors, design.control
    if type(s.seed) is not int or not 0 <= s.seed < 2**32:
        raise ValueError("seed: expected uint32 integer")
    for value, path in ((s.step_us, "step_us"), (s.output_us, "output_us"),
                        (sensors.imu_us, "imu_us"), (sensors.gnss_us, "gnss_us"),
                        (sensors.auxiliary_us, "auxiliary_us"), (c.period_us, "period_us")):
        if type(value) is not int or not 1000 <= value <= 1000000:
            raise ValueError(f"{path}: integer microseconds in 1000..1000000 required")
    for name in ("imu_delay_us", "gnss_delay_us", "auxiliary_delay_us"):
        if type(getattr(sensors, name)) is not int or not 0 <= getattr(sensors, name) <= 2000000:
            raise ValueError(name + ": delay must be 0..2000000 integer us")
    Number_Check(s.duration_s, "duration_s", .01, 600)
    Number_Check(s.launch_tilt_deg,"launch_tilt_deg",-80.,80.)
    if sensors.outage_start_s<0 or sensors.outage_end_s<sensors.outage_start_s:
        raise ValueError("sensors: invalid outage interval")
    if s.duration_s * 1e6 / min(s.step_us, sensors.imu_us) > 600000:
        raise ValueError("scenario: maximum 600000 integration/sample boundaries")
    sample_budget=sum(math.ceil(s.duration_s*1e6/period)+1 for period in
                      (sensors.imu_us,sensors.gnss_us,sensors.auxiliary_us,sensors.auxiliary_us))
    if sample_budget>100000 or math.ceil(s.duration_s*1e6/s.output_us)+1>50000:
        raise ValueError("scenario: maximum 100000 sensor samples / 50000 output rows; shorten run or reduce sampling")
    for key in ("wind_enu_mps", "wind_shear_per_s", "cp_body_m"):
        Vector_Check(getattr(s, key), 3, key)
    for key in ("accel_bias_mps2", "gyro_bias_radps"):
        Vector_Check(getattr(sensors, key), 3, key)
    Quaternion_Matrix(sensors.rotation_bs_wxyz)
    if abs(np.linalg.norm(sensors.rotation_bs_wxyz)-1)>1e-6:
        raise ValueError("sensors.rotation_bs_wxyz: unit quaternion required")
    Vector_Check(c.actuator_position_m,3,"control.actuator_position_m")
    for obj in (s, sensors, c):
        for definition in fields(obj):
            value=getattr(obj,definition.name)
            if type(definition.default) in (int,float) and type(value) not in (int,float):
                raise ValueError(f"{definition.name}: boolean/text is not a physical number")
        for key, value in asdict(obj).items():
            if type(value) in (int, float):
                Number_Check(value, key, -1e6, 1e6)
    for key in ("reference_area_m2", "reference_length_m", "aero_max_angle_deg", "aero_max_mach"):
        Number_Check(getattr(s, key), key, 1e-8, 1000)
    for key in ("rail_length_m", "gravity_mps2", "drag_coefficient", "normal_slope_per_rad", "damping_coefficient"):
        Number_Check(getattr(s, key), key, 0, 1e4)
    for key in ("accel_noise_std_mps2", "gyro_noise_std_radps", "position_std_m", "velocity_std_mps", "quantization_mps2"):
        Number_Check(getattr(sensors, key), key, 0, 1e3)
    for key in ("accel_limit_mps2", "gyro_limit_radps"):
        Number_Check(getattr(sensors, key), key, 1e-6, 1e6)
    for key in ("position_std_m", "velocity_std_mps"):
        Number_Check(getattr(sensors,key),key,1e-6,1e3)
    Number_Check(sensors.pressure_std_pa,"pressure_std_pa",1e-6,1000.)
    Number_Check(sensors.magnetic_std_t,"magnetic_std_t",1e-12,1e-3)
    for key in ("torque_limit_nm", "angle_limit_rad", "rate_limit_radps", "response_s", "wheel_inertia_kg_m2", "wheel_speed_limit_radps", "rcs_force_n", "rcs_propellant_kg", "rcs_isp_s", "minimum_pulse_s", "lqr_r"):
        Number_Check(getattr(c, key), key, 1e-9, 1e6)
    for key in ("lqr_q_angle", "lqr_q_rate"):
        Number_Check(getattr(c, key), key, 0, 1e6)
    Number_Check(c.fin_area_m2,"fin_area_m2",1e-8,100.)
    Number_Check(c.fin_slope_per_rad,"fin_slope_per_rad",1e-8,100.)
    if c.controller not in ("none", "pid", "lqr") or c.actuator not in ACTUATORS:
        raise ValueError("control: unsupported controller/actuator")
    if c.estimator not in ("none", "ins", "sf6", "kf6", "eskf15", "eskf20", "inekf15", "inekf20"):
        raise ValueError("control.estimator: unsupported ID")
    phases = ("powered", "coast", "descent")
    if c.start_phase not in phases or c.end_phase not in phases or phases.index(c.start_phase) > phases.index(c.end_phase):
        raise ValueError("control: invalid inclusive phase range")
    if c.controller != "none" and c.estimator == "none":
        issues.append("control: 闭环控制需要真实估计输出")
    if c.estimator == "sf6" and sensors.imu_us > 10000:
        issues.append("sensors.imu_us: SF6宿主适配要求IMU间隔不超过10 ms")
    if c.controller != "none" and c.actuator == "gimbal" and design.motor and not design.motor.gimbal_capable:
        issues.append("motor: 未声明发动机具备推力偏转能力")
    if runnable and issues:
        raise ValueError("\n".join(issues))
    return tuple(issues)


def Part_Inertia(part: Part) -> np.ndarray:
    if part.inertia_kg_m2 is not None:
        return Inertia_Check(part.inertia_kg_m2, allow_zero=True)
    m, r, ri, length = part.mass_kg, part.radius_m, part.inner_radius_m, part.length_m
    # Uniform annular cylinder; cone/fin geometry can use explicit tensor overrides.
    axial = m * (r*r + ri*ri) / 2
    lateral = m * (3*(r*r+ri*ri)+length*length) / 12
    if part.kind == "nose":
        axial, lateral = .3*m*r*r, m*(3*r*r/20 + 3*length*length/80)
    return np.diag([lateral, lateral, axial])


def Assembly_Aggregate(parts: tuple[Part, ...]):
    """Local origin = own part CG; parent transforms resolve by stable IDs."""
    transformed: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for _ in range(len(parts)):
        for p in parts:
            if p.id in transformed or (p.parent_id is not None and p.parent_id not in transformed):
                continue
            rotation = Quaternion_Matrix(p.rotation_wxyz)
            position = np.array(p.position_m, dtype=float)
            if p.parent_id is not None:
                parent_position, parent_rotation = transformed[p.parent_id]
                position = parent_position + parent_rotation @ position
                rotation = parent_rotation @ rotation
            transformed[p.id] = position, rotation
    if len(transformed) != len(parts) or any(p.mass_kg is None for p in parts):
        raise ValueError("assembly has unresolved parents/masses")
    mass = sum(p.mass_kg for p in parts)
    cg = sum(p.mass_kg * transformed[p.id][0] for p in parts) / mass
    inertia = np.zeros((3, 3))
    for p in parts:
        position, rotation = transformed[p.id]
        inertia += rotation @ Part_Inertia(p) @ rotation.T + Inertia_Shift(p.mass_kg, position-cg)
    Inertia_Check(inertia)
    return float(mass), cg, inertia


def Design_CreateExample(controller="none", actuator="gimbal") -> Design:
    return Design(
        str(uuid4()), "离线单级探空箭 · 合成试车",
        (Part("body", "箭体", "tube", mass_kg=1.0, length_m=1., radius_m=.04, inner_radius_m=.037),
         Part("nose", "头锥", "nose", "body", (0., 0., .6), mass_kg=.15, length_m=.2, radius_m=.04),
         Part("fins", "尾翼组等效质量", "fins", "body", (0., 0., -.4), mass_kg=.1, length_m=.15, radius_m=.09),
         Part("avionics", "航电集中质量", "mass", "body", (0., 0., .15), mass_kg=.25)),
        Motor((0., .05, .25, 1., 1.8, 2.), (0., 50., 70., 65., 40., 0.), .3, .2,
              gimbal_capable=True, source={"origin": "synthetic", "calibration": "not applicable"}),
        control=ControlConfig(controller=controller, estimator="kf6" if controller != "none" else "none", actuator=actuator),
        assumptions=("示例装配与气动系数为软件参考；发动机证据与工程近似分别保留。", "推进剂按冲量比例消耗，均匀圆柱分布。",
                     "小攻角亚声速工程气动，超出适用域记录诊断。", "刚体、局部平地；无回收伞、级间分离和流体晃动。"))
