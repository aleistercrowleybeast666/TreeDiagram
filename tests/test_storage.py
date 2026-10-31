import json
from dataclasses import replace

import pytest

from treediagram.core import storage
from treediagram.core.model import Project_Create
from treediagram.core.session import ProjectSession
from treediagram.core.storage import ProjectIoResult, Project_Load, Project_Save


def test_roundtrip_has_version_no_machine_paths_and_backup(tmp_path):
    path = tmp_path / "中文工程.tdproj"
    project = replace(Project_Create(), name="界面试用", description="仅保存名称与备注")
    saved = Project_Save(project, path)
    assert saved.result == ProjectIoResult.Success
    raw = path.read_bytes()
    document = json.loads(raw)
    assert document["schema_version"] == 1
    assert document["project"]["dataset"]["values"] == []
    assert str(tmp_path) not in raw.decode("utf-8")
    assert Project_Load(path).project == project
    second = replace(project, description="已修改")
    assert Project_Save(second, path, saved.digest).result == ProjectIoResult.Success
    assert path.with_name(path.name + ".bak").read_bytes() == raw
    assert Project_Load(path).project == second


@pytest.mark.parametrize("damage", ["syntax", "future", "unknown", "duplicate", "nan"])
def test_bad_open_preserves_current_session(tmp_path, damage):
    session = ProjectSession()
    session.Project_Set(replace(session.project, name="当前未保存工程"))
    before = (session.project, session.path, session.digest, session.dirty)
    path = tmp_path / "bad.tdproj"
    Project_Save(Project_Create(), path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if damage == "syntax":
        content = "{broken"
    elif damage == "future":
        data["schema_version"] = 999
        content = json.dumps(data)
    elif damage == "unknown":
        data["project"]["future_data"] = [1, 2]
        content = json.dumps(data)
    elif damage == "duplicate":
        content = path.read_text(encoding="utf-8").replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1')
    else:
        data["project"]["dataset"]["values"] = [float("nan")]
        content = json.dumps(data)
    path.write_text(content, encoding="utf-8")
    assert session.Project_Open(path).result != ProjectIoResult.Success
    assert (session.project, session.path, session.digest, session.dirty) == before
    assert path.read_text(encoding="utf-8") == content


def test_external_edit_and_existing_file_refuse_overwrite(tmp_path):
    path = tmp_path / "shared.tdproj"
    project = Project_Create()
    first = Project_Save(project, path)
    assert Project_Save(project, path).result == ProjectIoResult.Conflict
    external = replace(project, name="外部修改")
    assert Project_Save(external, path, first.digest).result == ProjectIoResult.Success
    current = path.read_bytes()
    assert Project_Save(project, path, first.digest).result == ProjectIoResult.Conflict
    assert path.read_bytes() == current


def test_failed_atomic_replace_keeps_good_file_and_dirty_state(tmp_path, monkeypatch):
    path = tmp_path / "safe.tdproj"
    session = ProjectSession()
    assert session.Project_Save(path).result == ProjectIoResult.Success
    original, digest = path.read_bytes(), session.digest
    session.Project_Set(replace(session.project, name="未落盘的修改"))
    real_replace = storage.os.replace

    def fail_primary(source, destination):
        if destination == path:
            raise PermissionError("模拟文件被占用")
        return real_replace(source, destination)

    monkeypatch.setattr(storage.os, "replace", fail_primary)
    assert session.Project_Save().result == ProjectIoResult.IoError
    assert path.read_bytes() == original
    assert session.dirty and session.digest == digest
    assert not list(tmp_path.glob("*.lock"))
    assert not list(tmp_path.glob("*.tmp"))


def test_validation_failure_does_not_touch_existing_file(tmp_path):
    path = tmp_path / "valid.tdproj"
    project = Project_Create()
    saved = Project_Save(project, path)
    original = path.read_bytes()
    assert Project_Save(replace(project, name=""), path, saved.digest).result == ProjectIoResult.Invalid
    assert path.read_bytes() == original

