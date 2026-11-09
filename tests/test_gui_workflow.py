"""Production workspace entries; drafts, readiness and stable result ownership."""
from dataclasses import replace
import threading

import pytest
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialogButtonBox, QDoubleSpinBox, QLabel,
    QPushButton, QSpinBox,
)

from treediagram.core.storage import ProjectIoResult, Project_Load, Project_Save
from treediagram.design import Design_CreateExample, Design_Decode, Design_Validate
from treediagram.simulation import Simulation_Run


def interact(opener, callback):
    errors = []

    def perform():
        dialog = QApplication.activeModalWidget()
        try:
            assert dialog is not None
            callback(dialog)
        except BaseException as exc:
            errors.append(exc)
        finally:
            if dialog is not None and dialog.isVisible():
                dialog.reject()

    QTimer.singleShot(40, perform)
    opener()
    if errors:
        raise errors[0]


def button(dialog, role):
    return dialog.findChild(QDialogButtonBox).button(role)


def type_value(widget, text):
    widget.setFocus()
    widget.lineEdit().selectAll()
    QTest.keyClick(widget.lineEdit(), Qt.Key.Key_Backspace)
    QTest.keyClicks(widget.lineEdit(), text)


def test_task_controller_fields_and_integer_period(window, app):
    window.workbench.Design_Commit(Design_CreateExample("pid"))
    before = window.session.project

    def inspect(dialog):
        controller = dialog.findChild(QComboBox, "controller")
        assert controller is not None
        kp = dialog.findChild(QDoubleSpinBox, "kp")
        q = dialog.findChild(QDoubleSpinBox, "lqr_q_angle")
        period = dialog.findChild(QSpinBox, "period_us")
        assert period is not None and kp.isVisible() and not q.isVisible()
        type_value(kp, "2.75")
        controller.setCurrentIndex(controller.findData("lqr"))
        assert q.isVisible() and not kp.isVisible()
        controller.setCurrentIndex(controller.findData("pid"))
        assert kp.value() == 2.75
        QTest.keyClick(dialog, Qt.Key.Key_Escape)

    interact(window.workbench.task_edit_button.click, inspect)
    assert window.session.project == before


def test_part_invalid_intermediate_text_does_not_apply(window, app):
    window.workbench.Design_Commit(Design_CreateExample())
    part = window.workbench.design.parts[0]
    before = window.session.project

    def inspect(dialog):
        mass = dialog.findChildren(QDoubleSpinBox)[0]
        type_value(mass, "")
        QTest.mouseClick(button(dialog, QDialogButtonBox.StandardButton.Apply),
                         Qt.MouseButton.LeftButton)
        assert dialog.isVisible()
        assert mass.lineEdit().text() == ""
        assert window.session.project == before

    interact(lambda: window.workbench.Part_EditDraft(part), inspect)


def test_part_valid_keyboard_apply_without_enter_and_reopen(window, app, tmp_path):
    window.workbench.Design_Commit(Design_CreateExample())
    part = window.workbench.design.parts[0]

    def apply(dialog):
        type_value(dialog.findChildren(QDoubleSpinBox)[0], "0.75321")
        QTest.mouseClick(button(dialog, QDialogButtonBox.StandardButton.Apply),
                         Qt.MouseButton.LeftButton)
        assert not dialog.isVisible()

    interact(lambda: window.workbench.Part_EditDraft(part), apply)
    assert window.workbench.design.parts[0].mass_kg == 0.75321
    target = tmp_path / "draft.tdproj"
    assert Project_Save(window.session.project, target).result == ProjectIoResult.Success
    restored = Project_Load(target)
    assert restored.result == ProjectIoResult.Success
    assert Design_Decode(restored.project.design).parts[0].mass_kg == 0.75321


def test_refresh_preserves_selected_run_and_comparison_by_id(window, app):
    design = Design_CreateExample()
    design = replace(design, scenario=replace(design.scenario, duration_s=.04))
    first = Simulation_Run(design)
    second = Simulation_Run(design)
    window.session.Project_Set(replace(window.session.project,
                                       flight_runs=(first, second)))
    window.workbench.Design_Commit(design)
    window.workbench.run_select.setCurrentIndex(0)
    window.workbench.compare.setCurrentIndex(2)
    window.workbench.Design_Commit(replace(design, name="renamed"))
    assert window.workbench.run_select.currentData() == first["run_id"]
    assert window.workbench.compare.currentData() == second["run_id"]
    assert "历史配置" in window.workbench.result_info.text()


def test_empty_results_explain_disabled_export(window):
    assert not window.workbench.result_export_button.isEnabled()
    assert not window.workbench.parameter_export_button.isEnabled()
    assert "运行" in window.workbench.result_info.text()


def test_fractional_period_is_not_silently_truncated(window):
    window.workbench.Design_Commit(Design_CreateExample("pid"))
    before = window.session.project

    def inspect(dialog):
        period = dialog.findChild(QSpinBox, "period_us")
        type_value(period, "10000.5")
        assert period.lineEdit().text() == "10000.5"
        QTest.mouseClick(button(dialog, QDialogButtonBox.StandardButton.Apply), Qt.MouseButton.LeftButton)
        assert dialog.isVisible()
        assert period.lineEdit().text() == "10000.5"
        assert window.session.project == before
        assert "尚未应用" in dialog.findChild(QLabel, "draft_error").text()
        type_value(period, "10000")
        QTest.mouseClick(button(dialog, QDialogButtonBox.StandardButton.Apply), Qt.MouseButton.LeftButton)
        assert not dialog.isVisible()

    interact(window.workbench.task_edit_button.click, inspect)
    assert window.workbench.design.control.period_us == 10000


