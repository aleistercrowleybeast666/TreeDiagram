from dataclasses import replace, asdict
import json
import threading
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QDialogButtonBox, QDoubleSpinBox

from treediagram.design import Design_CreateExample, Design_Digest
from treediagram.core.storage import Project_Save, Project_Load, ProjectIoResult


def finish(window,app,limit=1000):
    for _ in range(limit):
        app.processEvents()
        if not window.workbench.busy:return
        # QTest.qWait holds the Python GIL on this PySide build; let the actual
        # Python solver worker execute as the normal Qt app.exec loop does.
        threading.Event().wait(.01)
    raise AssertionError("background job did not finish in bounded test wait")


def test_shared_algorithm_draft_cancel_and_apply(window,app):
    window.workbench.Design_Commit(Design_CreateExample())
    before=window.session.project
    def cancel():
        dialog=QApplication.activeModalWidget()
        box=dialog.findChildren(QComboBox)[1]
        box.setCurrentIndex(box.findData("pid"))
        QTest.keyClick(dialog,Qt.Key.Key_Escape)
    QTimer.singleShot(30,cancel)
    window.workbench.Task_Edit()
    assert window.session.project==before
    def apply():
        dialog=QApplication.activeModalWidget()
        boxes=dialog.findChildren(QComboBox)
        boxes[0].setCurrentIndex(boxes[0].findData("kf6"))
        boxes[1].setCurrentIndex(boxes[1].findData("pid"))
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Apply).click()
    QTimer.singleShot(30,apply)
    window.workbench.Task_Edit()
    assert window.workbench.design.control.controller=="pid"
    assert window.workbench.design.control.estimator=="kf6"


def test_real_background_publish_staleness_cancel_and_roundtrip(window,app,tmp_path):
    design=Design_CreateExample()
    design=replace(design,scenario=replace(design.scenario,duration_s=.25))
    window.workbench.Design_Commit(design)
    window.workbench.Run_Start()
    finish(window,app)
    assert len(window.session.project.flight_runs)==1
    first=window.session.project.flight_runs[0]
    assert first["input_digest"]==Design_Digest(design)
    window.workbench.Design_Commit(replace(design,name="after run"))
    assert "历史配置" in window.workbench.result_info.text()
    window.workbench.Run_Start();window.workbench.Run_Cancel();finish(window,app)
    assert window.session.project.flight_runs==(first,)
    path=tmp_path/"real.tdproj"
    assert Project_Save(window.session.project,path).result==ProjectIoResult.Success
    loaded=Project_Load(path)
    assert loaded.result==ProjectIoResult.Success
    assert loaded.project==window.session.project


def test_legacy_v1_is_read_without_inventing_design(tmp_path):
    from treediagram.core.model import Project_Create
    project=asdict(Project_Create())
    del project["design"];del project["flight_runs"]
    path=tmp_path/"legacy.tdproj"
    path.write_text(json.dumps({"format":"TreeDiagramProject","schema_version":1,"project":project}),encoding="utf-8")
    loaded=Project_Load(path)
    assert loaded.result==ProjectIoResult.Success and loaded.project.design is None


def test_part_cancel_and_invalid_mass_dont_commit(window,app):
    window.workbench.Design_Commit(Design_CreateExample())
    before=window.session.project
    part=window.workbench.design.parts[0]
    def cancel():
        dialog=QApplication.activeModalWidget()
        dialog.findChildren(QDoubleSpinBox)[0].setValue(12.)
        QTest.keyClick(dialog,Qt.Key.Key_Escape)
    QTimer.singleShot(30,cancel)
    window.workbench.Part_EditDraft(part)
    assert window.session.project==before
