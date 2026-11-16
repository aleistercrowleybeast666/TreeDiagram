"""Real property entries restore private drafts without replacing user evidence."""
from dataclasses import asdict, replace
import json
from pathlib import Path
import threading

import pytest
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialogButtonBox, QDoubleSpinBox, QLabel,
    QPushButton, QScrollArea, QSpinBox,
)

from treediagram.core.storage import ProjectIoResult, Project_Load
from treediagram.design import ControlConfig, Design_CreateExample, Design_Decode, Scenario, SensorConfig
from treediagram.importers import Motor_Import
from treediagram.simulation import Simulation_Run


def config_data(config):
    # Production project JSON represents vector tuples as arrays.
    return json.loads(json.dumps(asdict(config)))


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

    QTimer.singleShot(20, perform)
    opener()
    if errors:
        raise errors[0]


def click(dialog, role):
    QTest.mouseClick(dialog.findChild(QDialogButtonBox).button(role), Qt.MouseButton.LeftButton)


def type_value(widget, text):
    widget.setFocus()
    widget.lineEdit().selectAll()
    QTest.keyClick(widget.lineEdit(), Qt.Key.Key_Backspace)
    QTest.keyClicks(widget.lineEdit(), text)


def test_algorithm_defaults_preserve_selection_range_and_cancel(window, tmp_path):
    design = Design_CreateExample("pid", "wheel")
    control = replace(design.control, start_phase="coast", end_phase="descent", kp=8.25,
                      lqr_q_angle=11., period_us=10000, wheel_inertia_kg_m2=.003)
    window.workbench.Design_Commit(replace(design, control=control))
    path = tmp_path / "parameters.tdproj"
    assert window.session.Project_Save(path).result == ProjectIoResult.Success
    before = window.session.project

    def restore(dialog):
        status = dialog.findChild(QLabel, "draft_status")
        assert "3 项参数偏离默认" in status.text()
        click(dialog, QDialogButtonBox.StandardButton.RestoreDefaults)
        assert window.session.project == before and not window.session.dirty
        assert "待应用" in status.text()
        assert "均为默认" in status.text()
        for key in ("estimator", "controller", "actuator", "start_phase", "end_phase"):
            assert dialog.findChild(QComboBox, key).currentData() == getattr(control, key)
        for key in ("kp", "lqr_q_angle"):
            assert dialog.findChild(QDoubleSpinBox, key).value() == getattr(ControlConfig(), key)
        QTest.keyClick(dialog, Qt.Key.Key_Escape)

    interact(window.workbench.Task_Edit, restore)
    assert window.session.project == before and not window.session.dirty

    def apply(dialog):
        assert dialog.findChild(QDoubleSpinBox, "kp").value() == control.kp
        click(dialog, QDialogButtonBox.StandardButton.RestoreDefaults)
        click(dialog, QDialogButtonBox.StandardButton.Apply)
        assert not dialog.isVisible()

    interact(window.workbench.Task_Edit, apply)
    defaults = ControlConfig()
    expected = replace(control, kp=defaults.kp, lqr_q_angle=defaults.lqr_q_angle,
                       period_us=defaults.period_us)
    assert config_data(window.workbench.design.control) == config_data(expected)
    assert window.workbench.design.id == design.id
    assert window.session.dirty
    assert window.session.Project_Save().result == ProjectIoResult.Success
    assert config_data(Design_Decode(Project_Load(path).project.design).control) == config_data(expected)

    def reopen(dialog):
        assert not dialog.findChild(QPushButton, "restore_defaults").isEnabled()
        assert "与已应用配置一致" in dialog.findChild(QLabel, "draft_status").text()

    interact(window.workbench.Task_Edit, reopen)


@pytest.mark.parametrize("key,text", [("step_us", "10000.5"), ("gravity_mps2", "")])
def test_restore_replaces_invalid_numeric_text_and_direct_apply(window, key, text):
    design = Design_CreateExample()
    design = replace(design, scenario=replace(design.scenario, gravity_mps2=9.5))
    window.workbench.Design_Commit(design)
    before = window.session.project

    def edit(dialog):
        widget = dialog.findChild(QSpinBox if key == "step_us" else QDoubleSpinBox, key)
        type_value(widget, text)
        click(dialog, QDialogButtonBox.StandardButton.Apply)
        assert dialog.isVisible() and window.session.project == before
        assert widget.lineEdit().text() == text
        assert "尚未应用" in dialog.findChild(QLabel, "draft_error").text()
        assert "默认状态待确认" in dialog.findChild(QLabel, "draft_status").text()
        click(dialog, QDialogButtonBox.StandardButton.RestoreDefaults)
        assert not dialog.findChild(QLabel, "draft_error").text()
        assert widget.Draft_Value() == getattr(Scenario(), key)
        # A new legal edit after reset must be consumed without Enter or focus-out.
        type_value(dialog.findChild(QDoubleSpinBox, "gravity_mps2"), "9.765432")
        click(dialog, QDialogButtonBox.StandardButton.Apply)
        assert not dialog.isVisible()

    interact(window.workbench.Scenario_Edit, edit)
    assert config_data(window.workbench.design.scenario) == config_data(replace(Scenario(), gravity_mps2=9.765432))


