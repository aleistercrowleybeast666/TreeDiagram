"""Reproducible real-core example matrix; outputs summaries, never fake trajectories."""
from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import platform
import sys

import numpy as np
import scipy

from treediagram.design import Design_CreateExample, Design_Decode
from treediagram.export import Parameters_ExportRun
from treediagram.io import Json_Read, Json_Write
from treediagram.simulation import Simulation_Run
from treediagram.results import Run_Save


def Main():
    parser=argparse.ArgumentParser()
    parser.add_argument("output",type=Path)
    parser.add_argument("--runs",type=Path)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    if args.runs:args.runs.mkdir(parents=True,exist_ok=True)
    root=Path(__file__).resolve().parents[1]
    records=[]
    for controller in ("none","pid","lqr"):
        name="native" if controller=="none" else controller
        design=Design_Decode(Json_Read(root/"examples"/(name+".json")))
        run=Simulation_Run(design)
        if args.runs:Run_Save(args.runs/(name+".tdrun.json"),run)
        if controller!="none":Parameters_ExportRun(run,args.output/f"{controller}.sstuning.json")
        records.append({"case":controller,"summary":run["summary"],"algorithm_results":run["algorithm_results"],
                        "diagnostics":run["diagnostics"],"input_digest":run["input_digest"],
                        "algorithm_identity":run["algorithm_identity"]})
        print(controller,run["summary"],flush=True)
    for actuator in ("gimbal","fin","wheel","rcs"):
        design=Design_Decode(Json_Read(root/"examples/actuators"/(actuator+".json")))
        run=Simulation_Run(design)
        actual=max(abs(r["actuator_actual_nm"]) for r in run["rows"])
        if actual<=0:raise AssertionError(f"{actuator}: no physical response")
        records.append({"case":actuator,"summary":run["summary"],"max_actual_nm":actual,
                        "diagnostics":run["diagnostics"],"input_digest":run["input_digest"]})
        print(actuator,actual,flush=True)
    for kind in ("ins","sf6","kf6","eskf15","eskf20","inekf15","inekf20"):
        design=Design_Decode(Json_Read(root/"examples/estimators"/(kind+".json")))
        run=Simulation_Run(design)
        valid=[r for r in run["rows"] if r["estimate_position_enu_m"] is not None]
        if not valid:raise AssertionError(kind+": no actual C output")
        error=float(np.linalg.norm(np.asarray(valid[-1]["estimate_position_enu_m"])-valid[-1]["position_enu_m"]))
        records.append({"case":kind,"valid_estimates":len(valid),"final_position_error_m":error,
                        "algorithm_results":run["algorithm_results"],"input_digest":run["input_digest"]})
        print(kind,error,flush=True)
    design=Design_Decode(Json_Read(root/"examples/underline-pid.json"))
    run=Simulation_Run(design)
    if args.runs:Run_Save(args.runs/"underline-pid.tdrun.json",run)
    Parameters_ExportRun(run,args.output/"underline-pid.sstuning.json")
    records.append({"case":"underline-pid","summary":run["summary"],"algorithm_results":run["algorithm_results"],
                    "input_digest":run["input_digest"]})
    Json_Write(args.output/"matrix.json",{"python":sys.version,"platform":platform.platform(),
        "numpy":np.__version__,"scipy":scipy.__version__,"cases":records,
        "scope":"Host software only; scientific approximations and hardware limitations retained"})


if __name__=="__main__":Main()
