"""Offline build/loading of pinned, unmodified SilverStar mathematical sources."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading

import numpy
import scipy


class AlgorithmBuildError(RuntimeError):
    """The actual C implementation could not be built; there is no Python fallback."""


def Sdk_Path() -> Path:
    """Find the installed resource first, then the editable checkout."""
    here = Path(__file__).resolve()
    candidates = [here.parent / "sdk", here.parents[3] / "vendor/silverstar"]
    for candidate in candidates:
        if (candidate / "manifest.json").is_file():
            return candidate
    raise AlgorithmBuildError("SilverStar SDK missing; install the complete TreeDiagram package")


def Sdk_Identity() -> dict:
    path = Sdk_Path()
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    for name, entry in manifest["files"].items():
        resolved = (path / name).resolve()
        if not resolved.is_relative_to(path.resolve()):
            raise AlgorithmBuildError("SDK manifest contains an escaping path")
        if hashlib.sha256(resolved.read_bytes()).hexdigest() != entry["sha256"]:
            raise AlgorithmBuildError(f"SDK source identity mismatch: {name}")
    return manifest


def Native_Load() -> ctypes.CDLL:
    """Bind native code and offline numerical runtime; each caller owns C state."""
    sdk = Sdk_Path()
    manifest = Sdk_Identity()
    compiler = shutil.which(os.environ.get("CC", "gcc"))
    if compiler is None:
        raise AlgorithmBuildError("C compiler unavailable: install GCC or set CC; no reference fallback")
    native = Path(__file__).with_name("native")
    sources = sorted(sdk.glob("*/*.c")) + sorted(native.glob("*.c"))
    flags = ["-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-shared"]
    if os.name == "nt":
        flags.append("-static-libgcc")
    else:
        flags.append("-fPIC")
    version = subprocess.check_output([compiler, "--version"], text=True, timeout=15)
    identity = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode())
    for source in sorted(native.iterdir()):
        if source.is_file():
            identity.update(source.name.encode() + source.read_bytes())
    wrapper_hashes = {
        name: hashlib.sha256(native.parent.joinpath(name).read_bytes()).hexdigest()
        for name in ("native.py", "navigation.py", "control.py")
    }
    numerical_runtime = {"python": sys.version, "numpy": numpy.__version__,
                         "scipy": scipy.__version__}
    identity.update(json.dumps({"compiler": compiler, "compiler_version": version,
        "flags": flags, "wrapper_hashes": wrapper_hashes,
        "numerical_runtime": numerical_runtime}, sort_keys=True).encode())
    cache = Path(os.environ.get("TREEDIAGRAM_CACHE", str(Path.home() / ".cache/treediagram")))
    build = cache / "algorithms" / identity.hexdigest()
    build.mkdir(parents=True, exist_ok=True)
    library = build / ("silverstar.dll" if os.name == "nt" else "silverstar.so")
    if not library.exists():
        includes = [native, sdk, *sorted(p for p in sdk.iterdir() if p.is_dir())]
        temporary = build / f".{os.getpid()}-{threading.get_ident()}{library.suffix}"
        command = [compiler, *flags, *(f"-I{p}" for p in includes),
                   *(str(p) for p in sources), "-lm", "-o", str(temporary)]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=120)
        (build / "build.json").write_text(json.dumps({"command": command,
            "compiler_version": version, "returncode": completed.returncode,
            "wrapper_hashes": wrapper_hashes, "numerical_runtime": numerical_runtime,
            "stdout": completed.stdout, "stderr": completed.stderr}, indent=2), encoding="utf-8")
        if completed.returncode:
            temporary.unlink(missing_ok=True)
            raise AlgorithmBuildError(f"C SDK compilation failed:\n{completed.stderr}")
        try:
            os.replace(temporary, library)
        except PermissionError:
            # Another caller may have published/loaded identical content meanwhile.
            if not library.exists():
                raise
            temporary.unlink(missing_ok=True)
    result = ctypes.CDLL(str(library))
    result._treediagram_identity = identity.hexdigest()
    return result