def test_scenario_defaults_keep_imported_motor_assembly_and_unexposed_fields(window):
    design, _ = Motor_Import(Path(__file__).parent / "fixtures/motor/valid_positive.tdmotor.json",
                             Design_CreateExample())
    design = replace(design, scenario=replace(design.scenario, duration_s=25.,
                     wind_enu_mps=(8., -3., 1.), cp_body_m=(0., 0., -.4),
                     reference_area_m2=.015, output_us=40000, aero_max_angle_deg=15.,
                     aero_provenance="reviewed user coefficients"))
    window.workbench.Design_Commit(design)
    before = asdict(window.workbench.design)

    def apply(dialog):
        click(dialog, QDialogButtonBox.StandardButton.RestoreDefaults)
        assert asdict(window.workbench.design) == before
        click(dialog, QDialogButtonBox.StandardButton.Apply)

    interact(window.workbench.Scenario_Edit, apply)
    after = asdict(window.workbench.design)
    assert {key: value for key, value in after.items() if key != "scenario"} == {
        key: value for key, value in before.items() if key != "scenario"}
    assert config_data(window.workbench.design.scenario) == config_data(replace(
        Scenario(), output_us=40000, aero_max_angle_deg=15.))


@pytest.mark.parametrize("key,text,expected_source", [
    ("gravity_mps2", "9.7", "reviewed user coefficients"),
    ("drag_coefficient", "0.6", Scenario().aero_provenance),
])
def test_scenario_edits_only_replace_provenance_when_aerodynamics_change(window, key, text, expected_source):
    design = Design_CreateExample()
    design = replace(design, scenario=replace(design.scenario, aero_provenance="reviewed user coefficients"),
                     import_issues=("aero_provenance: 请审核气动近似适用性",))
    window.workbench.Design_Commit(design)

    def apply(dialog):
        type_value(dialog.findChild(QDoubleSpinBox, key), text)
        click(dialog, QDialogButtonBox.StandardButton.Apply)
        assert not dialog.isVisible()

    interact(window.workbench.Scenario_Edit, apply)
    assert window.workbench.design.scenario.aero_provenance == expected_source
    assert tuple(window.workbench.design.import_issues) == design.import_issues
    assert not window.workbench.run_button.isEnabled()


def test_sensor_defaults_preserve_mounting_and_validate_retained_draft(window):
    design = Design_CreateExample()
    sensors = replace(design.sensors, rotation_bs_wxyz=(0., 0., 0., 1.), imu_us=20000,
                      accel_bias_mps2=(1., 2., 3.), accel_limit_mps2=100.)
    window.workbench.Design_Commit(replace(design, sensors=sensors))
    before = window.session.project

    def apply(dialog):
        rotation = dialog.findChild(QDoubleSpinBox, "rotation_bs_wxyz_3")
        type_value(rotation, "0")
        click(dialog, QDialogButtonBox.StandardButton.RestoreDefaults)
        assert rotation.Draft_Value() == 0
        click(dialog, QDialogButtonBox.StandardButton.Apply)
        assert dialog.isVisible() and window.session.project == before
        assert dialog.findChild(QLabel, "draft_error").text()
        type_value(rotation, "1")
        click(dialog, QDialogButtonBox.StandardButton.Apply)
        assert not dialog.isVisible()

    interact(window.workbench.Sensors_Edit, apply)
    assert config_data(window.workbench.design.sensors) == config_data(replace(
        SensorConfig(), rotation_bs_wxyz=(0., 0., 0., 1.), accel_limit_mps2=100.))


@pytest.mark.parametrize("dismiss", ["cancel", "escape", "close"])
def test_scenario_restoration_dismissal_keeps_saved_project(window, tmp_path, dismiss):
    design = Design_CreateExample()
    window.workbench.Design_Commit(replace(design, scenario=replace(design.scenario, gravity_mps2=9.7)))
    assert window.session.Project_Save(tmp_path / "saved.tdproj").result == ProjectIoResult.Success
    before = window.session.project

    def cancel(dialog):
        click(dialog, QDialogButtonBox.StandardButton.RestoreDefaults)
        assert "待应用" in dialog.findChild(QLabel, "draft_status").text()
        if dismiss == "cancel":
            click(dialog, QDialogButtonBox.StandardButton.Cancel)
        elif dismiss == "escape":
            QTest.keyClick(dialog, Qt.Key.Key_Escape)
        else:
            dialog.close()
        assert not dialog.isVisible()

    interact(window.workbench.Scenario_Edit, cancel)
    assert window.session.project == before and not window.session.dirty
    assert config_data(Design_Decode(Project_Load(window.session.path).project.design)) == config_data(window.workbench.design)


