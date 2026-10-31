from dataclasses import asdict, replace
import math
import numpy as np
import pytest

from treediagram.design import (Assembly_Aggregate, Design_CreateExample, Design_Decode,
                               Design_Validate, Part)
from treediagram.geometry import Quaternion_Matrix, Inertia_Check
from treediagram.physics import Integrator_Step, RigidBody_Derivative, Plant, Environment_Atmosphere
from treediagram.simulation import Simulation_Run, SimulationCancelled


def state():
    value=np.zeros(13);value[6]=1.;return value


def test_hamilton_rotation_and_parallel_axis_nested_assembly():
    q=(math.sqrt(.5),0.,math.sqrt(.5),0.)
    assert Quaternion_Matrix(q)@np.array([0.,0.,1.]) == pytest.approx([1.,0.,0.])
    parts=(Part("a","a","mass",mass_kg=2.,rotation_wxyz=q),
           Part("b","b","mass","a",(0.,0.,1.),mass_kg=2.))
    mass,cg,inertia=Assembly_Aggregate(parts)
    assert mass==4 and cg==pytest.approx([.5,0,0])
    assert inertia[1,1]>1 and inertia[2,2]>1
    with pytest.raises(ValueError,match="triangle"):
        Inertia_Check([[1,0,0],[0,1,0],[0,0,4]])


def test_free_and_constant_force_analytic_solution():
    initial=state();initial[3:6]=[1,2,3]
    for force in (np.zeros(3),np.array([2.,-4.,6.])):
        y=initial.copy()
        for tick in range(100):
            y=Integrator_Step(lambda t,x:RigidBody_Derivative(x,2.,np.eye(3),force,np.zeros(3)),tick*.01,y,.01)
        assert y[:3]==pytest.approx(initial[3:6]+force/4,abs=1e-11)
        assert y[3:6]==pytest.approx(initial[3:6]+force/2,abs=1e-11)


def test_constant_torque_and_free_body_energy_momentum():
    y=state()
    for tick in range(200):
        y=Integrator_Step(lambda t,x:RigidBody_Derivative(x,1.,np.eye(3),np.zeros(3),np.array([0,0,.2])),tick*.01,y,.01)
    assert y[12]==pytest.approx(.4,abs=1e-12)
    assert y[6:10]==pytest.approx([math.cos(.2),0,0,math.sin(.2)],abs=1e-10)
    y=state();y[10:13]=[.7,1.,.2];inertia=np.diag([1.,1.5,2.])
    energy0=y[10:13]@inertia@y[10:13]/2
    momentum0=inertia@y[10:13]
    for tick in range(400):
        y=Integrator_Step(lambda t,x:RigidBody_Derivative(x,1.,inertia,np.zeros(3),np.zeros(3)),tick*.005,y,.005)
    assert y[10:13]@inertia@y[10:13]/2==pytest.approx(energy0,rel=1e-10)
    assert Quaternion_Matrix(y[6:10])@inertia@y[10:13]==pytest.approx(momentum0,abs=1e-10)


def test_variable_mass_wind_and_zero_air_speed():
    design=Design_CreateExample();plant=Plant(design);y=plant.State_Create()
    full=plant.Mass_Evaluate(0);empty=plant.Mass_Evaluate(100)
    assert full[0]-empty[0]==pytest.approx(design.motor.propellant_mass_kg)
    assert not np.allclose(full[1],empty[1]) and not np.allclose(full[2],empty[2])
    assert plant.Motor_Evaluate(100)==(0.,0.)
    y[3:6]=design.scenario.wind_enu_mps
    force,torque,dynamic,_=plant.Aero_Evaluate(0,y,full[1])
    assert np.all(force==0) and np.all(torque==0) and dynamic==0
    assert Environment_Atmosphere(1000).density_kg_m3<Environment_Atmosphere(0).density_kg_m3
    with pytest.raises(ValueError):Environment_Atmosphere(12000)


