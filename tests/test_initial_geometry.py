"""Real workbench geometry, view state and initial-frame boundaries."""
import pytest
from PySide6.QtCore import QRect

from treediagram.app import App_ConstrainInitialGeometry


@pytest.mark.parametrize("size", [(1536, 816), (1280, 680)])
def test_initial_frame_keeps_status_and_task_action_reachable(window, app, size):
    available = QRect(0, 0, *size)
    window.move(350, 180)
    app.processEvents()
    assert not available.contains(window.frameGeometry())
    project = window.session.project
    App_ConstrainInitialGeometry(window, available)
    app.processEvents()
    assert available.contains(window.frameGeometry())
    status = window.statusBar()
    assert available.contains(status.mapToGlobal(status.rect().bottomRight()))
    window.navigation.setCurrentRow(2)
    app.processEvents()
    action = window.workbench.run_button
    assert window.rect().contains(action.mapTo(window, action.rect().bottomRight()))
    assert window.session.project == project and not window.session.dirty


def test_valid_geometry_maximization_and_later_views_are_preserved(window, app):
    available = QRect(0, 0, 1600, 1000)
    window.resize(1000, 660)
    window.move(25, 30)
    app.processEvents()
    before = window.frameGeometry()
    assert available.contains(before)
    App_ConstrainInitialGeometry(window, available)
    assert window.frameGeometry() == before
    project = window.session.project
    window.theme_combo.setCurrentIndex(1)
    window.navigation.setCurrentRow(2)
    window.navigation.setCurrentRow(0)
    app.processEvents()
    assert window.frameGeometry() == before
    assert window.session.project == project and not window.session.dirty
    window.showMaximized()
    app.processEvents()
    before = window.frameGeometry()
    App_ConstrainInitialGeometry(window, available)
    assert window.isMaximized() and window.frameGeometry() == before