def test_phase_capsule_uses_shared_editor_and_preserves_id(window, app, tmp_path):
    design = Design_CreateExample("pid")
    window.workbench.Design_Commit(design)
    window.navigation.setCurrentRow(2)

    def phase_inspect(dialog):
        assert "本阶段运行" in dialog.findChild(QLabel, "phase_instances").text()
        before = window.session.project

        def cancel(editor):
            type_value(editor.findChild(QDoubleSpinBox, "kp"), "3.5")
            QTest.keyClick(editor, Qt.Key.Key_Escape)

        edit = dialog.findChild(QPushButton, "phase_edit_shared")
        interact(edit.click, cancel)
        assert window.session.project == before

        def apply(editor):
            type_value(editor.findChild(QDoubleSpinBox, "kp"), "3.5")
            QTest.mouseClick(button(editor, QDialogButtonBox.StandardButton.Apply), Qt.MouseButton.LeftButton)
            assert not editor.isVisible()

        interact(edit.click, apply)
        assert window.workbench.design.control.kp == 3.5
        assert window.workbench.design.id == design.id
        QTest.keyClick(dialog, Qt.Key.Key_Escape)

    interact(window.workbench.phase_buttons["powered"].click, phase_inspect)
    path = tmp_path / "shared.tdproj"
    assert Project_Save(window.session.project, path).result == ProjectIoResult.Success
    assert Design_Decode(Project_Load(path).project.design).control.kp == 3.5


def test_missing_model_inputs_block_run_and_expose_next_step(window):
    design = Design_CreateExample()
    missing = replace(design.parts[0], mass_kg=None)
    window.workbench.Design_Commit(replace(design, parts=(missing, *design.parts[1:])))
    assert not window.workbench.run_button.isEnabled()
    assert window.workbench.issues.count() > 0
    assert "尚缺" in window.readiness_label.text()
    window.next_step_button.click()
    assert window.navigation.currentRow() == 1
    window.workbench.Design_Commit(design)
    assert window.workbench.run_button.isEnabled()
    assert "配置已就绪" in window.workbench.run_status.text()
    assert "先建立" not in window.workbench.run_status.text()


def wait_job(window, app):
    for _ in range(500):
        app.processEvents()
        if not window.workbench.busy:
            app.processEvents()
            return
        threading.Event().wait(.005)
    raise AssertionError("worker did not finish")


def test_busy_edit_cannot_be_replaced_by_old_worker(window, app, monkeypatch):
    import treediagram.workbench as module
    entered, release = threading.Event(), threading.Event()
    original = module.Simulation_Run

    def delayed(design, cancel, progress):
        entered.set()
        assert release.wait(2.)
        return original(design, cancel, progress)

    monkeypatch.setattr(module, "Simulation_Run", delayed)
    design = Design_CreateExample()
    design = replace(design, scenario=replace(design.scenario, duration_s=.04))
    window.workbench.Design_Commit(design)
    window.workbench.Run_Start()
    assert entered.wait(1.)
    window.workbench.Design_Commit(replace(design, name="newer draft committed"))
    release.set()
    wait_job(window, app)
    assert window.workbench.design.name == "newer draft committed"
    assert window.session.project.flight_runs[0]["design"]["name"] == design.name
    assert "历史配置" in window.workbench.result_info.text()


def test_close_during_run_continues_unsaved_protection_once(window, app, monkeypatch):
    import treediagram.workbench as module
    from treediagram.simulation import SimulationCancelled

    def wait_cancel(design, cancel, progress):
        for _ in range(500):
            if cancel():
                raise SimulationCancelled("test cancellation")
            threading.Event().wait(.002)
        raise AssertionError("cancel was not requested")

    monkeypatch.setattr(module, "Simulation_Run", wait_cancel)
    checks = []
    monkeypatch.setattr(window, "_Changes_ConfirmDiscard", lambda: checks.append(True) or False)
    window.workbench.Design_Commit(Design_CreateExample())
    window.workbench.Run_Start()
    assert not window.close()
    wait_job(window, app)
    assert checks == [True]
    assert window.isVisible()
    assert not window._close_pending
    assert window.session.project.flight_runs == ()
    monkeypatch.setattr(window, "_Changes_ConfirmDiscard", lambda: True)


def test_failed_worker_keeps_last_valid_result(window, app, monkeypatch):
    import treediagram.workbench as module
    design = Design_CreateExample()
    design = replace(design, scenario=replace(design.scenario, duration_s=.04))
    first = Simulation_Run(design)
    window.session.Project_Set(replace(window.session.project, flight_runs=(first,)))
    window.workbench.Design_Commit(design)

    def fail(*args):
        raise RuntimeError("compiler dependency missing")

    monkeypatch.setattr(module, "Simulation_Run", fail)
    window.workbench.Run_Start()
    wait_job(window, app)
    assert window.session.project.flight_runs == (first,)
    assert "运行失败" in window.workbench.run_status.text()
    assert window.workbench.run_select.currentData() == first["run_id"]


def test_untouched_numeric_values_keep_scientific_precision(window):
    design = Design_CreateExample()
    value = 0.753211234567
    design = replace(design, parts=(replace(design.parts[0], mass_kg=value), *design.parts[1:]))
    window.workbench.Design_Commit(design)

    def apply(dialog):
        button(dialog, QDialogButtonBox.StandardButton.Apply).click()

    interact(lambda: window.workbench.Part_EditDraft(design.parts[0]), apply)
    assert window.workbench.design.parts[0].mass_kg == value


@pytest.mark.parametrize("value", [10000.5, 10000., True, 999, 1000001])
def test_backend_period_does_not_coerce_invalid_values(value):
    design = Design_CreateExample("pid")
    with pytest.raises(ValueError, match="period_us"):
        Design_Validate(replace(design, control=replace(design.control, period_us=value)))
