"""Research results and exact target scalar profiles are separate file members."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile

from jsonschema import Draft202012Validator

from .control import LqrController, PidController
from .native import Sdk_Path
from .navigation import Navigation


def _Profile_Build(folder: str, overrides: dict) -> dict:
    path = Sdk_Path() / folder / "plugin.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    definitions = manifest["algorithm_parameters"]["parameters"]
    if set(overrides) - {row["id"] for row in definitions}:
        raise ValueError("Unknown target parameter")
    parameters = []
    for row in definitions:
        value = overrides.get(row["id"], row["default"])
        # Retired settings preserve their saved lexical value. The strict v1
        # reader correctly forbids even cosmetic changes to read-only inputs.
        if row["type"] == "float" and row.get("lifecycle", "active") == "active":
            value = struct.unpack("<f", struct.pack("<f", value))[0]
        parameters.append({"id": row["id"], "value": value, "unit": row["unit"],
            "representation": row["representation"],
            "storage_type": "float32" if row["type"] == "float" else "int32"})
    return {"schema_id": "silverstar.function-parameters/1", "schema_version": 1,
        "plugin_id": manifest["id"], "plugin_version": manifest["version"],
        "manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "parameter_schema": "silverstar.algorithm-parameters/1.0",
        "value_source": "project_actual_input", "parameters": parameters}


def ControlResearch_Build(controller: PidController | LqrController | None) -> dict | None:
    if controller is None:
        return None
    if isinstance(controller, PidController):
        return {"schema_id": "silverstar.control-research/1", "kind": "pid", "deployable": False,
            "parameters": controller.parameters, "design": None}
    if not isinstance(controller, LqrController):
        raise ValueError("Unknown controller implementation")
    design = controller.design
    return {"schema_id": "silverstar.control-research/1", "kind": "lqr", "deployable": False,
        "parameters": {"k_angle": float(design.target_k[0, 0]),
            "k_rate": float(design.target_k[0, 1]), "output_limit": controller._config.output_limit},
        "design": {"a": design.a.tolist(), "b": design.b.tolist(), "q": design.q.tolist(),
            "r": design.r.tolist(), "k": design.target_k.tolist(), "dt_s": design.dt_s,
            "model_source": design.model_source, "state_order": ["angle_error_rad", "angular_rate_radps"],
            "input_order": ["actuator_command"], "storage_order": "row_major",
            "riccati_residual": design.residual, "closed_loop_radius": design.closed_loop_radius}}


def TuningBundle_Build(navigation: Navigation, controller: PidController | LqrController | None,
                       model_id: str, run_id: str) -> dict:
    """Build exact scalar target defaults plus the bindings actually tuned here.

    These are proposed target inputs, not a claim of full target-backend parity.
    No research control record is inserted into the old 128-item scalar schema.
    """
    if not model_id or not run_id or len(model_id) > 128 or len(run_id) > 128:
        raise ValueError("Model and run identities must be nonempty, at most 128 characters")
    profiles = []
    if navigation.kind in ("ins", "sf6", "kf6"):
        profiles.append(_Profile_Build("silverstar_algorithm_ins_coning2_sculling2",
                                     {"gravity_mps2": navigation.gravity_mps2}))
    if navigation.kind == "kf6":
        profiles.append(_Profile_Build("silverstar_algorithm_estimator_kf6",
                                     {"gravity_mps2": navigation.gravity_mps2}))
    result = {"schema_id": "silverstar.tuning-bundle/1", "schema_version": 1,
        "model_id": model_id, "run_id": run_id, "coordinates": "ENU; body+Z; Hamilton-wxyz; q_nb",
        "implementation_identity": navigation.implementation_identity, "profiles": profiles,
        "control_research": ControlResearch_Build(controller),
        "limitations": [
            "Control cores are research-only: target mission dispatch and actuator drivers are not connected.",
            "Scalar profiles propose pinned target defaults plus the simulated gravity binding; they do not certify full backend parity.",
            "KF6 host adapter uses current-state updates on arrival; no delayed replay is claimed.",
            "Non-INS/KF6 tuning is retained as research; no unverified firmware scalar profile is exported.",
            "Initial pose and zero launch velocity are explicit simulation priors; no sensor or hardware qualification is claimed.",
        ]}
    result["content_sha256"] = hashlib.sha256(json.dumps(result, sort_keys=True,
        ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    return result


def TuningBundle_Write(path: str | Path, value: dict) -> None:
    target = Path(path)
    schema = json.loads((Sdk_Path()/"tuning_bundle_v1.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(value)
    data = (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")
    if len(data) > 1048576:
        raise ValueError("Tuning bundle exceeds 1 MiB")
    payload = {key: item for key, item in value.items() if key != "content_sha256"}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    if value.get("content_sha256") != digest:
        raise ValueError("Tuning bundle content digest changed")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".tuning-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
