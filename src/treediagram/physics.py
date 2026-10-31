"""One production 6DoF backend: RK4 with bounded event localization.

State [p_ENU(3),v_ENU(3),q_nb(4),omega_b(3),deflection,wheel_H,rcs_used,throttle].
Propellant consumption is an explicit impulse-proportional approximation. The
outflow carries the removed distribution's co-rotating angular momentum, cancelling
I_dot*omega. No internal slosh/relative-flow torque is inferred from a thrust curve.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .design import Assembly_Aggregate, Design, Part, Part_Inertia
from .geometry import Inertia_Shift, Quaternion_Matrix, Quaternion_Multiply, Quaternion_Normalize


@dataclass(frozen=True)
class Atmosphere:
    temperature_k: float
    pressure_pa: float
    density_kg_m3: float
    sound_mps: float


def Environment_Atmosphere(height_m: float) -> Atmosphere:
    if not math.isfinite(height_m) or not -100 <= height_m <= 11000:
        raise ValueError("environment: ISA troposphere supports -100..11000 m only")
    temperature = 288.15 - .0065 * height_m
    pressure = 101325. * (temperature / 288.15) ** 5.2558797
    return Atmosphere(temperature, pressure, pressure/(287.05287*temperature),
                      math.sqrt(1.4*287.05287*temperature))


def RigidBody_Derivative(state, mass, inertia, force_n, torque_b, gravity=0., wheel_h=0., wheel_h_dot=0.):
    """Force is navigation-frame, moment is about current CG in body frame."""
    rotation = Quaternion_Matrix(state[6:10])
    omega = state[10:13]
    out = np.zeros_like(state)
    out[:3] = state[3:6]
    out[3:6] = force_n / mass + np.array([0., 0., -gravity])
    out[6:10] = .5 * Quaternion_Multiply(state[6:10], [0., *omega])
    momentum = inertia @ omega + np.array([0., wheel_h, 0.])
    out[10:13] = np.linalg.solve(inertia, torque_b - np.cross(omega, momentum)
                                - np.array([0., wheel_h_dot, 0.]))
    return out


def Integrator_Step(derivative, time_s, state, dt_s):
    if dt_s <= 0 or not np.all(np.isfinite(state)):
        raise ValueError("integrator: invalid state/time interval")
    k1 = derivative(time_s, state)
    k2 = derivative(time_s+dt_s/2, state+dt_s*k1/2)
    k3 = derivative(time_s+dt_s/2, state+dt_s*k2/2)
    k4 = derivative(time_s+dt_s, state+dt_s*k3)
    updated = state + dt_s*(k1+2*k2+2*k3+k4)/6
    if not np.all(np.isfinite(updated)):
        raise ValueError("integrator: nonfinite state; run discarded")
    updated[6:10] = Quaternion_Normalize(updated[6:10])
    return updated


class Plant:
    def __init__(self, design: Design):
        self.design = design
        self.dry_mass, self.dry_cg, self.dry_inertia = Assembly_Aggregate(design.parts)
        self.times = np.array(design.motor.time_s)
        self.thrust = np.array(design.motor.thrust_n)
        increments = np.diff(self.times) * (self.thrust[1:] + self.thrust[:-1]) / 2
        self.impulses = np.r_[0., np.cumsum(increments)]
        self.total_impulse = self.impulses[-1]
        self.burnout_s = design.motor.ignition_s + max(0., self.times[-1])
        self.diagnostics: set[str] = set()
        tilt = math.radians(design.scenario.launch_tilt_deg)
        self.initial_q = np.array([math.cos(tilt/2), 0., math.sin(tilt/2), 0.])
        self.rail_axis = Quaternion_Matrix(self.initial_q)[:, 2]
        self.on_rail = design.scenario.rail_length_m > 0
        self.request_nm = 0.
        self.command_enabled = False
        self.rcs_hold_until_s = -1.
        self.rcs_sign = 1.

    def State_Create(self):
        result = np.zeros(17)
        result[6:10] = self.initial_q
        return result

    def Motor_Evaluate(self, time_s):
        relative = time_s - self.design.motor.ignition_s
        if relative < 0 or relative < self.times[0]:
            return 0., 1.
        if relative >= self.times[-1]:
            return 0., 0.
        index = min(len(self.times)-2, max(0, np.searchsorted(self.times, relative, side="right")-1))
        delta = relative - self.times[index]
        slope = (self.thrust[index+1]-self.thrust[index])/(self.times[index+1]-self.times[index])
        thrust = self.thrust[index]+slope*delta
        impulse = self.impulses[index] + self.thrust[index]*delta + .5*slope*delta*delta
        return float(thrust), float(np.clip(1-impulse/self.total_impulse, 0., 1.))

    def Mass_Evaluate(self, time_s, rcs_used=0.):
        motor, c = self.design.motor, self.design.control
        _, fraction = self.Motor_Evaluate(time_s)
        motor_mass = motor.dry_mass_kg + motor.propellant_mass_kg*fraction
        motor_position = np.asarray(motor.position_m)
        motor_tensor = Part_Inertia(Part("m", "m", "motor", mass_kg=motor_mass,
                                         length_m=motor.length_m, radius_m=motor.radius_m))
        motor_rotation=Quaternion_Matrix(motor.rotation_bm_wxyz)
        motor_tensor=motor_rotation@motor_tensor@motor_rotation.T
        rcs_mass = max(0., c.rcs_propellant_kg-rcs_used) if c.actuator == "rcs" else 0.
        mass = self.dry_mass + motor_mass + rcs_mass
        cg = (self.dry_mass*self.dry_cg + motor_mass*motor_position)/mass
        inertia = (self.dry_inertia + Inertia_Shift(self.dry_mass, self.dry_cg-cg)
                   + motor_tensor + Inertia_Shift(motor_mass, motor_position-cg)
                   + Inertia_Shift(rcs_mass, -cg))
        if c.actuator == "wheel":
            # Wheel dry transverse inertia is explicit; included once in plant tensor.
            inertia += np.diag([c.wheel_inertia_kg_m2/2, c.wheel_inertia_kg_m2, c.wheel_inertia_kg_m2/2])
        return mass, cg, inertia

    def Wind_Get(self, time_s, height_m):
        s = self.design.scenario
        gust = s.wind_gust_mps*np.array([math.sin(.7*time_s), math.sin(.4*time_s), 0.])
        return np.asarray(s.wind_enu_mps) + np.asarray(s.wind_shear_per_s)*max(0., height_m) + gust

    def Aero_Evaluate(self, time_s, state, cg):
        s = self.design.scenario
        rotation = Quaternion_Matrix(state[6:10])
        atmosphere = Environment_Atmosphere(state[2])
        air_b = rotation.T @ (state[3:6]-self.Wind_Get(time_s, state[2]))
        speed = np.linalg.norm(air_b)
        dynamic = .5*atmosphere.density_kg_m3*speed*speed
        if speed < 1e-9:
            return np.zeros(3), np.zeros(3), dynamic, atmosphere
        transverse = np.linalg.norm(air_b[:2])
        angle = math.atan2(transverse, air_b[2])
        if angle > math.radians(s.aero_max_angle_deg):
            self.diagnostics.add("气动超出已声明小攻角域；法向系数按边界限幅，结果属外推")
        if speed / atmosphere.sound_mps > s.aero_max_mach:
            self.diagnostics.add("气动超出亚声速系数适用域；未加入跨声速修正")
        force = -dynamic*s.reference_area_m2*s.drag_coefficient*air_b/speed
        if transverse > 1e-10:
            coefficient = s.normal_slope_per_rad*min(angle, math.radians(s.aero_max_angle_deg))
            force[:2] -= dynamic*s.reference_area_m2*coefficient*air_b[:2]/transverse
        torque = np.cross(np.asarray(s.cp_body_m)-cg, force)
        torque -= (.5*atmosphere.density_kg_m3*speed*s.reference_area_m2
                   *s.reference_length_m**2*s.damping_coefficient*state[10:13])
        return force, torque, dynamic, atmosphere

    def Actuator_Evaluate(self, time_s, state, thrust, dynamic, cg, *, rcs_active=None):
        c, motor = self.design.control, self.design.motor
        motor_rotation=Quaternion_Matrix(motor.rotation_bm_wxyz)
        force = motor_rotation@np.array([0.,0.,thrust])
        motor_lever=np.asarray(motor.position_m)-cg
        torque=np.cross(motor_lever,force)
        derivative = np.zeros(4)
        request = float(np.clip(self.request_nm, -c.torque_limit_nm, c.torque_limit_nm))
        lever = motor_lever if c.actuator=="gimbal" else np.asarray(c.actuator_position_m)-cg
        effective_lever = lever[2]
        actual = 0.
        if c.actuator in ("gimbal", "fin"):
            coefficient = thrust*np.cross(lever,motor_rotation[:,0])[1] if c.actuator == "gimbal" else dynamic*c.fin_area_m2*effective_lever*c.fin_slope_per_rad
            desired = np.clip((request-torque[1])/coefficient, -c.angle_limit_rad, c.angle_limit_rad) if abs(coefficient) > 1e-8 else 0.
            if not self.command_enabled:
                desired=0.
            if c.actuator == "gimbal" and not motor.gimbal_capable:
                desired = 0.
            derivative[0] = np.clip((desired-state[13])/c.response_s, -c.rate_limit_radps, c.rate_limit_radps)
            angle = np.clip(state[13], -c.angle_limit_rad, c.angle_limit_rad)
            if c.actuator == "gimbal" and motor.gimbal_capable:
                force = thrust*motor_rotation@np.array([math.sin(angle), 0., math.cos(angle)])
                torque = np.cross(lever, force)
            elif c.actuator == "fin":
                fin_force = np.array([dynamic*c.fin_area_m2*c.fin_slope_per_rad*angle, 0., -dynamic*c.fin_area_m2*angle*angle])
                force += fin_force
                torque += np.cross(lever, fin_force)
            actual = torque[1]
        elif c.actuator == "wheel":
            limit = c.wheel_inertia_kg_m2*c.wheel_speed_limit_radps
            hdot = -request
            if abs(state[14]) >= limit and hdot*state[14] > 0:
                hdot = 0.
            derivative[1] = hdot
            actual = -hdot
        elif c.actuator == "rcs":
            # Explicit paired +/- X thrusters at the same aft station; one axis only.
            has_fuel = state[15] < c.rcs_propellant_kg if rcs_active is None else rcs_active
            demand = min(1., abs(request)/(c.rcs_force_n*max(abs(effective_lever), 1e-8)))
            if not has_fuel:
                demand = 0.
            if time_s < self.rcs_hold_until_s and has_fuel:
                demand = max(demand, .2)
            derivative[3] = (demand-state[16])/c.response_s
            throttle = np.clip(state[16], 0., 1.) if has_fuel else 0.
            rcs_force = np.array([self.rcs_sign*c.rcs_force_n*throttle, 0., 0.])
            force += rcs_force
            torque += np.cross(lever, rcs_force)
            derivative[2] = np.linalg.norm(rcs_force)/(c.rcs_isp_s*9.80665)
            actual = torque[1]
        return force, torque, derivative, float(actual)

    def Control_Set(self, request_nm, time_s, enabled=True):
        if not math.isfinite(request_nm):
            raise ValueError("controller returned nonfinite command")
        self.request_nm = float(request_nm)
        self.command_enabled = bool(enabled)
        if self.design.control.actuator == "rcs" and abs(request_nm) > 1e-9:
            lever_z=self.design.control.actuator_position_m[2]-self.Mass_Evaluate(time_s)[1][2]
            self.rcs_sign = math.copysign(1., request_nm*lever_z)
            self.rcs_hold_until_s = max(self.rcs_hold_until_s, time_s+self.design.control.minimum_pulse_s)

    def Derivative(self, time_s, state, *, wheel_h_dot=None, rcs_active=None):
        mass, cg, inertia = self.Mass_Evaluate(time_s, state[15])
        thrust, _ = self.Motor_Evaluate(time_s)
        aero_force, aero_torque, dynamic, _ = self.Aero_Evaluate(time_s, state, cg)
        prop_force, prop_torque, actuators, _ = self.Actuator_Evaluate(
            time_s, state, thrust, dynamic, cg, rcs_active=rcs_active
        )
        if wheel_h_dot is not None:
            # A wheel substep has one fixed internal motor torque, including
            # the left limit at its saturation endpoint. All RK stages must
            # use that same exchange for wheel momentum and body reaction.
            actuators[1] = wheel_h_dot
        rotation = Quaternion_Matrix(state[6:10])
        output = RigidBody_Derivative(state, mass, inertia, rotation@(aero_force+prop_force),
                                     aero_torque+prop_torque, self.design.scenario.gravity_mps2,
                                     state[14], actuators[1])
        output[13:17] = actuators
        if self.on_rail:
            acceleration = np.dot(output[3:6], self.rail_axis)
            if np.dot(state[:3], self.rail_axis) <= 0 and np.dot(state[3:6], self.rail_axis) <= 0:
                acceleration = max(0., acceleration)
            output[:3] = np.dot(state[3:6], self.rail_axis)*self.rail_axis
            output[3:6] = acceleration*self.rail_axis
            output[6:13] = 0.
        return output

    def _Wheel_Step(self, time_s, state, dt_s):
        c = self.design.control
        limit = c.wheel_inertia_kg_m2*c.wheel_speed_limit_radps
        if not math.isfinite(dt_s) or dt_s <= 0 or abs(state[14]) > limit:
            raise ValueError("wheel: invalid time interval or stored momentum exceeds limit")
        rate = -float(np.clip(self.request_nm, -c.torque_limit_nm, c.torque_limit_nm))
        target = math.copysign(limit, rate)
        boundary_s = (target-state[14])/rate if rate else math.inf
        if boundary_s <= 0:
            rate, boundary_s = 0., math.inf
        active_s = min(dt_s, boundary_s)
        updated = Integrator_Step(
            lambda t, x: self.Derivative(t, x, wheel_h_dot=rate), time_s, state, active_s
        )
        if boundary_s <= dt_s:
            # The crossing time is analytic because the bounded command is
            # constant within this Step. Only roundoff may differ from target;
            # a material discrepancy is a failed run, never a clipping repair.
            if abs(updated[14]-target) > 64*np.finfo(float).eps*max(1., limit):
                raise ValueError("wheel: saturation event disagrees with integrated momentum")
            updated[14] = target
            remaining_s = dt_s-boundary_s
            if remaining_s > 0:
                updated = Integrator_Step(
                    lambda t, x: self.Derivative(t, x, wheel_h_dot=0.),
                    time_s+boundary_s, updated, remaining_s,
                )
        return updated

    def _Rcs_Substep(self, time_s, state, dt_s):
        limit = self.design.control.rcs_propellant_kg
        active = state[15] < limit
        derivative = lambda t, x: self.Derivative(t, x, rcs_active=active)
        updated = Integrator_Step(derivative, time_s, state, dt_s)
        if not active or updated[15] < limit:
            return updated
        # Solve the exhaustion boundary using the same active force/mass-flow
        # equations as the body dynamics. Never switch only selected RK stages
        # off and then clip away fuel that already produced an angular impulse.
        low, high = 0., dt_s
        for _ in range(48):
            middle = (low+high)/2
            candidate = Integrator_Step(derivative, time_s, state, middle)
            if candidate[15] < limit:
                low = middle
            else:
                high, updated = middle, candidate
        if abs(updated[15]-limit) > 64*np.finfo(float).eps*max(1., limit):
            raise ValueError("RCS: exhaustion event failed to converge; reduce physics step")
        updated[15] = limit  # Only the verified root's floating roundoff is normalized.
        if dt_s > high:
            updated = Integrator_Step(
                lambda t, x: self.Derivative(t, x, rcs_active=False),
                time_s+high, updated, dt_s-high,
            )
        return updated

    def _Rcs_Step(self, time_s, state, dt_s):
        c = self.design.control
        if (not math.isfinite(dt_s) or dt_s <= 0
                or not 0 <= state[15] <= c.rcs_propellant_kg):
            raise ValueError("RCS: invalid time interval or stored propellant consumption")
        # Resolve the existing first-order valve without unstable giant RK
        # stages. Work is statically capped, including a minimum-pulse boundary.
        count = max(1, math.ceil(dt_s/(.25*c.response_s)))
        if count > 256:
            raise ValueError("RCS: valve needs more than 256 substeps; reduce physics step")
        boundaries = [time_s+dt_s*i/count for i in range(count+1)]
        if time_s < self.rcs_hold_until_s < time_s+dt_s:
            boundaries.append(self.rcs_hold_until_s)
            boundaries = sorted(set(boundaries))
        updated = state
        for left, right in zip(boundaries[:-1], boundaries[1:], strict=True):
            updated = self._Rcs_Substep(left, updated, right-left)
        return updated

    def Step(self, time_s, state, dt_s):
        if self.design.control.actuator == "wheel":
            updated = self._Wheel_Step(time_s, state, dt_s)
        elif self.design.control.actuator == "rcs":
            updated = self._Rcs_Step(time_s, state, dt_s)
        else:
            updated = Integrator_Step(self.Derivative, time_s, state, dt_s)
        # Wheel momentum is solved at its physical boundary, never clipped
        # independently of the equal-and-opposite angular impulse on the body.
        c = self.design.control
        updated[13] = np.clip(updated[13], -c.angle_limit_rad, c.angle_limit_rad)
        updated[16] = np.clip(updated[16], 0., 1.)
        return updated

    def Event_Locate(self, time_s, state, dt_s, condition):
        low, high = 0., dt_s
        initial = condition(state)
        for _ in range(32):
            mid = (low+high)/2
            value = condition(self.Step(time_s, state, mid))
            if value*initial > 0:
                low = mid
            else:
                high = mid
        return high, self.Step(time_s, state, high)
