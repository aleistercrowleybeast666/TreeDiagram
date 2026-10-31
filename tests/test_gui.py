from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPalette, QRawFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QPushButton

from treediagram import __version__
from treediagram.core.storage import ProjectIoResult, Project_Load


def test_shell_navigation_resize_theme_and_font(window, app):
    assert window.windowTitle() == "TreeDiagram"
    assert window.version_label.text() == f"v{__version__}"
    assert [action.text() for action in window.file_actions] == ["新建工程", "打开工程…", "保存工程", "工程另存为…"]
    assert not any("运行" in button.text() or "计算" in button.text() for button in window.findChildren(QPushButton))
    for width, height in ((920, 620), (1180, 780), (1440, 900)):
        window.resize(width, height)
        app.processEvents()
        assert window.size().width() == width
        assert window.size().height() == height
        assert window.theme_combo.isVisible()
        assert window.theme_combo.mapTo(window, window.theme_combo.rect().bottomRight()).x() < width
        for index in range(4):
            rectangle = window.navigation.visualItemRect(window.navigation.item(index))
            QTest.mouseClick(window.navigation.viewport(), Qt.MouseButton.LeftButton, pos=rectangle.center())
            assert window.pages.currentIndex() == index
            assert window.pages.currentWidget().horizontalScrollBar().maximum() == 0
    for index, background in ((1, "#0f172a"), (0, "#f4f6fa")):
        window.theme_combo.setCurrentIndex(index)
        app.processEvents()
        assert app.palette().color(QPalette.ColorRole.Window).name() == background
        assert "headerComboPopup" in app.styleSheet()
    assert app.font().family() == "Microsoft YaHei UI"
    assert app.font().pointSize() == 10
    raw_font = QRawFont.fromFont(app.font())
    assert raw_font.isValid()
    assert all(raw_font.supportsCharacter(ord(character)) for character in "TreeDiagram工程概览")


def test_gui_save_open_and_cancel_file_dialogs(window, tmp_path, monkeypatch):
    window.project_name.setText("TreeDiagram 界面试用")
    window.description.setPlainText("定位待确定。")
    assert window.session.dirty
    before = window.session.project
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: ("", ""))
    assert not window._Project_Save(False)
    assert window.session.path is None and window.session.project == before
    assert list(tmp_path.iterdir()) == []
    path = tmp_path / "试用.tdproj"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(path), ""))
    assert window._Project_Save(False)
    assert Project_Load(path).project == before
    assert not window.session.dirty
    window._Project_New()
    assert window.session.path is None
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(path), ""))
    window._Project_Open()
    assert window.session.project == before
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: ("", ""))
    window._Project_Open()
    assert window.session.project == before
    assert window.windowTitle() == "TreeDiagram"


def test_bad_file_does_not_replace_gui_edits(window, tmp_path, monkeypatch):
    window.project_name.setText("保留编辑")
    path = tmp_path / "损坏.tdproj"
    path.write_text("{invalid", encoding="utf-8")
    errors = []
    monkeypatch.setattr(window, "_Error_Show", errors.append)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (str(path), ""))
    window._Project_Open()
    assert errors and window.project_name.text() == "保留编辑" and window.session.dirty
    assert window.Project_LoadPath(path).result == ProjectIoResult.Invalid


def test_dirty_cancel_new_close_and_failed_save_preserve_window(window, app, monkeypatch):
    window.project_name.setText("尚未保存")
    before = window.session.project

    def choose(label):
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, QMessageBox)
        next(button for button in dialog.buttons() if button.text() == label).click()

    QTimer.singleShot(30, lambda: choose("取消"))
    window._Project_New()
    assert window.session.project == before
    QTimer.singleShot(30, lambda: choose("取消"))
    assert not window.close()
    assert window.isVisible() and window.session.project == before
    monkeypatch.setattr(window, "_Project_Save", lambda save_as: False)
    QTimer.singleShot(30, lambda: choose("保存"))
    window._Project_New()
    assert window.session.project == before
    QTimer.singleShot(30, lambda: choose("放弃更改"))
    window._Project_New()
    assert window.session.project != before

