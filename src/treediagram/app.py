import sys

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
from PySide6.QtWidgets import QApplication

from .ui import MainWindow


def App_Main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("TreeDiagram")
    app.setOrganizationName("TreeDiagram")
    translator = QTranslator(app)
    translator.load(QLocale("zh_CN"), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
    app.installTranslator(translator)
    window = MainWindow()
    window.show()
    return app.exec()

