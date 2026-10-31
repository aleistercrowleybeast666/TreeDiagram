"""SI, Hamilton wxyz, active body-to-navigation rotations."""
from __future__ import annotations

import numpy as np


def Vector_Check(value, size: int, path: str) -> np.ndarray:
    if not isinstance(value, (list, tuple, np.ndarray)) or len(value) != size:
        raise ValueError(f"{path}: expected {size} numbers")
    if any(isinstance(v, (bool, np.bool_)) for v in value):
        raise ValueError(f"{path}: boolean is not a physical number")
    result = np.asarray(value, dtype=float)
    if result.shape != (size,) or not np.all(np.isfinite(result)):
        raise ValueError(f"{path}: expected finite vector")
    return result


def Quaternion_Normalize(q) -> np.ndarray:
    q = Vector_Check(q, 4, "quaternion")
    norm = np.linalg.norm(q)
    if norm < 1e-12:
        raise ValueError("degenerate quaternion")
    return q / norm


def Quaternion_Multiply(a, b) -> np.ndarray:
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return np.array([aw*bw-ax*bx-ay*by-az*bz, aw*bx+ax*bw+ay*bz-az*by,
                     aw*by-ax*bz+ay*bw+az*bx, aw*bz+ax*by-ay*bx+az*bw])


def Quaternion_Matrix(q) -> np.ndarray:
    w, x, y, z = Quaternion_Normalize(q)
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def Inertia_Check(value, path="inertia_kg_m2", allow_zero=False) -> np.ndarray:
    if not isinstance(value, (list, tuple, np.ndarray)) or len(value) != 3:
        raise ValueError(f"{path}: expected 3x3 tensor")
    tensor = np.array([Vector_Check(row, 3, path) for row in value])
    if not np.allclose(tensor, tensor.T, atol=1e-10):
        raise ValueError(f"{path}: tensor must be symmetric")
    eigen = np.linalg.eigvalsh(tensor)
    if min(eigen) < 0 or (not allow_zero and min(eigen) <= 0):
        raise ValueError(f"{path}: tensor must be positive {'semi-' if allow_zero else ''}definite")
    if eigen[2] > eigen[0] + eigen[1] + 1e-9:
        raise ValueError(f"{path}: principal moment triangle inequality violated")
    return tensor


def Inertia_Shift(mass: float, offset) -> np.ndarray:
    r = np.asarray(offset, dtype=float)
    return mass * (np.dot(r, r) * np.eye(3) - np.outer(r, r))
