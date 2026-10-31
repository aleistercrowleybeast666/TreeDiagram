from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .model import Project, Project_Create, RunRecord
from .storage import ProjectIoOutcome, ProjectIoResult, Project_Load, Project_Save


class ProjectSession:
    def __init__(self):
        self.project = Project_Create()
        self.path: Path | None = None
        self.digest: str | None = None
        self.dirty = False

    def Project_Set(self, project: Project) -> None:
        if project != self.project:
            self.project = project
            self.dirty = True

    def Project_New(self) -> None:
        self.project = Project_Create()
        self.path, self.digest, self.dirty = None, None, False

    def Project_Open(self, path: Path) -> ProjectIoOutcome:
        outcome = Project_Load(path)
        if outcome.result == ProjectIoResult.Success:
            self.project = outcome.project
            self.path, self.digest, self.dirty = path, outcome.digest, False
        return outcome

    def Project_Save(self, path: Path | None = None, expected_digest: str | None = None) -> ProjectIoOutcome:
        target = path or self.path
        if target is None:
            return ProjectIoOutcome(ProjectIoResult.Invalid, "尚未选择保存路径。")
        expected = self.digest if target == self.path else expected_digest
        outcome = Project_Save(self.project, target, expected)
        if outcome.result == ProjectIoResult.Success:
            self.path, self.digest, self.dirty = target, outcome.digest, False
        return outcome

    def Run_Append(self, record: RunRecord) -> None:
        if len(self.project.runs) >= 100:
            raise ValueError("运行历史已满；请新建项目以保留现有历史。")
        self.Project_Set(replace(self.project, runs=(*self.project.runs, record)))

