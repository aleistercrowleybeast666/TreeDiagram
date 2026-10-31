"""Isolated old-physics vs current-test regression; never alter production files."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).resolve().parent
WORK = ROOT / ".test-tmp/actuator-fault-regression-20261101"
PHYSICS = "src/treediagram/physics.py"
TEST_FILE = "tests/test_physics.py"
TESTS = [
    TEST_FILE + "::test_plant_wheel_saturation_and_reversal_conserve_inertial_momentum",
    TEST_FILE + "::test_plant_rcs_exhaustion_respects_impulse_budget_and_rocket_equation",
]


def Git_Read(*arguments: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *arguments])


def Digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def Json_Write(name: str, value) -> None:
    (EVIDENCE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                                  encoding="utf-8", newline="\n")


def Child_Run(mode: str) -> int:
    sys.path.insert(0, str(ROOT / "src"))
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if mode == "before":
        import treediagram
        source = WORK / "before/physics.py"
        spec = importlib.util.spec_from_file_location("treediagram.physics", source)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        treediagram.physics = module
        original = module.Plant.Actuator_Evaluate

        def Actuator_ApiCompat(self, time_s, state, thrust, dynamic, cg, *, rcs_active=None):
            # The final test's extra force observer passes the new keyword as
            # None against old physics. Accept only that no-override spelling;
            # every old force, mass flow, RK stage and post-step clip is intact.
            if rcs_active is not None:
                raise ValueError("Old physics cannot accept an RCS mode override")
            return original(self, time_s, state, thrust, dynamic, cg)

        module.Plant.Actuator_Evaluate = Actuator_ApiCompat
        print("OLD PHYSICS:", source, "SHA256", Digest(source.read_bytes()), flush=True)
        print("API adapter: accept rcs_active=None only; scientific equations unmodified", flush=True)
    else:
        import treediagram.physics as module
        print("CURRENT PHYSICS:", module.__file__, "SHA256",
              Digest(Path(module.__file__).read_bytes()), flush=True)
    import pytest
    return pytest.main([
        *TESTS, "-vv", "--tb=long", "-p", "no:cacheprovider",
        "--basetemp=" + str(WORK / ("pytest-" + mode)),
        "--junitxml=" + str(EVIDENCE / (mode + ".junit.xml")),
    ])


def Main() -> None:
    for filename in ("before.log", "after.log", "provenance.json", "commands.json", "summary.json"):
        if (EVIDENCE / filename).exists():
            raise FileExistsError("Refusing to overwrite formal evidence: " + filename)
    WORK.mkdir(parents=True, exist_ok=False)
    (WORK / "before").mkdir()
    before_commit = Git_Read("rev-parse", "1983911").decode().strip()
    fix_commit = Git_Read("rev-parse", "440db63").decode().strip()
    parent_commit = Git_Read("rev-parse", fix_commit + "^").decode().strip()
    assert parent_commit == before_commit
    before = Git_Read("show", before_commit + ":" + PHYSICS)
    assert before == Git_Read("show", fix_commit + "^:" + PHYSICS)
    (WORK / "before/physics.py").write_bytes(before)
    current = (ROOT / PHYSICS).read_bytes()
    committed = Git_Read("show", fix_commit + ":" + PHYSICS)
    assert current.replace(b"\r\n", b"\n") == committed.replace(b"\r\n", b"\n")
    tests = (ROOT / TEST_FILE).read_bytes()
    Json_Write("provenance.json", {
        "before_commit": before_commit, "fix_commit": fix_commit,
        "head": Git_Read("rev-parse", "HEAD").decode().strip(),
        "extraction_commands": [
            ["git", "show", before_commit + ":" + PHYSICS],
            ["git", "show", fix_commit + "^:" + PHYSICS],
        ],
        "before_git_blob_sha256": Digest(before),
        "before_extracted_source_sha256": Digest((WORK / "before/physics.py").read_bytes()),
        "after_git_blob_sha256": Digest(committed), "after_runtime_source_sha256": Digest(current),
        "tests_path": TEST_FILE, "unchanged_final_tests_sha256": Digest(tests),
        "selected_tests": TESTS, "python": sys.version, "platform": platform.platform(),
        "scope": "historical physics module with final unchanged model/test environment, not a historical full-suite run",
        "compatibility_adapter": "before only: accept rcs_active=None and call the old method unchanged; reject non-None overrides",
        "hardware_validation": "not performed",
    })
    commands, summary = [], []
    for mode, expected in (("before", 1), ("after", 0)):
        command = [sys.executable, "-u", str(Path(__file__).resolve()), "--mode", mode]
        started = time.monotonic()
        result = subprocess.run(command, cwd=ROOT, capture_output=True)
        raw = result.stdout + result.stderr
        (EVIDENCE / (mode + ".log")).write_bytes(raw)
        commands.append({"mode": mode, "command": command, "cwd": str(ROOT),
                         "exit_code": result.returncode, "expected_exit_code": expected,
                         "seconds": time.monotonic()-started, "log_sha256": Digest(raw)})
        Json_Write("commands.json", commands)
        assert result.returncode == expected, mode + ": unexpected pytest exit code"
        suite = ET.parse(EVIDENCE / (mode + ".junit.xml")).getroot().find("testsuite")
        totals = {key: int(suite.attrib[key]) for key in ("tests", "failures", "errors", "skipped")}
        assert totals == {"tests": 5, "failures": 5 if mode == "before" else 0, "errors": 0, "skipped": 0}
        if mode == "before":
            assert b"TypeError" not in raw
            assert b"0.002736666666666679" in raw
            assert b"0.006461869855967078" in raw
        summary.append({"mode": mode, **totals, "exit_code": result.returncode,
                        "test_cases": [row.attrib["name"] for row in suite.findall("testcase")]})
        Json_Write("summary.json", summary)
        print(mode, totals, "exit", result.returncode, flush=True)
    assert (ROOT / PHYSICS).read_bytes() == current
    assert (ROOT / TEST_FILE).read_bytes() == tests


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("before", "after"))
    args = parser.parse_args()
    if args.mode:
        raise SystemExit(Child_Run(args.mode))
    Main()
