"""Headless product entry point using exactly the desktop core."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace
from pathlib import Path

from .design import Design_CreateExample, Design_Decode, Design_Validate
from .importers import Motor_Import, Ork_Import
from .io import Json_Read, Json_Write
from .results import Run_Load, Run_Save
from .simulation import Simulation_Run


def Cli_Main(argv=None) -> int:
    parser=argparse.ArgumentParser(prog="treediagram-cli",description="Offline 6DoF engineering workbench")
    sub=parser.add_subparsers(dest="command",required=True)
    example=sub.add_parser("example",help="write a complete offline native model")
    example.add_argument("output",type=Path)
    example.add_argument("--controller",choices=("none","pid","lqr"),default="none")
    example.add_argument("--actuator",choices=("gimbal","fin","wheel","rcs"),default="gimbal")
    run=sub.add_parser("run",help="simulate a validated model")
    run.add_argument("design",type=Path);run.add_argument("output",type=Path)
    check=sub.add_parser("check",help="validate structure and show missing simulation inputs")
    check.add_argument("design",type=Path)
    motor=sub.add_parser("import-motor",help="preview/commit a motor source; installation is preserved")
    motor.add_argument("design",type=Path);motor.add_argument("motor",type=Path);motor.add_argument("output",type=Path)
    motor.add_argument("--negative-roundoff-tolerance",type=float,default=None,help="explicit derived-curve policy in N; only negative values within tolerance become zero")
    ork=sub.add_parser("import-ork",help="import the documented single-stage geometry subset")
    ork.add_argument("input",type=Path);ork.add_argument("output",type=Path)
    export=sub.add_parser("export-parameters",help="export exact run-bound SilverStar tuning bundle")
    export.add_argument("run",type=Path);export.add_argument("output",type=Path)
    args=parser.parse_args(argv)
    try:
        if args.command=="example":
            Json_Write(args.output,asdict(Design_CreateExample(args.controller,args.actuator)))
        elif args.command=="check":
            design=Design_Decode(Json_Read(args.design));issues=Design_Validate(design,False)
            print(json.dumps({"structurally_valid":True,"runnable":not issues,"issues":issues},ensure_ascii=False,indent=2))
            return 2 if issues else 0
        elif args.command=="run":
            result=Simulation_Run(Design_Decode(Json_Read(args.design)))
            Run_Save(args.output,result);print(json.dumps(result["summary"],ensure_ascii=False,indent=2))
        elif args.command=="import-motor":
            candidate,changes=Motor_Import(args.motor,Design_Decode(Json_Read(args.design)))
            if args.negative_roundoff_tolerance is not None:
                from .importers import Motor_DeriveRoundoff
                candidate=Motor_DeriveRoundoff(candidate,args.negative_roundoff_tolerance)
            Json_Write(args.output,asdict(candidate));print("changed: "+", ".join(changes))
        elif args.command=="import-ork":
            candidate=Ork_Import(args.input);Json_Write(args.output,asdict(candidate))
            print("\n".join(Design_Validate(candidate,False)))
        elif args.command=="export-parameters":
            from .export import Parameters_ExportRun
            Parameters_ExportRun(Run_Load(args.run),args.output)
        return 0
    except (ValueError,OSError,KeyError,TypeError,RuntimeError) as exc:
        print(f"ERROR: {exc}")
        return 2