def test_restore_keeps_invalid_phase_range_for_explicit_correction(window):
    design = Design_CreateExample("pid")
    window.workbench.Design_Commit(replace(design, control=replace(design.control, kp=8.)))
    before = window.session.project

    def edit(dialog):
        start = dialog.findChild(QComboBox, "start_phase")
        start.setCurrentIndex(start.findData("descent"))
        click(dialog, QDialogButtonBox.StandardButton.RestoreDefaults)
        click(dialog, QDialogButtonBox.StandardButton.Apply)
        assert dialog.isVisible() and window.session.project == before
        assert "invalid inclusive phase range" in dialog.findChild(QLabel, "draft_error").text()
        assert start.currentData() == "descent"
        start.setCurrentIndex(start.findData("powered"))
        click(dialog, QDialogButtonBox.StandardButton.Apply)
        assert not dialog.isVisible()

    interact(window.workbench.Task_Edit, edit)
    assert window.workbench.design.control.kp == ControlConfig().kp


def test_unchanged_default_apply_is_not_a_configuration_change(window, tmp_path):
    window.workbench.Design_Commit(Design_CreateExample())
    assert window.session.Project_Save(tmp_path / "default.tdproj").result == ProjectIoResult.Success
    before = window.session.project

    def apply(dialog):
        assert not dialog.findChild(QPushButton, "restore_defaults").isEnabled()
        assert "均为默认" in dialog.findChild(QLabel, "draft_status").text()
        click(dialog, QDialogButtonBox.StandardButton.Apply)
        assert not dialog.isVisible()

    interact(window.workbench.Scenario_Edit, apply)
    assert window.session.project == before and not window.session.dirty


@pytest.mark.parametrize("focus", ["input", "restore"])
@pytest.mark.parametrize("entry,attribute,key,text", [
    ("Task_Edit", "control", "kp", "6.75"),
    ("Scenario_Edit", "scenario", "gravity_mps2", "9.73"),
    ("Sensors_Edit", "sensors", "pressure_std_pa", "2.5"),
    ("Actuator_Edit", "control", "angle_limit_rad", "0.25"),
])
def test_return_never_restores_parameters_implicitly(window, entry, attribute, key, text, focus):
    design = Design_CreateExample("pid")
    window.workbench.Design_Commit(replace(
        design, control=replace(design.control, kp=8., angle_limit_rad=.3),
        scenario=replace(design.scenario, gravity_mps2=9.5),
        sensors=replace(design.sensors, pressure_std_pa=3.5)))

    def edit(dialog):
        value = dialog.findChild(QDoubleSpinBox, key)
        type_value(value, text)
        target = value.lineEdit() if focus == "input" else dialog.findChild(QPushButton, "restore_defaults")
        target.setFocus()
        QTest.keyClick(target, Qt.Key.Key_Return)
        assert value.Draft_Value() == float(text)
        if dialog.isVisible():
            click(dialog, QDialogButtonBox.StandardButton.Apply)
        assert not dialog.isVisible()

    interact(getattr(window.workbench, entry), edit)
    assert getattr(getattr(window.workbench.design, attribute), key) == float(text)


def test_return_keeps_invalid_text_and_space_can_explicitly_restore(window):
    design = Design_CreateExample("pid")
    window.workbench.Design_Commit(replace(design, control=replace(design.control, kp=8.)))
    before = window.session.project

    def edit(dialog):
        period = dialog.findChild(QSpinBox, "period_us")
        type_value(period, "10000.5")
        QTest.keyClick(period.lineEdit(), Qt.Key.Key_Return)
        assert dialog.isVisible() and window.session.project == before
        assert period.lineEdit().text() == "10000.5"
        reset = dialog.findChild(QPushButton, "restore_defaults")
        assert not reset.autoDefault() and not reset.isDefault()
        reset.setFocus()
        QTest.keyClick(reset, Qt.Key.Key_Space)
        assert dialog.findChild(QDoubleSpinBox, "kp").Draft_Value() == ControlConfig().kp
        assert period.Draft_Value() == ControlConfig().period_us
        assert window.session.project == before

    interact(window.workbench.Task_Edit, edit)
    assert window.session.project == before


