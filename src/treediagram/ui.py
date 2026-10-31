"""FLP 风格的最小中文 GUI 外壳；不启用业务计算或后台插件。"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QFileDialog, QFormLayout, QFrame,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListView, QListWidget,
    QMainWindow, QMessageBox, QPlainTextEdit, QScrollArea, QSizePolicy, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import __version__
from .core.session import ProjectSession
from .core.storage import ProjectIoOutcome, ProjectIoResult, Project_Load
from .theme import Caption_Apply, Theme_Apply


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.session = ProjectSession()
        self._loading = False
        self.setWindowTitle("TreeDiagram")
        self.resize(1180, 780)
        self.setMinimumSize(920, 620)
        self._Ui_Build()
        self._Theme_Select()
        self._View_LoadProject()

    def _Ui_Build(self) -> None:
        shell = QWidget()
        shell.setObjectName("centralRoot")
        root = QVBoxLayout(shell)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        header = QFrame()
        header.setObjectName("headerBar")
        header.setMinimumHeight(54)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 6, 14, 6)
        header_layout.setSpacing(10)
        self.title_label = QLabel("TreeDiagram")
        self.title_label.setObjectName("headerTitle")
        self.version_label = QLabel(f"v{__version__}")
        self.version_label.setObjectName("headerVersion")
        stage = QLabel("六自由度工程工作台")
        stage.setObjectName("headerStage")
        self.project_label = QLabel()
        self.project_label.setTextFormat(Qt.TextFormat.PlainText)
        self.project_label.setMinimumWidth(65)
        self.project_label.setMaximumWidth(210)
        self.project_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        for widget in (self.title_label, self.version_label, stage, QLabel("当前工程：")):
            header_layout.addWidget(widget)
        header_layout.addWidget(self.project_label, 1)
        header_layout.addStretch()
        header_layout.addWidget(QLabel("简体中文"))
        header_layout.addWidget(QLabel("主题"))
        self.theme_combo = QComboBox()
        self.theme_combo.setView(QListView())
        self.theme_combo.setObjectName("headerCombo")
        self.theme_combo.view().setObjectName("headerComboPopup")
        self.theme_combo.setMaxVisibleItems(10)
        self.theme_combo.addItems(["浅色", "深色"])
        self.theme_combo.currentIndexChanged.connect(self._Theme_Select)
        header_layout.addWidget(self.theme_combo)
        root.addWidget(header)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(190)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 8, 0, 8)
        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.navigation.addItems(["工程概览", "模型与装配", "任务与算法", "结果"])
        self.navigation.currentRowChanged.connect(self._Page_Select)
        sidebar_layout.addWidget(self.navigation)
        body_layout.addWidget(sidebar)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._Page_CreateOverview())
        from .workbench import Workbench
        self.workbench = Workbench(self)
        for page in (self.workbench.model_page, self.workbench.task_page, self.workbench.result_page):
            self.pages.addWidget(page)
        body_layout.addWidget(self.pages, 1)
        root.addWidget(body, 1)
        self.setCentralWidget(shell)
        self._Menu_Build()
        self.stage_status = QLabel("离线仿真  ·  实机资格独立验证")
        self.statusBar().addPermanentWidget(self.stage_status)

    def _Page_Wrap(self, page: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setWidget(page)
        return area

    def _Page_CreateOverview(self) -> QScrollArea:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)
        heading = QLabel("工程概览")
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)
        note = QLabel("从试车曲线与装配开始，运行真实六自由度模型，比较估计和控制结果。首次体验无需硬件或联网。")
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        basic = QGroupBox("工程信息")
        form = QFormLayout(basic)
        form.setSpacing(12)
        self.project_name = QLineEdit()
        self.project_name.setMaxLength(120)
        self.project_name.setPlaceholderText("输入工程名称")
        self.description = QPlainTextEdit()
        self.description.setMinimumHeight(100)
        self.description.setMaximumHeight(140)
        self.description.setPlaceholderText("记录模型目的、假设与适用范围。")
        self.path_label = QLabel()
        self.path_label.setTextFormat(Qt.TextFormat.PlainText)
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.file_state = QLabel()
        form.addRow("工程名称", self.project_name)
        form.addRow("工程备注", self.description)
        form.addRow("保存位置", self.path_label)
        form.addRow("保存状态", self.file_state)
        layout.addWidget(basic)
        modules = QGroupBox("工作区状态")
        modules_layout = QVBoxLayout(modules)
        self.module_table = self._Table_Create([
            ("工程概览", "可用", "编辑名称、备注；新建、打开、保存工程"),
            ("模型与装配", "可用", "离线示例、试车包、OpenRocket 几何子集；逐对象编辑"),
            ("任务与算法", "可用", "RK4 六自由度、模拟传感器、真实 C 估计 / PID / LQR"),
            ("结果", "可用", "轨迹、姿态、误差、执行器响应与独立运行快照"),
        ], ["工作区", "状态", "当前范围"])
        self.module_table.setFixedHeight(170)
        modules_layout.addWidget(self.module_table)
        layout.addWidget(modules)
        layout.addStretch()
        self.project_name.textChanged.connect(self._Project_EditMetadata)
        self.description.textChanged.connect(self._Project_EditMetadata)
        return self._Page_Wrap(page)

    def _Page_CreatePlaceholder(self, title: str, description: str, items) -> QScrollArea:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)
        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)
        group = QGroupBox("工作区占位 · 功能待定义")
        group_layout = QVBoxLayout(group)
        label = QLabel(description)
        label.setWordWrap(True)
        group_layout.addWidget(label)
        table = self._Table_Create(items, ["内容", "状态"])
        table.setFixedHeight(42 + len(items) * 32)
        group_layout.addWidget(table)
        layout.addWidget(group)
        layout.addStretch()
        return self._Page_Wrap(page)

    def _Table_Create(self, rows, labels) -> QTableWidget:
        table = QTableWidget(len(rows), len(labels))
        table.setHorizontalHeaderLabels(labels)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(32)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        for index, row in enumerate(rows):
            for column, text in enumerate(row):
                table.setItem(index, column, QTableWidgetItem(text))
        return table

    def _Menu_Build(self) -> None:
        file_menu = self.menuBar().addMenu("文件")
        self.file_actions = []
        for text, shortcut, callback in (
            ("新建工程", QKeySequence.StandardKey.New, self._Project_New),
            ("打开工程…", QKeySequence.StandardKey.Open, self._Project_Open),
            ("保存工程", QKeySequence.StandardKey.Save, lambda: self._Project_Save(False)),
            ("工程另存为…", QKeySequence.StandardKey.SaveAs, lambda: self._Project_Save(True)),
        ):
            action = QAction(text, self)
            action.setShortcut(shortcut)
            action.triggered.connect(callback)
            file_menu.addAction(action)
            self.file_actions.append(action)
        file_menu.addSeparator()
        file_menu.addAction("退出", self.close)
        help_menu = self.menuBar().addMenu("帮助")
        help_menu.addAction("关于 TreeDiagram", self._About_Show)

    def _About_Show(self) -> None:
        QMessageBox.about(self, "关于 TreeDiagram", f"TreeDiagram v{__version__}\n\n离线六自由度工程工作台\n真实 C 算法、声明式文件、可追溯结果。\n工程近似与实机验证范围请参阅 README。")

    def _Theme_Select(self) -> None:
        dark = self.theme_combo.currentIndex() == 1
        Theme_Apply(QApplication.instance(), dark)
        Caption_Apply(self, dark)

    def _Page_Select(self, index: int) -> None:
        if index >= 0:
            self.pages.setCurrentIndex(index)

    def _View_LoadProject(self) -> None:
        self._loading = True
        self.project_name.setText(self.session.project.name)
        self.description.setPlainText(self.session.project.description)
        self._loading = False
        self.navigation.setCurrentRow(0)
        self._View_RefreshStatus()
        self.workbench.Refresh()

    def _View_RefreshStatus(self) -> None:
        name = self.session.project.name or "未命名工程"
        compact = name if len(name) <= 18 else name[:17] + "…"
        self.project_label.setText(("* " if self.session.dirty else "") + compact)
        self.project_label.setToolTip(f"{name}\n{self.session.path or '尚未保存'}")
        self.file_state.setText("有未保存的更改" if self.session.dirty else ("已保存" if self.session.path else "新工程，尚未保存"))
        self.path_label.setText(str(self.session.path) if self.session.path else "尚未保存")
        self.statusBar().showMessage(f"{compact}  ·  {self.file_state.text()}")

    def _Project_EditMetadata(self) -> None:
        if not self._loading:
            self.session.Project_Set(replace(self.session.project, name=self.project_name.text(), description=self.description.toPlainText()))
            self._View_RefreshStatus()

    def _Error_Show(self, message: str) -> None:
        QMessageBox.warning(self, "TreeDiagram", message)

    def _Changes_ConfirmDiscard(self) -> bool:
        if not self.session.dirty:
            return True
        dialog = QMessageBox(self)
        dialog.setWindowTitle("尚有未保存的更改")
        dialog.setText("是否先保存当前工程？")
        save = dialog.addButton("保存", QMessageBox.ButtonRole.AcceptRole)
        discard = dialog.addButton("放弃更改", QMessageBox.ButtonRole.DestructiveRole)
        cancel = dialog.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(save)
        dialog.setEscapeButton(cancel)
        dialog.exec()
        if dialog.clickedButton() == save:
            return self._Project_Save(False)
        return dialog.clickedButton() == discard

    def _Project_New(self) -> None:
        if self._Changes_ConfirmDiscard():
            self.session.Project_New()
            self._View_LoadProject()

    def _Project_Open(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "打开 TreeDiagram 工程", "", "TreeDiagram 工程 (*.tdproj);;所有文件 (*)")
        if not filename:
            return
        # 先验证候选文件；损坏文件不触发放弃当前更改的提示。
        candidate = Project_Load(Path(filename))
        if candidate.result != ProjectIoResult.Success:
            self._Error_Show(candidate.message + "\n当前工程保持不变。")
            return
        if self._Changes_ConfirmDiscard():
            self.Project_LoadPath(Path(filename))

    def Project_LoadPath(self, path: Path) -> ProjectIoOutcome:
        outcome = self.session.Project_Open(path)
        if outcome.result == ProjectIoResult.Success:
            self._View_LoadProject()
        else:
            self._Error_Show(outcome.message + "\n当前工程保持不变。")
        return outcome

    def _Project_Save(self, save_as: bool) -> bool:
        target = self.session.path
        expected = None
        if save_as or target is None:
            filename, _ = QFileDialog.getSaveFileName(self, "保存 TreeDiagram 工程", str(target or Path("未命名工程.tdproj")), "TreeDiagram 工程 (*.tdproj)")
            if not filename:
                return False
            target = Path(filename)
            if target.suffix.lower() != ".tdproj":
                target = target.with_suffix(".tdproj")
            if target.exists() and target != self.session.path:
                existing = Project_Load(target)
                if existing.result != ProjectIoResult.Success:
                    self._Error_Show("目标文件无法安全校验，不能覆盖；请选择新文件名。")
                    return False
                answer = QMessageBox.question(self, "替换已有工程", "是否替换已有工程？上一版将保存到同名 .bak 文件。", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                if answer != QMessageBox.StandardButton.Yes:
                    return False
                expected = existing.digest
        outcome = self.session.Project_Save(target, expected)
        if outcome.result != ProjectIoResult.Success:
            self._Error_Show(outcome.message)
            return False
        self._View_RefreshStatus()
        return True

    def closeEvent(self, event):
        if self.workbench.busy:
            self.workbench.Run_Cancel()
            self.statusBar().showMessage("正在安全取消运行，请结束后再次关闭。")
            event.ignore()
            return
        if self._Changes_ConfirmDiscard():
            event.accept()
        else:
            event.ignore()

