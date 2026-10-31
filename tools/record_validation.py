"""Record auditable local source and generated validation artifacts; never delete."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import zipfile


def Digest_Read(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def Report_Write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def Main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    evidence = root / "docs/evidence/20261101"
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    sources = {}
    for folder in ("src", "tests", "examples", "contracts", "tools"):
        for path in sorted((root / folder).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts and ".egg-info" not in str(path):
                sources[path.relative_to(root).as_posix()] = Digest_Read(path)
    for name in ("pyproject.toml", "requirements-tested.txt", ".gitattributes"):
        sources[name] = Digest_Read(root / name)
    Report_Write(evidence / f"source-snapshot-{args.revision}.json", {
        "head": head, "revision_label": args.revision, "python": platform.python_version(),
        "platform": platform.platform(), "packages": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "scipy", "PySide6", "jsonschema", "defusedxml", "pytest", "setuptools")},
        "compiler": subprocess.check_output(["gcc", "--version"], text=True),
        "sources": sources, "identity_scope": "Exact working bytes; Git SHA alone does not replace these hashes."})
    wheel = root / f".qa/20261101/wheel-{args.revision}/treediagram_workbench-0.1.0-py3-none-any.whl"
    matches = {}
    with zipfile.ZipFile(wheel) as archive:
        for path in sorted((root / "src/treediagram").rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                name = path.relative_to(root / "src").as_posix()
                matches[name] = hashlib.sha256(archive.read(name)).hexdigest() == Digest_Read(path)
    if not all(matches.values()):
        raise RuntimeError("wheel source mismatch: " + str([name for name, ok in matches.items() if not ok]))
    Report_Write(evidence / f"packaging-{args.revision}.json", {
        "source_head": head, "wheel_sha256": Digest_Read(wheel), "source_files": matches,
        "smoke_exit": int((evidence / f"wheel-smoke-{args.revision}.exit.txt").read_text().strip()),
        "scope": "Installed wheel, isolated Python, actual bundled C SDK; existing dependencies, not a new OS installation."})
    inventory = []
    for path in sorted((root / ".qa/20261101").rglob("*")):
        if path.is_file():
            inventory.append({"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size,
                "sha256": Digest_Read(path), "owner": "TreeDiagram 20261101 implementation task",
                "purpose": "Generated simulation, GUI save/export, isolated wheel installation or compiler smoke output",
                "retained_evidence": "docs/evidence/20261101; no deletion performed"})
    Report_Write(evidence / "generated-task-inventory.json", inventory)
    print(f"{len(sources)} source hashes; {len(matches)} wheel source matches; {len(inventory)} generated files retained")


if __name__ == "__main__":
    Main()
