"""Bounded C control laws and offline, verified standard discrete LQR design."""
from __future__ import annotations

import ctypes as ct
from dataclasses import dataclass
from enum import IntEnum
import math
from typing import Sequence

import numpy as np
from scipy.linalg import solve_discrete_are

from .native import Native_Load


class ControlResult(IntEnum):
    Ok = 0
    Invalid = 1
    Stopped = 2
    NumericError = 3


class ControlError(ValueError):
    def __init__(self, result: ControlResult, detail: str):
        self.result = result
        super().__init__(detail)


class _PidConfig(ct.Structure):
    _fields_ = [(name, ct.c_float) for name in ("kp", "ki", "kd", "derivative_tau_s",
                "integral_limit", "output_limit", "sample_period_s")]


class _PidContext(ct.Structure):
    _fields_ = [(name, ct.c_float) for name in ("integral", "previous_measurement", "derivative")]
    _fields_ += [("started", ct.c_uint8), ("has_previous", ct.c_uint8)]


class PidController:
    def __init__(self, kp: float = 2.0, ki: float = 0.2, kd: float = 0.1,
                 derivative_tau_s: float = 0.02, integral_limit: float = 0.2,
                 output_limit: float = 0.3, sample_period_s: float = 0.01):
        values = (kp, ki, kd, derivative_tau_s, integral_limit, output_limit, sample_period_s)
        if any(isinstance(v, bool) or not math.isfinite(v) for v in values):
            raise ValueError("PID parameters must be finite numbers")
        self._library = Native_Load()
        self._config = _PidConfig(*values)
        self._context = _PidContext()
        library = self._library
        library.ControlPid_Start.argtypes = [ct.POINTER(_PidContext), ct.POINTER(_PidConfig)]
        library.ControlPid_Stop.argtypes = [ct.POINTER(_PidContext)]
        library.ControlPid_Step.argtypes = [ct.POINTER(_PidContext), ct.POINTER(_PidConfig),
            ct.c_float, ct.c_float, ct.c_float, ct.POINTER(ct.c_float)]
        self.implementation_identity = library._treediagram_identity
        self.last_result = ControlResult.Ok
        self.Reset()

    @property
    def parameters(self) -> dict[str, float]:
        return {name: getattr(self._config, name) for name, _ in _PidConfig._fields_}

    @property
    def integral(self) -> float:
        return self._context.integral

    def Reset(self) -> None:
        result = ControlResult(self._library.ControlPid_Start(ct.byref(self._context), ct.byref(self._config)))
        if result != ControlResult.Ok:
            raise ControlError(result, "Invalid PID configuration")
        self.last_result = result

    def Stop(self) -> None:
        self.last_result = ControlResult(self._library.ControlPid_Stop(ct.byref(self._context)))

    def Step(self, reference: float, measured: float, dt_s: float) -> float:
        output = ct.c_float()
        result = ControlResult(self._library.ControlPid_Step(ct.byref(self._context),
            ct.byref(self._config), reference, measured, dt_s, ct.byref(output)))
        self.last_result = result
        if result != ControlResult.Ok:
            raise ControlError(result, f"PID output invalid ({result.name}); safe output is zero")
        return output.value


@dataclass(frozen=True)
class LqrDesign:
    a: np.ndarray
    b: np.ndarray
    q: np.ndarray
    r: np.ndarray
    p: np.ndarray
    k: np.ndarray
    target_k: np.ndarray
    residual: float
    closed_loop_radius: float
    dt_s: float
    model_source: str