@pytest.mark.parametrize("actuator,key,value", [
    ("gimbal", "angle_limit_rad", .3), ("fin", "fin_area_m2", .01),
    ("wheel", "wheel_inertia_kg_m2", .004), ("rcs", "rcs_force_n", 3.),
])
def test_actuator_defaults_only_affect_selected_model(window, actuator, key, value):
    design = Design_CreateExample("pid", actuator)
    control = replace(design.control, **{key: value}, kp=8.,
                      actuator_position_m=(.05, .01, -.6), rcs_isp_s=70. if actuator != "rcs" else 50.)
    window.workbench.Design_Commit(replace(design, control=control))
    before = window.session.project

    def apply(dialog):
        click(dialog, QDialogButtonBox.StandardButton.RestoreDefaults)
        assert window.session.project == before
        if actuator in ("fin", "rcs"):
            assert dialog.findChild(QDoubleSpinBox, "actuator_position_m_0").Draft_Value() == .05
        click(dialog, QDialogButtonBox.StandardButton.Apply)

    interact(window.workbench.Actuator_Edit, apply)
    expected = replace(control, **{key: getattr(ControlConfig(), key)})
    assert config_data(window.workbench.design.control) == config_data(expected)


def test_restoring_during_real_run_keeps_snapshot_and_historical_selection(window, app, monkeypatch):
    import treediagram.workbench as module
    design = Design_CreateExample()
    design = replace(design, scenario=replace(design.scenario, duration_s=.04, gravity_mps2=9.5))
    completed = Simulation_Run(design)
    window.session.Project_Set(replace(window.session.project, flight_runs=(completed,)))
    window.workbench.Design_Commit(design)
    entered, release = threading.Event(), threading.Event()

    def delayed(snapshot, cancel, progress):
        entered.set()
        assert release.wait(5.)
        return Simulation_Run(snapshot, cancel, progress)

    monkeypatch.setattr(module, "Simulation_Run", delayed)
    window.workbench.Run_Start()
    assert entered.wait(1.)
    try:
        def apply(dialog):
            assert any("下一次运行" in item.text() for item in dialog.findChildren(QLabel))
            click(dialog, QDialogButtonBox.StandardButton.RestoreDefaults)
            click(dialog, QDialogButtonBox.StandardButton.Apply)

        interact(window.workbench.Scenario_Edit, apply)
        assert window.workbench.busy
        assert config_data(window.workbench.design.scenario) == config_data(Scenario())
        assert window.session.project.flight_runs == (completed,)
        assert "历史配置" in window.workbench.result_info.text()
    finally:
        release.set()
        for _ in range(500):
            app.processEvents()
            if not window.workbench.busy:
                break
            QTest.qWait(5)
    assert not window.workbench.busy
    assert config_data(window.workbench.design.scenario) == config_data(Scenario())
    runs = window.session.project.flight_runs
    assert len(runs) == 2 and runs[0] == completed
    assert json.loads(json.dumps(runs[1]["design"])) == json.loads(json.dumps(completed["design"]))
    assert window.workbench.run_select.currentData() == completed["run_id"]
    assert "历史配置" in window.workbench.result_info.text()


@pytest.mark.parametrize("theme", [0, 1])
@pytest.mark.parametrize("entry", ["Task_Edit", "Scenario_Edit", "Sensors_Edit", "Actuator_Edit"])
def test_default_controls_remain_reachable_and_refresh_is_read_only(window, app, theme, entry):
    window.resize(920, 620)
    window.theme_combo.setCurrentIndex(theme)
    design = Design_CreateExample("lqr")
    window.workbench.Design_Commit(replace(design, control=replace(design.control, lqr_r=4.)))
    before = window.session.project
    window.session.dirty = False
    window.navigation.setCurrentRow(2)
    app.processEvents()
    assert "偏离模型默认" in window.workbench.defaults_info.text()
    action = window.workbench.run_button
    assert window.rect().contains(action.mapTo(window, action.rect().bottomRight()))

    def inspect(dialog):
        dialog.resize(520, 460)
        app.processEvents()
        status = dialog.findChild(QLabel, "draft_status")
        assert "与已应用配置一致" in status.text()
        for role in (QDialogButtonBox.StandardButton.RestoreDefaults,
                     QDialogButtonBox.StandardButton.Apply, QDialogButtonBox.StandardButton.Cancel):
            button = dialog.findChild(QDialogButtonBox).button(role)
            assert button.isVisible()
            assert dialog.rect().contains(button.mapTo(dialog, button.rect().bottomRight()))
        scroll = dialog.findChild(QScrollArea)
        assert scroll.horizontalScrollBar().maximum() == 0
        window.workbench.Refresh()
        assert status.text().startswith("与已应用配置一致")
        assert window.session.project == before and not window.session.dirty

    interact(getattr(window.workbench, entry), inspect)
    assert window.session.project == before and not window.session.dirty
