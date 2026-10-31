"""Execute real C kernels; analytic dynamics and adversarial contracts are oracles."""
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from treediagram.algorithms import (
    AlgorithmResult, ControlError, KINDS, LqrController, Lqr_Solve, Navigation, PidController,
)
from treediagram.algorithms.native import Sdk_Identity


@pytest.mark.parametrize("kind", KINDS)
def test_actual_c_stationary_and_constant_acceleration(kind):
    nav = Navigation(kind)
    for timestamp in range(0, 1000001, 10000):
        state = nav.Imu_Update(timestamp, (1.0, 0.0, 9.80665), (0.0, 0.0, 0.0))
    assert state.valid and state.result == AlgorithmResult.Ok
    assert state.position_enu_m == pytest.approx((0.5, 0, 0), abs=2e-5)
    assert state.velocity_enu_mps == pytest.approx((1, 0, 0), abs=2e-5)
    assert state.q_nb == pytest.approx((1, 0, 0, 0), abs=1e-6)


@pytest.mark.parametrize("kind", KINDS)
def test_quaternion_direction_and_no_truth_attitude_input(kind):
    nav = Navigation(kind)
    for timestamp in range(0, 1000001, 10000):
        state = nav.Imu_Update(timestamp, (0, 0, 9.80665), (0, 0, 0.2))
    assert state.valid
    assert state.q_nb == pytest.approx((np.cos(.1), 0, 0, np.sin(.1)), abs=1e-5)


@pytest.mark.parametrize("kind", KINDS)
def test_invalid_clock_does_not_advance_and_nan_is_rejected(kind):
    nav = Navigation(kind)
    for timestamp in (0, 10000, 20000):
        nav.Imu_Update(timestamp, (0, 0, 9.80665), (0, 0, 0))
    previous = nav.Snapshot_Get()
    assert nav.Imu_Update(10000, (0, 0, 9.80665), (0, 0, 0)).result == AlgorithmResult.Stale
    assert nav.Snapshot_Get().position_enu_m == previous.position_enu_m
    with pytest.raises(ValueError, match="finite"):
        nav.Imu_Update(30000, (float("nan"), 0, 0), (0, 0, 0))
    assert nav.Imu_Update(30000, (0, 0, 9.80665), (0, 0, 0)).result in (AlgorithmResult.Ok, AlgorithmResult.Waiting)


@pytest.mark.parametrize("kind", KINDS[1:])
def test_gnss_actual_timestamp_contract_and_duplicate(kind):
    nav = Navigation(kind)
    for timestamp in range(0, 1000001, 10000):
        nav.Imu_Update(timestamp, (0, 0, 9.80665), (0, 0, 0))
    delayed = nav.Gnss_Update(900000, 1000000, (0, 0, 0), (0, 0, 0))
    assert delayed == (AlgorithmResult.Ok if kind in ("kf6", "sf6") else AlgorithmResult.Stale)
    # SF6 explicitly requires receive time to increase between admitted epochs.
    for timestamp in (1010000, 1020000):
        nav.Imu_Update(timestamp, (0, 0, 9.80665), (0, 0, 0))
    assert nav.Gnss_Update(1020000, 1020000, (0, 0, 0), (0, 0, 0)) == AlgorithmResult.Ok
    assert nav.Gnss_Update(1020000, 1020000, (0, 0, 0), (0, 0, 0)) == AlgorithmResult.Stale
    assert nav.Gnss_Update(1100000, 1020000, (0, 0, 0), (0, 0, 0)) == AlgorithmResult.Stale


def test_independent_contexts_and_threads():
    def run(accel):
        nav = Navigation("kf6")
        for t in range(0, 1000001, 10000):
            result = nav.Imu_Update(t, (accel, 0, 9.80665), (0, 0, 0))
        return result.position_enu_m[0]
    with ThreadPoolExecutor(2) as pool:
        outputs = list(pool.map(run, (1., -2.)))
    assert outputs == pytest.approx((.5, -1.), abs=1e-5)


def test_pid_saturation_recovery_reset_and_invalid_period():
    pid = PidController(kp=1, ki=2, kd=0, output_limit=.2)
    assert all(pid.Step(100, 0, .01) == pytest.approx(.2) for _ in range(100))
    assert pid.integral == 0
    assert pid.Step(0, 0, .01) == 0
    with pytest.raises(ControlError):
        pid.Step(0, 0, .02)
    pid.Stop()
    with pytest.raises(ControlError, match="Stopped"):
        pid.Step(0, 0, .01)
    pid.Reset()
    assert pid.Step(0, 0, .01) == 0


def test_pid_derivative_is_on_measurement_not_setpoint():
    pid = PidController(kp=0, ki=0, kd=1, output_limit=100)
    assert pid.Step(0, 0, .01) == 0
    assert pid.Step(100, 0, .01) == 0
    assert pid.Step(100, .1, .01) < 0


def test_pid_corrupt_state_and_integral_overflow_fail_closed():
    pid = PidController()
    pid._context.integral = float("nan")
    with pytest.raises(ControlError, match="NumericError"):
        pid.Step(1, 0, .01)
    assert pid._context.started == 0
    pid = PidController(kp=0,ki=1e38,kd=0,output_limit=1,integral_limit=1)
    with pytest.raises(ControlError, match="NumericError"):
        pid.Step(1e38,0,.01)
    assert pid._context.started == 0


