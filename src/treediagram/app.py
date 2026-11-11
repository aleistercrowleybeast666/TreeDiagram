import sys

from PySide6.QtCore import QLibraryInfo, QLocale, QRect, QTimer, QTranslator
from PySide6.QtWidgets import QApplication, QMainWindow

from .ui import MainWindow


def App_ConstrainInitialGeometry(window: QMainWindow, available: QRect | None = None) -> None:
    """Keep the initial frame on its screen while preserving valid user geometry."""
    if window.isMaximized() or window.isFullScreen():
        return
    if available is None:
        screen = window.screen()
        if screen is None:
            return
        available = screen.availableGeometry()
    frame = window.frameGeometry()
    if not available.isValid() or available.contains(frame):
        return
    width = max(1, available.width() - max(0, frame.width() - window.width()))
    height = max(1, available.height() - max(0, frame.height() - window.height()))
    window.setMinimumSize(min(window.minimumWidth(), width), min(window.minimumHeight(), height))
    window.resize(min(window.width(), width), min(window.height(), height))
    frame = window.frameGeometry()
    window.move(
        max(available.left(), min(frame.left(), available.right() - frame.width() + 1)),
        max(available.top(), min(frame.top(), available.bottom() - frame.height() + 1)),
    )


def App_Main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("TreeDiagram")
    app.setOrganizationName("TreeDiagram")
    translator = QTranslator(app)
    translator.load(QLocale("zh_CN"), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
    app.installTranslator(translator)
    window = MainWindow()
    window.show()
    App_ConstrainInitialGeometry(window)
    # Native frame margins settle after show; this is a startup-only correction.
    QTimer.singleShot(0, window, lambda: App_ConstrainInitialGeometry(window))
    return app.exec()

