"""Run persistence validates input identity and prevents partial-success records."""
from __future__ import annotations

import math
from pathlib import Path

from .design import Design_Decode, Design_Digest, Number_Check
from .geometry import Vector_Check, Inertia_Check
from .io import Json_Read, Json_Write


def Run_Validate(run: dict) -> None:
    if not isinstance(run, dict) or run.get("schema") != "treediagram.run/1" or run.get("status") != "succeeded":
        raise ValueError("run: unsupported or incomplete result")
    expected={"schema","run_id","status","input_digest","design","backend","algorithm_identity",
              "sample_order","time_resolution_us","rows","events","samples","arrivals",
              "diagnostics","algorithm_results","summary"}
    if set(run)!=expected or not isinstance(run["run_id"],str) or not 1<=len(run["run_id"])<=128:
        raise ValueError("run: invalid identity/fields")
    if run["backend"]!="treediagram.rk4/1" or type(run["time_resolution_us"]) is not int or run["time_resolution_us"]!=1:
        raise ValueError("run: unsupported backend/time contract")
    design = Design_Decode(run["design"])
    if Design_Digest(design) != run["input_digest"]:
        raise ValueError("run: design digest mismatch")
    rows = run.get("rows")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 600001:
        raise ValueError("run: invalid result row count")
    previous = -1.
    for row in rows:
        t = row["time_s"]
        if type(t) not in (int, float) or not math.isfinite(t) or t <= previous:
            raise ValueError("run: time must be strictly increasing")
        previous = t
        for key in ("position_enu_m", "velocity_enu_mps", "omega_b_radps"):
            Vector_Check(row[key], 3, key)
        Vector_Check(row["cg_body_m"],3,"cg_body_m")
        Inertia_Check(row["inertia_kg_m2"])
        Number_Check(row["mass_kg"],"mass_kg",1e-9,1e9)
        for key in ("control_request_nm","actuator_actual_nm","deflection_rad","wheel_momentum_nms","rcs_used_kg"):
            Number_Check(row[key],key,-1e12,1e12)
        for key,size in (("estimate_position_enu_m",3),("estimate_velocity_enu_mps",3),("estimate_q_nb",4)):
            if row[key] is not None:
                value=Vector_Check(row[key],size,key)
                if size==4 and abs(sum(value*value)-1)>1e-5:
                    raise ValueError("run: estimate quaternion norm invalid")
        if row["phase"] not in ("powered","coast","descent"):
            raise ValueError("run: invalid phase")
        q = Vector_Check(row["q_nb"], 4, "q_nb")
        if abs(sum(q*q)-1) > 1e-5:
            raise ValueError("run: quaternion norm invalid")
    summary=run["summary"]
    if not isinstance(summary,dict) or type(summary.get("landed")) is not bool:
        raise ValueError("run: invalid summary")
    for key in ("maximum_altitude_m","duration_s","total_impulse_ns"):
        Number_Check(summary[key],key,0,1e12)
    if summary["duration_s"]!=rows[-1]["time_s"] or abs(summary["maximum_altitude_m"]-max(r["position_enu_m"][2] for r in rows))>1e-8:
        raise ValueError("run: summary differs from result rows")
    if not isinstance(run["diagnostics"],list) or any(not isinstance(x,str) for x in run["diagnostics"]):
        raise ValueError("run: invalid diagnostic text")
    if not isinstance(run["algorithm_identity"],dict) or not isinstance(run["algorithm_results"],dict):
        raise ValueError("run: invalid algorithm record")


def Run_Save(path: Path, run: dict) -> None:
    Run_Validate(run)
    Json_Write(path, run)


def Run_Load(path: Path) -> dict:
    run = Json_Read(path)
    Run_Validate(run)
    return run
