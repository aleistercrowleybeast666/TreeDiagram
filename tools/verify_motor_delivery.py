"""Exercise a newly exported motor through the real desktop and CLI consumers.

The supplied package is read-only. Generated cases are explicitly synthetic.
Qt offscreen coverage does not claim a native desktop or hardware test.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QPushButton

from treediagram.core.storage import ProjectIoResult, Project_Load, Project_Save
from treediagram.design import Design_CreateExample, Design_Decode, Design_Digest, Design_Validate
from treediagram.importers import Motor_Import
from treediagram.io import Json_Read, Json_Write, Json_Digest
from treediagram.results import Run_Save
from treediagram.ui import MainWindow
from treediagram.vendor_motor.contract import MotorPackage_Digest, MotorPackage_Load


def Digest_Get(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def Main():
    parser = argparse.ArgumentParser()
    parser.add_argument("motor", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = args.motor.resolve()
    source_hash = Digest_Get(source)
    package = MotorPackage_Load(source)
    commands = []

    def cli(*arguments, expected=0):
        command = [sys.executable, "-m", "treediagram", *map(str, arguments)]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=180,
                                env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        commands.append({"command": command, "exit": result.returncode,
                         "stdout": result.stdout, "stderr": result.stderr})
        assert result.returncode == expected, commands[-1]
        return result.stdout

    base = Design_CreateExample("pid")
    base = replace(base, name="20261110 new Underline package / synthetic integration",
                   control=replace(base.control, period_us=10000, kp=1.75),
                   scenario=replace(base.scenario, gravity_mps2=9.78),
                   motor=replace(base.motor, position_m=(.01, 0., -.43), ignition_s=.05))
    Json_Write(output / "base.json", asdict(base))
    cli("import-motor", output / "base.json", source, output / "imported.json")
    cli("check", output / "imported.json")
    imported = Design_Decode(Json_Read(output / "imported.json"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    window.workbench.Design_Commit(base)
    window.navigation.setCurrentRow(1)
    app.processEvents()
    import_button = next(item for item in window.workbench.model_page.findChildren(QPushButton)
                         if item.text() == "导入发动机…")

    def gui_import(path, answer=QMessageBox.StandardButton.Yes):
        errors = []
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "")), \
                patch.object(QMessageBox, "question", return_value=answer), \
                patch.object(window, "_Error_Show", side_effect=errors.append):
            import_button.click()
        return errors

    before = window.session.project
    assert not gui_import(source, QMessageBox.StandardButton.No)
    assert window.session.project == before
    assert not gui_import(source)
    assert Design_Digest(window.workbench.design) == Design_Digest(imported)
    before = window.session.project
    assert not gui_import(source)
    assert window.session.project == before
    again, changes = Motor_Import(source, imported)
    assert Design_Digest(again) == Design_Digest(imported) and changes == ()

    preserved = ("position_m", "rotation_bm_wxyz", "ignition_s", "mass_model", "gimbal_capable")
    updated = copy.deepcopy(package)
    updated["motor"]["total_mass_kg"] += .01
    updated["content_sha256"] = MotorPackage_Digest(updated)
    Json_Write(output / "synthetic-update.tdmotor.json", updated)
    assert not gui_import(output / "synthetic-update.tdmotor.json")
    assert all(Json_Digest(getattr(window.workbench.design.motor, key)) == Json_Digest(getattr(base.motor, key))
               for key in preserved)
    assert not gui_import(source)

    rejected = {}
    for case in ("version", "digest"):
        bad = copy.deepcopy(package)
        if case == "version":
            bad["schema_version"] = 999
        else:
            bad["content_sha256"] = "0" * 64
        path = output / ("invalid-" + case + ".tdmotor.json")
        Json_Write(path, bad)
        before = window.session.project
        errors = gui_import(path)
        assert len(errors) == 1 and window.session.project == before
        text = cli("import-motor", output / "base.json", path,
                   output / ("rejected-" + case + ".json"), expected=2)
        assert errors[0] in text
        assert not (output / ("rejected-" + case + ".json")).exists()
        rejected[case] = errors[0]

    missing = copy.deepcopy(package)
    missing["motor"]["total_mass_kg"] = None
    missing["content_sha256"] = MotorPackage_Digest(missing)
    Json_Write(output / "missing-mass.tdmotor.json", missing)
    assert not gui_import(output / "missing-mass.tdmotor.json")
    assert not window.workbench.run_button.isEnabled()
    issues = Design_Validate(window.workbench.design, False)
    assert any("dry_mass_kg" in issue for issue in issues)
    cli("import-motor", output / "base.json", output / "missing-mass.tdmotor.json",
        output / "missing-model.json")
    diagnostic = json.loads(cli("check", output / "missing-model.json", expected=2))
    assert diagnostic["issues"] == list(issues)
    assert not gui_import(source)

    window.navigation.setCurrentRow(2)
    window.workbench.run_button.click()
    deadline = time.monotonic() + 180
    while window.workbench.busy and time.monotonic() < deadline:
        app.processEvents()
        threading.Event().wait(.01)
    assert not window.workbench.busy, "background run timed out"
    assert len(window.session.project.flight_runs) == 1, window.workbench.run_status.text()
    run = window.session.project.flight_runs[0]
    Run_Save(output / "completed.tdrun.json", run)
    assert run["input_digest"] == Design_Digest(imported)
    assert np.isclose(run["summary"]["total_impulse_ns"], package["metrics"]["total_impulse_ns"])

    # Editing after completion must not alter the export's model or target gravity.
    current = replace(window.workbench.design,
                      scenario=replace(window.workbench.design.scenario, gravity_mps2=9.81))
    window.workbench.Design_Commit(current)
    assert "历史配置" in window.workbench.result_info.text()
    with patch.object(QFileDialog, "getSaveFileName", return_value=(str(output / "run.sstuning.json"), "")):
        window.workbench.parameter_export_button.click()
    bundle = Json_Read(output / "run.sstuning.json")
    assert bundle["run_id"] == run["run_id"] and bundle["model_id"] == run["input_digest"]
    for profile in bundle["profiles"]:
        assert np.isclose(next(row["value"] for row in profile["parameters"]
                               if row["id"] == "gravity_mps2"), 9.78)
    assert bundle["control_research"]["deployable"] is False
    cli("export-parameters", output / "completed.tdrun.json", output / "cli.sstuning.json")
    assert (output / "cli.sstuning.json").read_bytes() == (output / "run.sstuning.json").read_bytes()
    target = output / "CurrentAndHistorical.tdproj"
    assert Project_Save(window.session.project, target).result == ProjectIoResult.Success
    restored = Project_Load(target)
    assert restored.result == ProjectIoResult.Success and restored.project == window.session.project
    window.session.dirty = False
    window.close()
    assert Digest_Get(source) == source_hash
    receipt = {"source_path": str(source), "source_sha256": source_hash,
               "scope": "Synthetic source; real CLI and Qt offscreen button consumers, not native desktop or hardware",
               "source_unchanged": True, "run_id": run["run_id"],
               "input_digest": run["input_digest"], "algorithm_identity": run["algorithm_identity"],
               "summary": run["summary"], "rejected": rejected,
               "readiness_issues": list(issues), "commands": commands,
               "files": {path.name: {"bytes": path.stat().st_size, "sha256": Digest_Get(path)}
                         for path in sorted(output.iterdir()) if path.is_file()}}
    Json_Write(output / "receipt.json", receipt)
    print(json.dumps({"run_id": run["run_id"], "summary": run["summary"],
                      "tuning_sha256": Digest_Get(output / "run.sstuning.json")}, indent=2))


if __name__ == "__main__":
    Main()