def test_lqr_psd_q_quantized_c_feedback_and_saturation():
    # Q need not be positive definite: stable unobserved state is admissible.
    design = Lqr_Solve([[.8, 0], [0, .7]], [[1], [0]], [[1, 0], [0, 0]], [[1]], dt_s=.01)
    assert design.residual < 1e-8 and design.closed_loop_radius < 1
    controller = LqrController(design, output_limit=.2)
    assert controller.Step([.01, .02]) == pytest.approx(float((-design.target_k @ [.01, .02])[0]), abs=1e-8)
    assert abs(controller.Step([100, 0])) == pytest.approx(.2)
    with pytest.raises(ControlError):
        controller.Step([float("nan"), 0])


def test_lqr_closed_loop_with_actual_c_limited_output():
    controller = LqrController(inertia_kg_m2=.1, dt_s=.01, output_limit=.1)
    state = np.array([.25, 0.])
    saturated = False
    for _ in range(1000):
        output = controller.Step(state)
        saturated |= abs(output) >= .0999
        state = controller.design.a @ state + controller.design.b[:, 0] * output
    assert saturated and np.linalg.norm(state) < 1e-6


@pytest.mark.parametrize("a,b,q,r,reason", [
    ([[1, 0], [0, 1]], [[0], [0]], [[1, 0], [0, 1]], [[1]], "stabilizable"),
    ([[1, 0], [0, .5]], [[1], [0]], [[0, 0], [0, 1]], [[1]], "detectable"),
    ([[1, .01], [0, 1]], [[0], [1]], [[-1, 0], [0, 1]], [[1]], "semidefinite"),
    ([[1, .01], [0, 1]], [[0], [1]], [[1, 0], [0, 1]], [[0]], "definite"),
])
def test_lqr_invalid_models(a,b,q,r,reason):
    with pytest.raises(ValueError, match=reason):
        Lqr_Solve(a,b,q,r,dt_s=.01)


def test_sdk_each_source_has_provenance_and_digest():
    identity = Sdk_Identity()
    assert identity["source_commit"]
    assert all(len(row["sha256"]) == 64 for row in identity["files"].values())


def test_lqr_boolean_matrix_rejected_and_caller_arrays_remain_mutable():
    with pytest.raises(ValueError,match="booleans"):
        Lqr_Solve([[True, 0], [0, .5]], [[1], [0]], [[1,0],[0,0]], [[1]], dt_s=.01)
    a = np.array([[.8,0.],[0.,.5]])
    Lqr_Solve(a,[[1],[0]],[[1,0],[0,0]],[[1]],dt_s=.01)
    assert a.flags.writeable


@pytest.mark.parametrize("kind", KINDS)
def test_nonidentity_launch_pose_is_valid_for_actual_precision_contract(kind):
    angle = .27
    q = (np.cos(angle/2),0,np.sin(angle/2),0)
    nav = Navigation(kind,initial_q_nb=q)
    body_gravity = (-9.80665*np.sin(angle),0,9.80665*np.cos(angle))
    for timestamp in range(0,1000001,10000):
        state = nav.Imu_Update(timestamp,body_gravity,(0,0,0))
    assert state.valid
    assert state.position_enu_m == pytest.approx((0,0,0),abs=3e-6)
    assert state.q_nb == pytest.approx(q,abs=1e-6)


@pytest.mark.parametrize("kind", ["sf6","kf6","eskf15"])
def test_barometer_uses_altitude_variance_and_rejects_duplicate(kind):
    nav = Navigation(kind)
    for timestamp in range(0,20001,10000):
        nav.Imu_Update(timestamp,(0,0,9.80665),(0,0,0))
    assert nav.Barometer_Update(20000,20000,1.,2.5) == AlgorithmResult.Ok
    assert nav.Snapshot_Get().position_enu_m[2] > 0
    assert nav.Barometer_Update(20000,20000,1.,2.5) == AlgorithmResult.Stale


@pytest.mark.parametrize("kind", ["eskf20","inekf20"])
def test_magnetic_sensor_frame_installation_and_strict_time(kind):
    # +90 deg sensor-to-body about Z: sensor vector is R_bs.T times Body field.
    nav = Navigation(kind,magnetic_rotation_bs_wxyz=(np.sqrt(.5),0,0,np.sqrt(.5)))
    for timestamp in range(0,20001,10000):
        nav.Imu_Update(timestamp,(0,0,9.80665),(0,0,0))
    assert nav.Magnetic_Update(10000,20000,(0,-20e-6,-40e-6)) == AlgorithmResult.Stale
    assert nav.Magnetic_Update(20000,20000,(0,-20e-6,-40e-6)) == AlgorithmResult.Ok
    assert nav.Snapshot_Get().q_nb == pytest.approx((1,0,0,0),abs=1e-6)
    assert nav.Magnetic_Update(20000,20000,(0,-20e-6,-40e-6)) == AlgorithmResult.Stale


def test_stopped_estimator_cannot_publish_valid_output_until_explicit_restart():
    nav=Navigation()
    for timestamp in (0,10000,20000):
        nav.Imu_Update(timestamp,(1,0,9.80665),(0,0,0))
    assert nav.Snapshot_Get().valid
    nav.Stop()
    assert not nav.Snapshot_Get().valid
    assert nav.Imu_Update(30000,(1,0,9.80665),(0,0,0)).result==AlgorithmResult.Stopped
    assert nav.Gnss_Update(30000,30000,(0,0,0),(0,0,0))==AlgorithmResult.Stopped
    nav.Start()
    assert not nav.Snapshot_Get().valid
    assert nav.Snapshot_Get().position_enu_m==(0,0,0)