def Lqr_Solve(a: Sequence, b: Sequence, q: Sequence, r: Sequence, *, dt_s: float,
              model_source: str = "explicit user small-angle linearization") -> LqrDesign:
    """Standard DARE, PSD Q, PD R, PBH stabilizability/detectability, float32 K."""
    for value in (a, b, q, r):
        if any(isinstance(item, (bool, np.bool_)) for item in np.asarray(value, dtype=object).flat):
            raise ValueError("LQR matrix entries must be numbers, not booleans")
    matrices = [np.array(value, dtype=float, copy=True) for value in (a, b, q, r)]
    a, b, q, r = matrices
    if [value.shape for value in matrices] != [(2, 2), (2, 1), (2, 2), (1, 1)]:
        raise ValueError("LQR core requires A(2,2), B(2,1), Q(2,2), R(1,1)")
    if any(not np.isfinite(value).all() for value in matrices) or isinstance(dt_s, bool) or not math.isfinite(dt_s) or dt_s <= 0:
        raise ValueError("LQR matrices and positive sample period must be finite")
    if not model_source.strip():
        raise ValueError("LQR model source must be declared")
    if not np.allclose(q, q.T, atol=1e-12, rtol=1e-12) or not np.allclose(r, r.T, atol=1e-12, rtol=1e-12):
        raise ValueError("LQR Q and R must be symmetric")
    eigenvalues, eigenvectors = np.linalg.eigh(q)
    if eigenvalues.min() < -1e-12 or np.linalg.eigvalsh(r).min() <= 0:
        raise ValueError("LQR requires positive semidefinite Q and positive definite R")
    c = np.diag(np.sqrt(np.maximum(eigenvalues, 0))) @ eigenvectors.T
    for eigenvalue in np.linalg.eigvals(a):
        if abs(eigenvalue) >= 1 - 1e-10:
            shift = eigenvalue * np.eye(2) - a
            if np.linalg.matrix_rank(np.concatenate((shift, b), axis=1)) != 2:
                raise ValueError("LQR pair (A,B) is not stabilizable")
            if np.linalg.matrix_rank(np.concatenate((shift, c), axis=0)) != 2:
                raise ValueError("LQR pair (sqrt(Q),A) is not detectable")
    try:
        p = solve_discrete_are(a, b, q, r)
        denominator = r + b.T @ p @ b
        if np.linalg.cond(denominator) > 1e10:
            raise ValueError("Ill-conditioned LQR input solve")
        k = np.linalg.solve(denominator, b.T @ p @ a)
    except np.linalg.LinAlgError as error:
        raise ValueError(f"No stable LQR solution: {error}") from error
    residual = np.linalg.norm(a.T @ p @ a - p - a.T @ p @ b @ k + q) / max(1., np.linalg.norm(p))
    with np.errstate(over="ignore", invalid="ignore"):
        target_k = k.astype(np.float32).astype(float)
    if not np.isfinite(target_k).all() or not math.isfinite(residual) or residual > 1e-8:
        raise ValueError("LQR target precision or Riccati residual failed")
    radius = float(max(abs(np.linalg.eigvals(a - b @ target_k))))
    if radius >= 1 - 1e-10 or not np.isfinite(p).all() or np.linalg.eigvalsh(p).min() < -1e-10:
        raise ValueError("Target float32 gain does not produce a strictly stable closed loop")
    for value in (*matrices, p, k, target_k):
        value.setflags(write=False)
    return LqrDesign(a, b, q, r, p, k, target_k, float(residual), radius, float(dt_s), model_source)


class _LqrConfig(ct.Structure):
    _fields_ = [("gain", ct.c_float * 2), ("output_limit", ct.c_float)]


class LqrController:
    def __init__(self, design: LqrDesign | None = None, output_limit: float = 0.3,
                 sample_period_s: float = 0.01, inertia_kg_m2: float = 0.1,
                 input_torque_nm: float = 1.0, dt_s: float | None = None,
                 q_angle: float = 10.0, q_rate: float = 1.0, r: float = 1.0):
        if isinstance(output_limit, bool) or not math.isfinite(ct.c_float(output_limit).value) or output_limit <= 0:
            raise ValueError("LQR output limit must be finite and positive")
        if design is None:
            if not math.isfinite(inertia_kg_m2) or inertia_kg_m2 <= 0 or not math.isfinite(input_torque_nm) or input_torque_nm == 0:
                raise ValueError("LQR linearization requires inertia and nonzero input authority")
            dt = sample_period_s if dt_s is None else dt_s
            authority = input_torque_nm / inertia_kg_m2
            design = Lqr_Solve([[1, dt], [0, 1]], [[0.5 * dt**2 * authority], [dt * authority]],
                [[q_angle, 0.], [0., q_rate]], [[r]], dt_s=dt,
                model_source="single rigid-body axis, small angle, constant specified inertia/torque authority")
        self.design = design
        self._library = Native_Load()
        self._config = _LqrConfig((ct.c_float * 2)(*design.target_k.ravel()), output_limit)
        self._library.ControlLqr_Step.argtypes = [ct.POINTER(_LqrConfig), ct.POINTER(ct.c_float), ct.POINTER(ct.c_float)]
        self.implementation_identity = self._library._treediagram_identity
        self._started = True

    def Stop(self) -> None:
        self._started = False

    def Reset(self) -> None:
        self._started = True

    def Step(self, state_error: Sequence[float]) -> float:
        if not self._started:
            raise ControlError(ControlResult.Stopped, "LQR stopped; safe output is zero")
        if len(state_error) != 2:
            raise ValueError("LQR error must be [angle_error_rad, angular_rate_radps]")
        output = ct.c_float()
        result = self._library.ControlLqr_Step(ct.byref(self._config),
            (ct.c_float * 2)(*state_error), ct.byref(output))
        if result:
            raise ControlError(ControlResult.Invalid if result == 1 else ControlResult.NumericError,
                               "LQR invalid input or arithmetic; safe output is zero")
        return output.value
