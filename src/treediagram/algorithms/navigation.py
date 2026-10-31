"""Context-isolated actual C estimators, with explicit timing/precision limits."""
from __future__ import annotations

import ctypes as ct
from dataclasses import dataclass
from enum import IntEnum
import math
from typing import Sequence

from .native import Native_Load


class AlgorithmResult(IntEnum):
    Ok = 0
    Waiting = 1
    Invalid = 2
    Stale = 3
    Rejected = 4
    NumericError = 5
    Unsupported = 6
    Stopped = 7


KINDS = ("ins", "sf6", "kf6", "eskf15", "eskf20", "inekf15", "inekf20")


@dataclass(frozen=True)
class Estimate:
    timestamp_us: int
    position_enu_m: tuple[float, float, float]
    velocity_enu_mps: tuple[float, float, float]
    q_nb: tuple[float, float, float, float]
    omega_b_radps: tuple[float, float, float]
    valid: bool
    result: AlgorithmResult
    health: str


def _Vector_Require(values: Sequence[float], size: int) -> ct.Array:
    if len(values) != size or any(isinstance(v, bool) or not math.isfinite(v) for v in values):
        raise ValueError(f"Expected {size} finite numbers")
    return (ct.c_double * size)(*values)


class Navigation:
    """Actual SilverStar C math, explicit launch pose and zero launch p/v prior.

    INS/KF6/SF6 attitude comes from INS propagation, never a KF6 attitude output.
    KF6 uses its current-state update mode: delayed observations apply on arrival
    with their actual age retained in diagnostics, not a claim of delayed replay.
    ESKF/Invariant kernels accept only co-timed observations in this adapter.
    """

    def __init__(self, kind: str = "kf6", initial_q_nb: Sequence[float] = (1, 0, 0, 0),
                 gravity_mps2: float = 9.80665,
                 magnetic_reference_n_uT: Sequence[float] = (20, 0, -40),
                 magnetic_rotation_bs_wxyz: Sequence[float] = (1, 0, 0, 0)):
        if kind not in KINDS:
            raise ValueError(f"Unknown estimator: {kind}")
        self.kind = kind
        self.gravity_mps2 = float(ct.c_float(gravity_mps2).value)
        self._library = Native_Load()
        self.implementation_identity = self._library._treediagram_identity
        library = self._library
        ptr = ct.POINTER(ct.c_double)
        library.HostNavigation_ContextSize.restype = ct.c_size_t
        library.HostNavigation_Init.argtypes = [ct.c_void_p, ct.c_int, ptr, ct.c_double]
        library.HostNavigation_Imu.argtypes = [ct.c_void_p, ct.c_uint64, ptr, ptr, ptr]
        library.HostNavigation_Gnss.argtypes = [ct.c_void_p, ct.c_uint64, ct.c_uint64, ptr, ptr, ptr, ptr]
        library.HostNavigation_Snapshot.argtypes = [ct.c_void_p, ptr]
        library.HostNavigation_MagneticPriorSet.argtypes = [ct.c_void_p, ptr, ptr]
        library.HostNavigation_Magnetic.argtypes = [ct.c_void_p, ct.c_uint64, ct.c_uint64, ptr, ct.c_double]
        library.HostNavigation_Barometer.argtypes = [ct.c_void_p, ct.c_uint64, ct.c_uint64, ct.c_double, ct.c_double]
        self._memory = (ct.c_uint64 * ((library.HostNavigation_ContextSize() + 7) // 8))()
        self._output = (ct.c_double * 13)()
        self._timestamp = 0
        self._ready = False
        self._active = True
        self._initial_q = tuple(initial_q_nb)
        self._magnetic_reference = tuple(magnetic_reference_n_uT)
        self._magnetic_rotation = tuple(magnetic_rotation_bs_wxyz)
        self.last_gnss_diagnostic: dict = {}
        self.Reset()

    def Reset(self) -> None:
        """Explicit new state with the same declared launch prior and implementation."""
        result = self._library.HostNavigation_Init(self._memory, KINDS.index(self.kind),
            _Vector_Require(self._initial_q, 4), self.gravity_mps2)
        if result:
            raise ValueError("Invalid navigation initialization")
        result = self._library.HostNavigation_MagneticPriorSet(self._memory,
            _Vector_Require(self._magnetic_reference, 3), _Vector_Require(self._magnetic_rotation, 4))
        if result:
            raise ValueError("Invalid explicit magnetic reference/installation prior")
        self._library.HostNavigation_Snapshot(self._memory,self._output)
        self._timestamp=0
        self._ready=False
        self._active=True
        self.last_gnss_diagnostic={}

    def Start(self) -> None:
        self.Reset()

    def Stop(self) -> None:
        self._active=False

    def _Estimate_Get(self, result: AlgorithmResult) -> Estimate:
        values = tuple(self._output)
        return Estimate(self._timestamp, values[:3], values[3:6], values[6:10], values[10:13],
                        self._active and self._ready and result in (AlgorithmResult.Ok, AlgorithmResult.Waiting),
                        result, "simulated source; explicit launch prior; " + result.name)

    def Imu_Update(self, timestamp_us: int, specific_force_b: Sequence[float],
                   gyro_b: Sequence[float]) -> Estimate:
        if not self._active:
            return self._Estimate_Get(AlgorithmResult.Stopped)
        if type(timestamp_us) is not int or not 0 <= timestamp_us < 2**63:
            raise ValueError("timestamp_us must be a nonnegative bounded integer")
        result = AlgorithmResult(self._library.HostNavigation_Imu(self._memory, timestamp_us,
            _Vector_Require(specific_force_b, 3), _Vector_Require(gyro_b, 3), self._output))
        if result in (AlgorithmResult.Ok, AlgorithmResult.Waiting):
            self._timestamp = timestamp_us
        if result == AlgorithmResult.Ok:
            self._ready = True
        return self._Estimate_Get(result)

    def Gnss_Update(self, measurement_us: int, arrival_us: int,
                    position_enu_m: Sequence[float], velocity_enu_mps: Sequence[float],
                    position_std_m: Sequence[float] = (1.5, 1.5, 2.5),
                    velocity_std_mps: Sequence[float] = (0.15, 0.15, 0.25)) -> AlgorithmResult:
        if not self._active:
            return AlgorithmResult.Stopped
        if any(type(t) is not int or not 0 <= t < 2**63 for t in (measurement_us, arrival_us)):
            raise ValueError("GNSS timestamps must be nonnegative bounded integers")
        result = AlgorithmResult(self._library.HostNavigation_Gnss(self._memory,
            measurement_us, arrival_us, _Vector_Require(position_enu_m, 3),
            _Vector_Require(velocity_enu_mps, 3), _Vector_Require(position_std_m, 3),
            _Vector_Require(velocity_std_mps, 3)))
        self.last_gnss_diagnostic = {"measurement_us": measurement_us, "arrival_us": arrival_us,
            "age_us": arrival_us - measurement_us, "result": result.name,
            "timing": "current_state_on_arrival" if self.kind in ("sf6", "kf6") else "strict_co_timed"}
        self._library.HostNavigation_Snapshot(self._memory, self._output)
        return result

    def Snapshot_Get(self) -> Estimate:
        if not self._active:
            return self._Estimate_Get(AlgorithmResult.Stopped)
        result = AlgorithmResult(self._library.HostNavigation_Snapshot(self._memory, self._output))
        return self._Estimate_Get(result)

    def Barometer_Update(self, measurement_us: int, arrival_us: int,
                          altitude_up_m: float, std_m: float = 2.5) -> AlgorithmResult:
        if not self._active:
            return AlgorithmResult.Stopped
        if any(type(t) is not int or not 0 <= t < 2**63 for t in (measurement_us, arrival_us)):
            raise ValueError("Barometer timestamps must be nonnegative bounded integers")
        result = AlgorithmResult(self._library.HostNavigation_Barometer(self._memory,
            measurement_us, arrival_us, altitude_up_m, std_m))
        self._library.HostNavigation_Snapshot(self._memory, self._output)
        return result

    def Magnetic_Update(self, measurement_us: int, arrival_us: int,
                         field_sensor_t: Sequence[float], std_t: float = 0.05e-6) -> AlgorithmResult:
        """Simulated calibrated sensor-frame field; declared mounting applied once."""
        if not self._active:
            return AlgorithmResult.Stopped
        if any(type(t) is not int or not 0 <= t < 2**63 for t in (measurement_us, arrival_us)):
            raise ValueError("Magnetic timestamps must be nonnegative bounded integers")
        result = AlgorithmResult(self._library.HostNavigation_Magnetic(self._memory,
            measurement_us, arrival_us, _Vector_Require(field_sensor_t, 3), std_t))
        self._library.HostNavigation_Snapshot(self._memory, self._output)
        return result