@pytest.mark.parametrize("kind",["gimbal","fin","wheel","rcs"])
def test_actuator_physical_authority_and_limits(kind):
    design=Design_CreateExample("none",kind);plant=Plant(design);plant.on_rail=False
    y=plant.State_Create();y[3:6]=[0,0,30]
    plant.Control_Set(.2,0)
    for i in range(200):y=plant.Step(i*.001,y,.001)
    mass,cg,_=plant.Mass_Evaluate(.2,y[15]);thrust,_=plant.Motor_Evaluate(.2)
    dynamic=plant.Aero_Evaluate(.2,y,cg)[2]
    force,torque,delta,actual=plant.Actuator_Evaluate(.2,y,thrust,dynamic,cg)
    assert np.isfinite(y).all() and abs(actual)>0
    assert abs(y[13])<=design.control.angle_limit_rad
    if kind=="fin":assert plant.Actuator_Evaluate(.2,y,thrust,0.,cg)[3]==0
    if kind=="gimbal":assert plant.Actuator_Evaluate(10,y,0.,dynamic,cg)[3]==0
    if kind=="wheel":assert abs(y[14])<=design.control.wheel_inertia_kg_m2*design.control.wheel_speed_limit_radps
    if kind=="rcs":
        assert y[15]>0
        y[15]=design.control.rcs_propellant_kg
        assert plant.Actuator_Evaluate(.2,y,thrust,dynamic,cg)[3]==0


def test_reaction_wheel_total_angular_momentum():
    # Isolate fixed inertia and zero external torque; wheel counter-torque is internal.
    y=np.zeros(17);y[6]=1.;inertia=np.diag([.3,.4,.5])
    def derivative(t,x):
        result=RigidBody_Derivative(x,1.,inertia,np.zeros(3),np.zeros(3),wheel_h=x[14],wheel_h_dot=.02)
        result[14]=.02
        return result
    for i in range(100):y=Integrator_Step(derivative,i*.01,y,.01)
    assert inertia@y[10:13]+[0,y[14],0]==pytest.approx([0,0,0],abs=1e-12)


def test_plant_wheel_saturation_and_reversal_conserve_inertial_momentum():
    design=Design_CreateExample("none","wheel")
    design=replace(design,motor=replace(design.motor,ignition_s=100.),
                   scenario=replace(design.scenario,rail_length_m=0.,gravity_mps2=0.,
                                    wind_enu_mps=(0.,0.,0.),drag_coefficient=0.,
                                    normal_slope_per_rad=0.,damping_coefficient=0.))
    plant=Plant(design);y=plant.State_Create()
    initial_mass,_,inertia=plant.Mass_Evaluate(0.)
    initial_h=Quaternion_Matrix(y[6:10])@(inertia@y[10:13]+[0.,y[14],0.])
    limit=design.control.wheel_inertia_kg_m2*design.control.wheel_speed_limit_radps
    history=[];momenta=[];step=.017
    for tick in range(80):
        plant.Control_Set(.37 if tick<40 else -.37,tick*step)
        y=plant.Step(tick*step,y,step)
        assert plant.Motor_Evaluate((tick+1)*step)[0]==0.
        assert plant.Mass_Evaluate((tick+1)*step)[0]==initial_mass
        momenta.append(Quaternion_Matrix(y[6:10])@(inertia@y[10:13]+[0.,y[14],0.]))
        history.append(y[14])
    assert min(history)==pytest.approx(-limit,abs=1e-14)
    assert max(history)==pytest.approx(limit,abs=1e-14)
    assert history[40]>history[39]  # Reversing the request unloads the saturated wheel.
    assert np.asarray(momenta)==pytest.approx(np.tile(initial_h,(80,1)),abs=1e-10)


