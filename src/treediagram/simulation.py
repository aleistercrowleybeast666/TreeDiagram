"""Integer-microsecond causal schedule shared by desktop and command line."""
from __future__ import annotations

import heapq
import json
import math
from dataclasses import asdict
from uuid import uuid4

import numpy as np

from .design import Design, Design_Digest, Design_Validate
from .geometry import Quaternion_Matrix
from .physics import Plant


class SimulationCancelled(RuntimeError):
    pass


def Simulation_Run(design: Design, cancel=lambda: False, progress=lambda value: None) -> dict:
    Design_Validate(design)
    plant = Plant(design)
    state = plant.State_Create()
    scenario, sensors, control = design.scenario, design.sensors, design.control
    rng = np.random.default_rng(scenario.seed)
    nav, controller, estimate = None, None, None
    algorithm_identity = {"estimator": "none", "controller": "none"}
    if control.estimator != "none":
        from .algorithms import Navigation
        nav = Navigation(kind=control.estimator, initial_q_nb=tuple(plant.initial_q),
                         gravity_mps2=scenario.gravity_mps2,
                         magnetic_rotation_bs_wxyz=sensors.rotation_bs_wxyz,
                         magnetic_reference_n_uT=(20.,0.,-40.))
        algorithm_identity["estimator"] = control.estimator
        algorithm_identity["initialization"] = "configured launcher orientation, zero position/velocity; simulated source"
    if control.controller != "none":
        from .algorithms import PidController, LqrController
        if control.controller == "pid":
            controller = PidController(kp=control.kp, ki=control.ki, kd=control.kd,
                                       output_limit=control.torque_limit_nm, sample_period_s=control.period_us/1e6)
        else:
            inertia_y = plant.Mass_Evaluate(0.)[2][1, 1]
            controller = LqrController(inertia_kg_m2=inertia_y, dt_s=control.period_us/1e6,
                                       q_angle=control.lqr_q_angle, q_rate=control.lqr_q_rate,
                                       r=control.lqr_r, output_limit=control.torque_limit_nm)
        algorithm_identity["controller"] = control.controller
    now, end = 0, round(scenario.duration_s*1e6)
    next_imu = next_gnss = next_aux = next_control = next_output = 0
    ordinal, samples, arrivals, events, diagnostics = 0, [], [], [], []
    pending = []
    phase, apogee, airborne, finished = "powered", False, False, False
    request, gyro_latest = 0., np.zeros(3)
    rows = []
    phases = ("powered", "coast", "descent")
    rotation_bs = Quaternion_Matrix(sensors.rotation_bs_wxyz)
    motor_boundaries = sorted({round((design.motor.ignition_s+max(0., t))*1e6) for t in design.motor.time_s})
    diagnostics_seen = set()
    algorithm_counts = {}
    controller_stopped = False

    def diagnostic(message):
        if message not in diagnostics_seen:
            diagnostics_seen.add(message)
            diagnostics.append(message)

    def enqueue(kind, measurement_us, delay_us, values):
        nonlocal ordinal
        ordinal += 1
        sample = {"id": ordinal, "sensor": kind, "measurement_us": measurement_us,
                  "arrival_us": measurement_us+delay_us, "source": "simulated", **values}
        samples.append(sample)
        # Same-time arrivals: IMU establishes the state horizon before GNSS update.
        priority = {"imu": 0, "gnss": 1, "barometer": 2, "magnetometer": 3}[kind]
        heapq.heappush(pending, (sample["arrival_us"], priority, ordinal, sample))

    while now <= end:
        if cancel():
            raise SimulationCancelled("已取消；已有结果保留，本次未发布")
        time_s = now/1e6
        # 1 physical boundary already reached, 2 sample, 3 arrivals, 4 events,
        # 5 controller held values, 6 result sampling, then next physical interval.
        derivative = plant.Derivative(time_s, state)
        rotation = Quaternion_Matrix(state[6:10])
        if now == next_imu:
            specific_b = rotation.T @ (derivative[3:6]+np.array([0., 0., scenario.gravity_mps2]))
            accel_s = rotation_bs.T@specific_b + np.asarray(sensors.accel_bias_mps2)
            gyro_s = rotation_bs.T@state[10:13] + np.asarray(sensors.gyro_bias_radps)
            accel_s += rng.normal(0, sensors.accel_noise_std_mps2, 3)
            gyro_s += rng.normal(0, sensors.gyro_noise_std_radps, 3)
            saturated = bool(np.any(abs(accel_s) > sensors.accel_limit_mps2) or np.any(abs(gyro_s) > sensors.gyro_limit_radps))
            accel_s = np.clip(accel_s, -sensors.accel_limit_mps2, sensors.accel_limit_mps2)
            gyro_s = np.clip(gyro_s, -sensors.gyro_limit_radps, sensors.gyro_limit_radps)
            if sensors.quantization_mps2 > 0:
                accel_s = np.round(accel_s/sensors.quantization_mps2)*sensors.quantization_mps2
            enqueue("imu", now, sensors.imu_delay_us, {"specific_force_s_mps2": accel_s.tolist(),
                    "gyro_s_radps": gyro_s.tolist(), "valid": not saturated, "saturated": saturated})
            next_imu += sensors.imu_us
        if now == next_gnss:
            valid = not sensors.outage_start_s <= time_s < sensors.outage_end_s
            enqueue("gnss", now, sensors.gnss_delay_us, {
                "position_enu_m": (state[:3]+rng.normal(0, sensors.position_std_m, 3)).tolist(),
                "velocity_enu_mps": (state[3:6]+rng.normal(0, sensors.velocity_std_mps, 3)).tolist(), "valid": valid})
            next_gnss += sensors.gnss_us
        if now == next_aux:
            atmosphere = plant.Aero_Evaluate(time_s, state, plant.Mass_Evaluate(time_s, state[15])[1])[3]
            pressure=float(atmosphere.pressure_pa+rng.normal(0,sensors.pressure_std_pa))
            enqueue("barometer", now, sensors.auxiliary_delay_us, {"pressure_pa":pressure,"valid":pressure>0})
            field_n = np.array([20e-6, 0., -40e-6])
            enqueue("magnetometer", now, sensors.auxiliary_delay_us, {"field_s_t": (rotation_bs.T@rotation.T@field_n+rng.normal(0,sensors.magnetic_std_t,3)).tolist(), "valid": True})
            next_aux += sensors.auxiliary_us
        while pending and pending[0][0] <= now:
            _, _, _, sample = heapq.heappop(pending)
            arrivals.append({"sample_id": sample["id"], "consumed_us": now})
            if not sample["valid"]:
                diagnostic(sample["sensor"]+": invalid/saturated/outage measurement rejected")
                continue
            if sample["sensor"] == "imu":
                gyro_latest = rotation_bs @ np.array(sample["gyro_s_radps"])
                if nav is not None:
                    estimate = nav.Imu_Update(sample["measurement_us"],
                                               rotation_bs @ np.array(sample["specific_force_s_mps2"]), gyro_latest)
                    key="imu_"+estimate.result.name
                    algorithm_counts[key]=algorithm_counts.get(key,0)+1
                    if estimate.result.name not in ("Ok","Waiting"):
                        diagnostic("IMU estimator: "+estimate.result.name)
            elif sample["sensor"] == "gnss" and nav is not None:
                result = nav.Gnss_Update(sample["measurement_us"], now, sample["position_enu_m"],
                                         sample["velocity_enu_mps"], position_std_m=(sensors.position_std_m,)*3,
                                         velocity_std_mps=(sensors.velocity_std_mps,)*3)
                estimate = nav.Snapshot_Get()
                key="gnss_"+result.name
                algorithm_counts[key]=algorithm_counts.get(key,0)+1
                if hasattr(result, "name") and result.name != "Ok":
                    diagnostic("GNSS: " + result.name)
            elif sample["sensor"] in ("barometer","magnetometer") and nav is not None:
                if sample["sensor"]=="barometer":
                    # Invert the declared ISA pressure law, using measured pressure only.
                    pressure=sample["pressure_pa"]
                    exponent=1./5.2558797
                    altitude=288.15/.0065*(1.-(pressure/101325.)**exponent)
                    sigma=288.15/.0065*exponent/101325.*(pressure/101325.)**(exponent-1)*sensors.pressure_std_pa
                    result=nav.Barometer_Update(sample["measurement_us"],now,altitude,max(sigma,1e-6))
                else:
                    result=nav.Magnetic_Update(sample["measurement_us"],now,sample["field_s_t"],sensors.magnetic_std_t)
                estimate=nav.Snapshot_Get()
                key=sample["sensor"]+"_"+result.name
                algorithm_counts[key]=algorithm_counts.get(key,0)+1
                if result.name!="Ok":diagnostic(sample["sensor"]+": "+result.name)
        if phase == "powered" and time_s >= plant.burnout_s:
            phase = "coast"
            events.append({"event": "burnout", "time_s": plant.burnout_s, "phase": phase})
        if now == next_control:
            active = phases.index(control.start_phase) <= phases.index(phase) <= phases.index(control.end_phase)
            if controller is not None and phases.index(phase)>phases.index(control.end_phase) and not controller_stopped:
                controller.Stop()
                controller_stopped=True
            fresh = estimate is not None and 0 <= now-estimate.timestamp_us <= 2*sensors.imu_us
            if controller is not None and estimate is not None and estimate.valid and fresh and active and not plant.on_rail:
                estimated_axis = Quaternion_Matrix(estimate.q_nb)[:, 2]
                pitch = math.atan2(estimated_axis[0], estimated_axis[2])
                if control.controller == "pid":
                    request = float(controller.Step(0., pitch, control.period_us/1e6))
                else:
                    request = float(controller.Step([pitch, gyro_latest[1]]))
            else:
                request = 0.
            plant.Control_Set(request, time_s, enabled=controller is not None and estimate is not None and estimate.valid and fresh and active and not plant.on_rail)
            next_control += control.period_us
        if now == next_output or finished or now == end:
            mass, cg, inertia = plant.Mass_Evaluate(time_s, state[15])
            thrust, _ = plant.Motor_Evaluate(time_s)
            dynamic = plant.Aero_Evaluate(time_s, state, cg)[2]
            actual = plant.Actuator_Evaluate(time_s, state, thrust, dynamic, cg)[3]
            rows.append({"time_s": time_s, "position_enu_m": state[:3].tolist(),
                         "velocity_enu_mps": state[3:6].tolist(), "q_nb": state[6:10].tolist(),
                         "omega_b_radps": state[10:13].tolist(), "mass_kg": mass,
                         "cg_body_m": cg.tolist(), "inertia_kg_m2": inertia.tolist(),
                         "estimate_position_enu_m": list(estimate.position_enu_m) if estimate is not None and estimate.valid else None,
                         "estimate_velocity_enu_mps": list(estimate.velocity_enu_mps) if estimate is not None and estimate.valid else None,
                         "estimate_q_nb": list(estimate.q_nb) if estimate is not None and estimate.valid else None,
                         "control_request_nm": request, "actuator_actual_nm": actual,
                         "deflection_rad": float(state[13]), "wheel_momentum_nms": float(state[14]),
                         "rcs_used_kg": float(state[15]), "phase": phase})
            if now == next_output:
                next_output += scenario.output_us
        if finished or now == end:
            break
        candidates = [end, now+scenario.step_us, next_imu, next_gnss, next_aux, next_control, next_output]
        if pending:
            candidates.append(pending[0][0])
        candidates.extend(t for t in motor_boundaries if t > now)
        target = min(t for t in candidates if t > now)
        dt = (target-now)/1e6
        updated = plant.Step(time_s, state, dt)
        # Locate physical transitions inside the RK interval; remainder is recomputed
        # under the new mode. Integer scheduling never drifts with float addition.
        crossings = []
        if plant.on_rail and np.dot(updated[:3], plant.rail_axis) >= scenario.rail_length_m:
            crossings.append(("rail_exit", lambda x: np.dot(x[:3], plant.rail_axis)-scenario.rail_length_m))
        if airborne and not apogee and state[5] > 0 >= updated[5]:
            crossings.append(("apogee", lambda x: x[5]))
        if airborne and state[2] > 0 >= updated[2]:
            crossings.append(("ground", lambda x: x[2]))
        if crossings:
            located = [(plant.Event_Locate(time_s, state, dt, fn)[0], name) for name, fn in crossings]
            event_dt, name = min(located)
            event_us = min(target, max(now+1, now+math.ceil(event_dt*1e6)))
            updated = plant.Step(time_s, state, (event_us-now)/1e6)
            target = event_us
            events.append({"event": name, "time_s": time_s+event_dt, "phase": phase})
            if name == "rail_exit":
                plant.on_rail = False
            elif name == "apogee":
                apogee, phase = True, "descent"
            elif name == "ground":
                updated[2], finished = 0., True
        airborne |= bool(updated[2] > .01)
        state, now = updated, target
        progress(min(99, int(now/end*100)))
    if cancel():
        raise SimulationCancelled("已取消；未发布结果")
    if nav is not None:
        algorithm_identity["source"] = nav.implementation_identity
    if controller is not None and hasattr(controller, "Export"):
        algorithm_identity["parameters"] = controller.Export()
    progress(100)
    return {"schema": "treediagram.run/1", "run_id": str(uuid4()), "status": "succeeded",
            "input_digest": Design_Digest(design), "design": json.loads(json.dumps(asdict(design))),
            "backend": "treediagram.rk4/1", "algorithm_identity": algorithm_identity,
            "sample_order": "physics,sample,arrival(IMU before GNSS at same arrival time; then stable ordinal),event,control,output",
            "time_resolution_us": 1, "rows": rows, "events": events,
            "samples": samples, "arrivals": arrivals,
            "diagnostics": diagnostics+sorted(plant.diagnostics), "algorithm_results":algorithm_counts,
            "summary": {"maximum_altitude_m": max(r["position_enu_m"][2] for r in rows),
                        "duration_s": rows[-1]["time_s"], "landed": finished,
                        "total_impulse_ns": float(plant.total_impulse),
                        "hardware_validation": "not performed"}}
