from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

from treediagram.dialog_geometry import CenteredMessageBox


def test_message_box_is_centered_and_cancel_preserves_project(window, app):
    owner = QWidget()
    owner.setGeometry(60, 40, 600, 420)
    owner.show()
    box = CenteredMessageBox(owner)
    box.setText('Save before closing?')
    box.show(); app.processEvents()
    assert (box.frameGeometry().center() - owner.frameGeometry().center()).manhattanLength() <= 2
    assert owner.screen().availableGeometry().contains(box.frameGeometry())
    box.reject(); owner.close()
    before = window.session.project
    window.session.dirty = True
    observed = []

    def cancel():
        dialog = QApplication.activeModalWidget()
        observed.append(isinstance(dialog, CenteredMessageBox))
        assert isinstance(dialog, QMessageBox)
        dialog.escapeButton().click()

    QTimer.singleShot(25, cancel)
    assert not window._Changes_ConfirmDiscard()
    assert observed == [True]
    assert window.session.dirty and window.session.project == before