def test_plant_wheel_three_axis_momentum_converges_through_saturation():
    design=Design_CreateExample("none","wheel")
    design=replace(design,motor=replace(design.motor,ignition_s=100.),
                   scenario=replace(design.scenario,rail_length_m=0.,gravity_mps2=0.,
                                    wind_enu_mps=(0.,0.,0.),drag_coefficient=0.,
                                    normal_slope_per_rad=0.,damping_coefficient=0.))
    errors=[]
    for step in (.017,.00425):
        plant=Plant(design);y=plant.State_Create();y[10:13]=[.3,.4,.2]
        inertia=plant.Mass_Evaluate(0.)[2]
        original=Quaternion_Matrix(y[6:10])@(inertia@y[10:13])
        maximum=0.;ticks=round(1.36/step)
        for tick in range(ticks):
            plant.Control_Set(.37 if tick<ticks//2 else -.37,tick*step)
            y=plant.Step(tick*step,y,step)
            h=Quaternion_Matrix(y[6:10])@(inertia@y[10:13]+[0.,y[14],0.])
            maximum=max(maximum,float(np.linalg.norm(h-original)))
        errors.append(maximum)
    # Finite RK4 gyroscopic error must converge, rather than being projected away.
    assert errors[0]<2e-6 and errors[1]<1e-8
    assert errors[0]/errors[1]>200


def test_plant_wheel_exact_boundary_and_invalid_stored_momentum():
    design=Design_CreateExample("none","wheel")
    design=replace(design,motor=replace(design.motor,ignition_s=100.),
                   scenario=replace(design.scenario,rail_length_m=0.,gravity_mps2=0.,
                                    wind_enu_mps=(0.,0.,0.)))
    plant=Plant(design);y=plant.State_Create()
    limit=design.control.wheel_inertia_kg_m2*design.control.wheel_speed_limit_radps
    plant.Control_Set(.2,0.)
    y=plant.Step(0.,y,limit/.2)
    assert y[14]==-limit
    at_limit=y.copy();y=plant.Step(limit/.2,y,.1)
    assert y[14]==at_limit[14] and y[10:13]==pytest.approx(at_limit[10:13],abs=1e-12)
    corrupt=y.copy();corrupt[14]=-limit-.001
    with pytest.raises(ValueError,match="stored momentum"):
        plant.Step(1.,corrupt,.01)


@pytest.mark.parametrize("step,initial_throttle",[(.005,1.),(.05,1.),(.005,0.),(.05,0.)])
def test_plant_rcs_exhaustion_respects_impulse_budget_and_rocket_equation(step,initial_throttle):
    class ImpulsePlant(Plant):
        def Derivative(self,time_s,state,**options):
            result=super().Derivative(time_s,state,**options)
            cg=self.Mass_Evaluate(time_s,state[15])[1]
            # An extra observable integrates actual produced force, not a
            # clipped fuel counter. No production state derivative is replaced.
            force=self.Actuator_Evaluate(time_s,state,0.,0.,cg,rcs_active=options.get("rcs_active"))[0]
            result[17]=np.linalg.norm(force)
            return result
    design=Design_CreateExample("none","rcs")
    design=replace(design,parts=(Part("b","body","mass",mass_kg=1.),),
                   motor=replace(design.motor,ignition_s=100.,position_m=(0.,0.,0.)),
                   control=replace(design.control,actuator_position_m=(0.,0.,0.),rcs_propellant_kg=1e-5),
                   scenario=replace(design.scenario,launch_tilt_deg=0.,rail_length_m=0.,gravity_mps2=0.,
                                    wind_enu_mps=(0.,0.,0.),drag_coefficient=0.,
                                    normal_slope_per_rad=0.,damping_coefficient=0.))
    Design_Validate(design)
    plant=ImpulsePlant(design);y=np.r_[plant.State_Create(),0.];y[16]=initial_throttle
    initial_mass=plant.Mass_Evaluate(0.)[0]
    plant.Control_Set(.2,0.)
    for tick in range(round(.2/step)):
        y=plant.Step(tick*step,y,step)
    final_mass=plant.Mass_Evaluate(.2,y[15])[0]
    exhaust_speed=design.control.rcs_isp_s*9.80665
    assert y[15]==design.control.rcs_propellant_kg
    assert y[17]==pytest.approx(design.control.rcs_propellant_kg*exhaust_speed,abs=1e-12)
    assert y[3]==pytest.approx(exhaust_speed*math.log(initial_mass/final_mass),abs=1e-10)
    assert y[4:6]==pytest.approx([0.,0.],abs=1e-14)
    coast=plant.Step(.2,y,.05)
    assert coast[3:6]==pytest.approx(y[3:6],abs=1e-14)
    assert coast[15]==y[15] and coast[17]==y[17]


def test_plant_rcs_rejects_corrupt_resource_state_and_unbounded_valve_work():
    design=Design_CreateExample("none","rcs")
    plant=Plant(design);y=plant.State_Create()
    y[15]=design.control.rcs_propellant_kg+.001
    with pytest.raises(ValueError,match="stored propellant"):
        plant.Step(0.,y,.005)
    stiff=replace(design,control=replace(design.control,response_s=1e-6))
    plant=Plant(stiff)
    with pytest.raises(ValueError,match="256 substeps"):
        plant.Step(0.,plant.State_Create(),.005)


def test_design_rejects_cycles_boolean_mass_and_missing_motor():
    design=Design_CreateExample()
    with pytest.raises(ValueError,match="cycle"):
        Design_Validate(replace(design,parts=(replace(design.parts[0],parent_id="body"),)))
    with pytest.raises(ValueError):Design_Decode({**asdict(design),"unexpected":True})
    with pytest.raises(ValueError):Design_Validate(replace(design,parts=(replace(design.parts[0],mass_kg=True),)))
    preview=replace(design,motor=None)
    assert Design_Validate(preview,False)
    with pytest.raises(ValueError):Design_Validate(preview)


def test_deterministic_causal_schedule_and_cancel():
    design=Design_CreateExample()
    design=replace(design,scenario=replace(design.scenario,duration_s=.5),
                   sensors=replace(design.sensors,imu_delay_us=7000))
    first=Simulation_Run(design);second=Simulation_Run(design)
    assert first["rows"]==second["rows"] and first["samples"]==second["samples"]
    byid={s["id"]:s for s in first["samples"]}
    assert all(x["consumed_us"]==byid[x["sample_id"]]["arrival_us"] for x in first["arrivals"])
    assert any(e["event"]=="rail_exit" for e in first["events"])
    with pytest.raises(SimulationCancelled):Simulation_Run(design,cancel=lambda:True)


def test_step_convergence_and_ground_event():
    design=Design_CreateExample()
    design=replace(design,scenario=replace(design.scenario,step_us=10000))
    coarse=Simulation_Run(design)
    fine=Simulation_Run(replace(design,scenario=replace(design.scenario,step_us=5000)))
    assert coarse["summary"]["landed"] and fine["summary"]["landed"]
    assert coarse["summary"]["maximum_altitude_m"]==pytest.approx(fine["summary"]["maximum_altitude_m"],abs=.03)
    assert coarse["rows"][-1]["position_enu_m"][2]==0
    assert coarse["summary"]["duration_s"]==pytest.approx(fine["summary"]["duration_s"],abs=.003)


def test_auxiliary_samples_reach_real_cores_without_truth_substitution():
    design=Design_CreateExample("pid")
    design=replace(design,scenario=replace(design.scenario,duration_s=.25),
                   sensors=replace(design.sensors,gnss_delay_us=0,auxiliary_delay_us=0))
    kf=Simulation_Run(design)
    assert kf["algorithm_results"].get("barometer_Ok",0)>0
    assert kf["algorithm_results"].get("magnetometer_Unsupported",0)>0
    enhanced=replace(design,control=replace(design.control,estimator="eskf20"))
    magnetic=Simulation_Run(enhanced)
    assert magnetic["algorithm_results"].get("magnetometer_Ok",0)>0
    delayed=Simulation_Run(replace(enhanced,sensors=replace(enhanced.sensors,auxiliary_delay_us=10000)))
    assert delayed["algorithm_results"].get("magnetometer_Stale",0)>0
    assert not delayed["algorithm_results"].get("magnetometer_Ok",0)


def test_motor_installation_and_forward_rcs_preserve_physical_moment_sign():
    design=Design_CreateExample()
    design=replace(design,motor=replace(design.motor,position_m=(.1,0,-.45)))
    plant=Plant(design);y=plant.State_Create();cg=plant.Mass_Evaluate(.5)[1]
    force,torque,_,actual=plant.Actuator_Evaluate(.5,y,50.,0.,cg)
    assert torque==pytest.approx(np.cross(np.asarray(design.motor.position_m)-cg,force))
    assert actual<0 and plant.Actuator_Evaluate(.5,y,50.,0.,cg)[2][0]==0
    design=Design_CreateExample("none","rcs")
    design=replace(design,control=replace(design.control,actuator_position_m=(0,0,.6)))
    plant=Plant(design);y=plant.State_Create();y[16]=1.;plant.Control_Set(.2,0.)
    cg=plant.Mass_Evaluate(0.)[1]
    assert plant.Actuator_Evaluate(0.,y,0.,0.,cg)[3]>0
