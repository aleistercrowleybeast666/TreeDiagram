"""Parent-relative placement for modal desktop message boxes."""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox


def Dialog_CenterOnOwner(dialog) -> None:
    owner = dialog.parentWidget()
    if owner is None or owner.window().screen() is None:
        return
    owner = owner.window()
    available = owner.screen().availableGeometry()
    frame = dialog.frameGeometry()
    width = max(1, available.width() - max(0, frame.width() - dialog.width()))
    height = max(1, available.height() - max(0, frame.height() - dialog.height()))
    dialog.setMinimumSize(min(dialog.minimumWidth(), width), min(dialog.minimumHeight(), height))
    dialog.resize(min(dialog.width(), width), min(dialog.height(), height))
    frame = dialog.frameGeometry()
    frame.moveCenter(owner.frameGeometry().center())
    dialog.move(
        max(available.left(), min(frame.left(), available.right() - frame.width() + 1)),
        max(available.top(), min(frame.top(), available.bottom() - frame.height() + 1)),
    )


class CenteredMessageBox(QMessageBox):
    def showEvent(self, event):
        super().showEvent(event)
        Dialog_CenterOnOwner(self)
        QTimer.singleShot(0, self, lambda: Dialog_CenterOnOwner(self))
