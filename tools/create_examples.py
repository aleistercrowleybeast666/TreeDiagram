"""Create bounded, self-contained scientific examples from the public API."""
from dataclasses import asdict, replace
from pathlib import Path

from treediagram.design import Design_CreateExample
from treediagram.importers import Motor_Import, Motor_DeriveRoundoff
from treediagram.io import Json_Write


def Examples_Write():
    root=Path(__file__).resolve().parents[1]
    output=root/"examples"
    for name in ("actuators","estimators"):
        (output/name).mkdir(parents=True,exist_ok=True)
    for controller in ("none","pid","lqr"):
        name="native" if controller=="none" else controller
        design=replace(Design_CreateExample(controller),id="example-"+name+"-v1")
        Json_Write(output/(name+".json"),asdict(design))
    for actuator in ("gimbal","fin","wheel","rcs"):
        design=Design_CreateExample("pid",actuator)
        design=replace(design,id="example-"+actuator+"-v1",scenario=replace(design.scenario,duration_s=3.))
        Json_Write(output/"actuators"/(actuator+".json"),asdict(design))
    for kind in ("ins","sf6","kf6","eskf15","eskf20","inekf15","inekf20"):
        design=Design_CreateExample("pid")
        design=replace(design,id="example-"+kind+"-v1",scenario=replace(design.scenario,duration_s=1.),
                       control=replace(design.control,estimator=kind),
                       sensors=replace(design.sensors,gnss_delay_us=0,auxiliary_delay_us=0))
        Json_Write(output/"estimators"/(kind+".json"),asdict(design))
    for name,fixture,policy in (("underline-pid","valid_positive",False),("underline","valid_synthetic",True)):
        design=replace(Design_CreateExample("pid"),id="example-"+name+"-v1")
        design,_=Motor_Import(root/"tests/fixtures/motor"/(fixture+".tdmotor.json"),design)
        if policy:design=Motor_DeriveRoundoff(design,1e-9)
        Json_Write(output/(name+".json"),asdict(design))


if __name__=="__main__":Examples_Write()
