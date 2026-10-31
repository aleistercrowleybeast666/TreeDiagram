"""Export from a completed run's immutable input, never current editor values."""
from __future__ import annotations

from pathlib import Path

from .design import Design_Decode
from .physics import Plant
from .results import Run_Validate


def Parameters_ExportRun(run: dict, path: Path) -> None:
    Run_Validate(run)
    from .algorithms import Navigation, PidController, LqrController
    from .algorithms.bundle import TuningBundle_Build, TuningBundle_Write
    design = Design_Decode(run["design"])
    control = design.control
    if control.estimator == "none":
        raise ValueError("此运行没有可导出的估计器；请选择真实 C 算法并重新运行。")
    plant = Plant(design)
    navigation = Navigation(control.estimator, initial_q_nb=tuple(plant.initial_q),
                            gravity_mps2=design.scenario.gravity_mps2)
    if navigation.implementation_identity != run["algorithm_identity"].get("source"):
        raise ValueError("算法源码/编译身份已变化；先重新运行再导出，不能给旧结果套用新实现。")
    controller = None
    if control.controller == "pid":
        controller = PidController(kp=control.kp, ki=control.ki, kd=control.kd,
            output_limit=control.torque_limit_nm, sample_period_s=control.period_us/1e6)
    elif control.controller == "lqr":
        controller = LqrController(inertia_kg_m2=plant.Mass_Evaluate(0.)[2][1,1],
            dt_s=control.period_us/1e6, q_angle=control.lqr_q_angle, q_rate=control.lqr_q_rate,
            r=control.lqr_r, output_limit=control.torque_limit_nm)
    # Content hash, not a display name, binds the complete model/conditions.
    bundle = TuningBundle_Build(navigation, controller, model_id=run["input_digest"], run_id=run["run_id"])
    TuningBundle_Write(path, bundle)
