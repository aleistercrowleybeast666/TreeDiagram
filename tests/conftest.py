import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from treediagram.ui import MainWindow


@pytest.fixture(scope="session")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def window(app):
    widget = MainWindow()
    widget.show()
    app.processEvents()
    yield widget
    widget.session.dirty = False
    widget.close()
    widget.deleteLater()
    app.processEvents()

