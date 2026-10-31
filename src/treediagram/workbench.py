"""Engineering workspaces; edits commit validated drafts, jobs publish atomically."""
from __future__ import annotations

import copy
import json
import threading
from dataclasses import asdict, replace
from pathlib import Path
from uuid import uuid4

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QListWidget, QPlainTextEdit,
    QProgressBar, QPushButton, QScrollArea, QSlider, QSplitter, QTableWidget,
    QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QLineEdit,
    QMessageBox, QInputDialog, QHeaderView, QMenu, QTabWidget)

from .design import (ACTUATORS, PART_KINDS, Assembly_Aggregate, Design_CreateExample,
                     Design_Decode, Design_Digest, Design_Validate, Part)
from .importers import Motor_Import, Ork_Import
from .results import Run_Save
from .simulation import Simulation_Run, SimulationCancelled
from .views import EngineeringView, SignalView

LABELS={"none":"不启用","pid":"PID","lqr":"LQR","ins":"INS","sf6":"SF6","kf6":"KF6",
        "eskf15":"ESKF15","eskf20":"ESKF20","inekf15":"InEKF15","inekf20":"InEKF20",
        "gimbal":"主推力偏转","fin":"空气舵","wheel":"动量轮","rcs":"冷气推力对",
        "powered":"动力段","coast":"滑行段","descent":"下降段"}


def _Button(text, callback, layout):
    button = QPushButton(text)
    button.clicked.connect(callback)
    layout.addWidget(button)
    return button


def _Number(value, minimum=0., maximum=1e6, decimals=5):
    widget = QDoubleSpinBox()
    widget.setRange(minimum, maximum)
    widget.setDecimals(decimals)
    widget.setValue(value)
    return widget


class Workbench:
    def __init__(self, window):
        self.window = window
        self._thread = None
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._job = None
        self._progress = 0
        self._refreshing = False
        self.model_page = self._Model_Create()
        self.task_page = self._Task_Create()
        self.result_page = self._Results_Create()
        self.timer = QTimer(window)
        self.timer.timeout.connect(self.Job_Poll)
        self.timer.start(80)

    @property
    def design(self):
        data = self.window.session.project.design
        return Design_Decode(data) if data else None

    @property
    def busy(self):
        return self._thread is not None

    def Design_Commit(self, design):
        Design_Validate(design, runnable=False)
        self.window.session.Project_Set(replace(self.window.session.project, design=json.loads(json.dumps(asdict(design)))))
        self.Refresh()
        self.window._View_RefreshStatus()

    def _Model_Create(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        actions = QHBoxLayout()
        _Button("打开离线示例", self.Example_Open, actions)
        _Button("导入发动机…", self.Motor_Open, actions)
        _Button("导入 OpenRocket…", self.Ork_Open, actions)
        actions.addStretch()
        layout.addLayout(actions)
        splitter = QSplitter()
        left = QWidget()
        side = QVBoxLayout(left)
        side.setContentsMargins(0,0,0,0)
        self.parts = QTreeWidget()
        self.parts.setHeaderLabels(["零件 / 装配", "质量 kg"])
        self.parts.header().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        self.parts.header().setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        self.parts.itemDoubleClicked.connect(self.Part_Edit)
        self.parts.currentItemChanged.connect(self.Part_Select)
        self.parts.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.parts.customContextMenuRequested.connect(self.Part_Menu)
        side.addWidget(self.parts)
        buttons = QHBoxLayout()
        _Button("添加", self.Part_Add, buttons)
        _Button("属性", self.Part_Edit, buttons)
        _Button("删除", self.Part_Delete, buttons)
        side.addLayout(buttons)
        splitter.addWidget(left)
        self.model_view = EngineeringView()
        splitter.addWidget(self.model_view)
        details = QWidget()
        detail_layout = QVBoxLayout(details)
        self.part_info = QLabel("选择对象查看属性，双击编辑。")
        self.part_info.setWordWrap(True)
        self.part_info.setTextFormat(Qt.TextFormat.PlainText)
        detail_layout.addWidget(self.part_info)
        self.assembly_info = QLabel()
        self.assembly_info.setWordWrap(True)
        detail_layout.addWidget(self.assembly_info)
        _Button("发动机 / 质量模型…", self.Motor_Edit, detail_layout)
        _Button("推力曲线与来源…", self.Motor_SourceShow, detail_layout)
        _Button("审核导入缺项…", self.Issues_Review, detail_layout)
        detail_layout.addStretch()
        splitter.addWidget(details)
        splitter.setSizes([230, 420, 250])
        layout.addWidget(splitter, 1)
        self.issues = QListWidget()
        self.issues.setMaximumHeight(130)
        self.issues.itemClicked.connect(self.Issue_Locate)
        layout.addWidget(self.issues)
        return page

    def _Task_Create(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel("共享实例与阶段范围")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        capsule_row = QHBoxLayout()
        for key, label in (("powered", "动力段"), ("coast", "滑行段"), ("descent", "下降段")):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, value=key: self.Phase_Show(value))
            capsule_row.addWidget(button)
        layout.addLayout(capsule_row)
        self.instances = QTableWidget(3, 4)
        self.instances.setHorizontalHeaderLabels(["共享实例", "实现 / 输入", "开始", "结束（含）"])
        self.instances.horizontalHeader().setStretchLastSection(True)
        self.instances.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.instances.cellDoubleClicked.connect(lambda *_: self.Task_Edit())
        layout.addWidget(self.instances)
        actions = QHBoxLayout()
        _Button("算法与范围…", self.Task_Edit, actions)
        _Button("场景 / 气动…", self.Scenario_Edit, actions)
        _Button("传感器…", self.Sensors_Edit, actions)
        _Button("执行机构…", self.Actuator_Edit, actions)
        layout.addLayout(actions)
        self.scenario_info = QLabel()
        self.scenario_info.setWordWrap(True)
        layout.addWidget(self.scenario_info)
        self.run_button = _Button("运行六自由度仿真", self.Run_Start, layout)
        row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0,100)
        self.progress.setValue(0)
        row.addWidget(self.progress,1)
        self.cancel_button = _Button("取消运行", self.Run_Cancel, row)
        self.cancel_button.setEnabled(False)
        layout.addLayout(row)
        self.run_status = QLabel("打开完整示例即可离线运行。")
        self.run_status.setWordWrap(True)
        self.run_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.run_status)
        layout.addStretch()
        return page

    def _Results_Create(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        row = QHBoxLayout()
        self.run_select = QComboBox()
        self.run_select.currentIndexChanged.connect(self.Results_Refresh)
        row.addWidget(self.run_select,1)
        self.compare = QComboBox()
        self.compare.currentIndexChanged.connect(self.Results_Refresh)
        row.addWidget(self.compare,1)
        _Button("导出结果…", self.Result_Export, row)
        _Button("导出参数…", self.Parameters_Export, row)
        layout.addLayout(row)
        self.result_info = QLabel("尚无运行结果。")
        self.result_info.setWordWrap(True)
        layout.addWidget(self.result_info)
        splitter = QSplitter()
        self.result_view = EngineeringView()
        splitter.addWidget(self.result_view)
        charts = QWidget()
        chart_layout = QVBoxLayout(charts)
        self.signal_select = QComboBox()
        self.signal_select.addItems(["高度 / 估计高度 [m]", "三轴位置 [m]", "三轴速度 [m/s]", "姿态角 [deg]", "估计位置误差 [m]", "控制请求 / 实际力矩 [N·m]", "执行机构状态"])
        self.signal_select.currentIndexChanged.connect(self.Results_Refresh)
        chart_layout.addWidget(self.signal_select)
        self.signal_view = SignalView()
        chart_layout.addWidget(self.signal_view,1)
        splitter.addWidget(charts)
        splitter.setSizes([350,650])
        layout.addWidget(splitter,1)
        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.timeline.valueChanged.connect(self.Replay_Seek)
        layout.addWidget(self.timeline)
        self.events = QPlainTextEdit()
        self.events.setReadOnly(True)
        self.events.setMaximumHeight(125)
        layout.addWidget(self.events)
        return page

    def Refresh(self):
        self._refreshing = True
        design = self.design
        self.parts.clear()
        self.model_view.design, self.model_view.rows = design, []
        self.model_view.update()
        self.issues.clear()
        if design:
            items = {}
            for _ in design.parts:
                for part in design.parts:
                    if part.id in items or part.parent_id is not None and part.parent_id not in items:
                        continue
                    item = QTreeWidgetItem([part.name, "未知" if part.mass_kg is None else f"{part.mass_kg:g}"])
                    item.setData(0,Qt.ItemDataRole.UserRole,part.id)
                    item.setToolTip(0,part.name)
                    (items[part.parent_id] if part.parent_id else self.parts.invisibleRootItem()).addChild(item)
                    items[part.id] = item
            self.parts.expandAll()
            self.issues.addItems(Design_Validate(design,runnable=False) or ("输入齐备；仍需按假设解释仿真结果。",))
            try:
                mass,cg,inertia = Assembly_Aggregate(design.parts)
                self.assembly_info.setText(f"零件自身总质量 {mass:.4f} kg\n不含发动机及推进剂\n质心 Body {np.round(cg,4)} m\n主惯量 {np.round(np.linalg.eigvalsh(inertia),5)} kg·m²")
            except ValueError as exc:
                self.assembly_info.setText(str(exc))
            c = design.control
            rows = [("状态估计", LABELS[c.estimator]+" · 模拟传感器", "启动", "落地"),
                    ("姿态控制", LABELS[c.controller]+" → "+LABELS[c.actuator], LABELS[c.start_phase],LABELS[c.end_phase]),
                    ("结果记录", "真值 / 估计 / 输出", "启动","落地")]
            for i,row in enumerate(rows):
                for j,value in enumerate(row):
                    self.instances.setItem(i,j,QTableWidgetItem(value))
            self.instances.resizeColumnsToContents()
            self.scenario_info.setText(f"RK4 {design.scenario.step_us/1000:g} ms · 仿真 {design.scenario.duration_s:g} s · 随机种子 {design.scenario.seed}\n"
                f"IMU {1e6/design.sensors.imu_us:g} Hz · GNSS {1e6/design.sensors.gnss_us:g} Hz / 延迟 {design.sensors.gnss_delay_us/1000:g} ms\n"+"\n".join(design.assumptions))
        else:
            self.assembly_info.setText("尚未建立物理模型。")
            self.scenario_info.setText("请选择离线示例或导入模型。")
        self.run_button.setEnabled(design is not None and not self.busy)
        self.run_select.clear()
        self.compare.clear()
        self.compare.addItem("不比较",-1)
        for index, run in enumerate(self.window.session.project.flight_runs):
            text = f"运行 {index+1} · {LABELS[run['design']['control']['controller']]} · {run['summary']['maximum_altitude_m']:.1f} m"
            self.run_select.addItem(text,index)
            self.compare.addItem(text,index)
        self.run_select.setCurrentIndex(self.run_select.count()-1)
        self._refreshing = False
        self.Results_Refresh()

    def Example_Open(self):
        if self.design and QMessageBox.question(self.window,"打开示例","替换当前装配和场景？已有结果仍保留。") != QMessageBox.StandardButton.Yes:
            return
        self.Design_Commit(Design_CreateExample())

    def Part_Select(self,*_):
        item = self.parts.currentItem()
        if not item or not self.design:
            return
        part = next(p for p in self.design.parts if p.id == item.data(0,Qt.ItemDataRole.UserRole))
        self.part_info.setText(f"{part.name}\n类型 {part.kind}\n位置 {part.position_m} m\n长度 {part.length_m:g} m · 半径 {part.radius_m:g} m\n{part.provenance}\n每件质量仅计自身；子件另计。")

    def Issue_Locate(self,item):
        identity = item.text().split(":",1)[0].split(".",1)[0]
        for candidate in self.parts.findItems("*",Qt.MatchFlag.MatchWildcard|Qt.MatchFlag.MatchRecursive):
            if candidate.data(0,Qt.ItemDataRole.UserRole) == identity:
                self.parts.setCurrentItem(candidate)
                break

    def Part_Add(self):
        if not self.design:
            return
        kind,ok = QInputDialog.getItem(self.window,"添加零件","类型",PART_KINDS,0,False)
        if ok:
            part = Part(str(uuid4()),"新零件",kind,mass_kg=None)
            self.Part_EditDraft(part,new=True)

    def Part_Edit(self,*_):
        item = self.parts.currentItem()
        if item and self.design:
            part = next(p for p in self.design.parts if p.id == item.data(0,Qt.ItemDataRole.UserRole))
            self.Part_EditDraft(part)

    def Part_EditDraft(self,part,new=False):
        dialog = QDialog(self.window)
        dialog.setWindowTitle("零件属性 · "+part.name)
        form = QFormLayout(dialog)
        name = QLineEdit(part.name)
        form.addRow("名称",name)
        parent=QComboBox();parent.addItem("装配根",None)
        for candidate in self.design.parts:
            if candidate.id!=part.id:parent.addItem(candidate.name,candidate.id)
        parent.setCurrentIndex(max(0,parent.findData(part.parent_id)))
        form.addRow("父件",parent)
        editors = {}
        for key,label,value,minimum in (("mass_kg","自身质量 kg",part.mass_kg or 0.,0.),
                  ("length_m","长度 m",part.length_m,.000001),("radius_m","外半径 m",part.radius_m,.000001),
                  ("inner_radius_m","内半径 m",part.inner_radius_m,0.)):
            editors[key]=_Number(value,minimum)
            form.addRow(label,editors[key])
        xyz = [_Number(v,-1000,1000) for v in part.position_m]
        for key,widget in zip("XYZ",xyz):
            form.addRow(f"相对父件 {key} / m",widget)
        orientation=QLineEdit(json.dumps(part.rotation_wxyz))
        form.addRow("Local→Parent 四元数 wxyz",orientation)
        tensor = QLineEdit(json.dumps(part.inertia_kg_m2) if part.inertia_kg_m2 else "")
        tensor.setPlaceholderText("留空使用已声明均匀形状近似；或输入3×3张量")
        form.addRow("质心惯量 kg·m²",tensor)
        warning = QLabel("惯量相对本件质心、在本件坐标表达。质量为0视为未知。")
        warning.setWordWrap(True)
        form.addRow(warning)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Cancel)
        form.addRow(buttons)
        buttons.rejected.connect(dialog.reject)
        def apply():
            try:
                values={key:widget.value() for key,widget in editors.items()}
                values["mass_kg"] = values["mass_kg"] or None
                edited=replace(part,name=name.text(),parent_id=parent.currentData(),position_m=tuple(w.value() for w in xyz),rotation_wxyz=json.loads(orientation.text()),
                               inertia_kg_m2=json.loads(tensor.text()) if tensor.text().strip() else None,**values)
                parts=(*self.design.parts,edited) if new else tuple(edited if p.id==part.id else p for p in self.design.parts)
                self.Design_Commit(replace(self.design,parts=parts))
                dialog.accept()
            except (ValueError,TypeError) as exc:
                warning.setText(str(exc))
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(apply)
        dialog.exec()

    def Part_Menu(self,position):
        item=self.parts.itemAt(position)
        if not item or not self.design:return
        identity=item.data(0,Qt.ItemDataRole.UserRole)
        part=next(p for p in self.design.parts if p.id==identity)
        menu=QMenu(self.window)
        duplicate=menu.addAction("复制此零件（不含子件）")
        up=menu.addAction("上移显示顺序");down=menu.addAction("下移显示顺序")
        chosen=menu.exec(self.parts.viewport().mapToGlobal(position))
        if chosen==duplicate:
            self.Part_EditDraft(replace(part,id=str(uuid4()),name=part.name+" 副本"),new=True)
        elif chosen in (up,down):
            parts=list(self.design.parts);index=parts.index(part)
            target=index+(-1 if chosen==up else 1)
            if 0<=target<len(parts):
                parts[index],parts[target]=parts[target],parts[index]
                self.Design_Commit(replace(self.design,parts=tuple(parts)))

    def Part_Delete(self):
        item=self.parts.currentItem()
        if not item or not self.design:
            return
        identity=item.data(0,Qt.ItemDataRole.UserRole)
        if len(self.design.parts)==1 or any(p.parent_id==identity for p in self.design.parts):
            self.window._Error_Show("先移动或删除子件；模型必须保留至少一个零件。")
            return
        if QMessageBox.question(self.window,"删除零件","删除所选零件？旧运行快照仍保留。") == QMessageBox.StandardButton.Yes:
            self.Design_Commit(replace(self.design,parts=tuple(p for p in self.design.parts if p.id!=identity)))

    def Motor_Open(self):
        if not self.design:
            self.window._Error_Show("请先创建装配（可打开离线示例后替换发动机）。")
            return
        path,_=QFileDialog.getOpenFileName(self.window,"导入试车包","","Motor (*.tdmotor.json)")
        if not path:
            return
        try:
            candidate,changes=Motor_Import(Path(path),self.design)
            labels={"time_s":"时间轴","thrust_n":"推力曲线","propellant_mass_kg":"推进剂质量",
                    "dry_mass_kg":"发动机干质量","length_m":"长度","radius_m":"半径","source":"来源记录"}
            motor=candidate.motor
            summary=f"{len(motor.time_s)} 个运行样本 · 总冲 {np.trapezoid(motor.thrust_n,motor.time_s):.6g} N·s\n"
            summary+="改变："+"、".join(labels.get(key,key) for key in changes)+"\n安装、点火与偏转能力保留。\n"
            summary+="标定资格："+motor.source["package"]["calibration"]["status"]+"（不独立证明原始试车真实性）\n"
            if QMessageBox.question(self.window,"导入预览",summary+"\n"+"\n".join(Design_Validate(candidate,False))+"\n应用？") == QMessageBox.StandardButton.Yes:
                self.Design_Commit(candidate)
        except (ValueError,OSError,KeyError) as exc:
            self.window._Error_Show(str(exc))

    def Motor_SourceShow(self):
        if not self.design or not self.design.motor:return
        motor=self.design.motor
        dialog=QDialog(self.window);dialog.setWindowTitle("推力曲线与只读来源");dialog.resize(700,560)
        layout=QVBoxLayout(dialog);tabs=QTabWidget();layout.addWidget(tabs)
        plot=SignalView();plot.units="N"
        def series(label,x,y):
            step=max(1,int(np.ceil(len(x)/4096)))
            indices=sorted(set(range(0,len(x),step))|{len(x)-1})
            return label+("（显示抽样）" if step>1 else ""),[x[i] for i in indices],[y[i] for i in indices]
        plot.series=[series("当前仿真曲线",motor.time_s,motor.thrust_n)]
        metadata=copy.deepcopy(motor.source)
        package=metadata.get("package")
        if package:
            evidence=package["evidence_curve"]
            plot.series.append(series("原始导出证据",evidence["time_s"],evidence["thrust_n"]))
            for key in ("evidence_curve","simulation_curve"):
                curve=package.get(key)
                if curve:
                    package[key]={"sample_count":len(curve["time_s"]),"time_range_s":[curve["time_s"][0],curve["time_s"][-1]],
                                  "note":"完整数组保留于工程；此详情只显示摘要"}
        tabs.addTab(plot,"实际推力样本")
        text=QPlainTextEdit();text.setReadOnly(True);text.setPlainText(json.dumps(metadata,ensure_ascii=False,indent=2))
        tabs.addTab(text,"来源与处理详情")
        note=QLabel(f"运行曲线 {len(motor.time_s)} 点 · 实际时间积分 {np.trapezoid(motor.thrust_n,motor.time_s):.6g} N·s\n来源只读；显示抽样不修改科学数据。当前质量/安装近似由工程单独拥有。")
        note.setWordWrap(True);layout.addWidget(note)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        dialog.exec()

    def Motor_Edit(self):
        if not self.design or not self.design.motor:
            return
        motor=self.design.motor
        dialog=QDialog(self.window)
        dialog.setWindowTitle("发动机安装与质量假设")
        form=QFormLayout(dialog)
        editors={}
        for key,label in (("propellant_mass_kg","推进剂质量 kg"),("dry_mass_kg","干质量 kg"),("length_m","长度 m"),("radius_m","半径 m")):
            editors[key]=_Number(getattr(motor,key) or 0.)
            form.addRow(label,editors[key])
        xyz=[_Number(v,-1000,1000) for v in motor.position_m]
        for key,widget in zip("XYZ",xyz):form.addRow(key+" 安装 m",widget)
        orientation=QLineEdit(json.dumps(motor.rotation_bm_wxyz))
        form.addRow("Motor→Body 四元数 wxyz",orientation)
        capable=QCheckBox("此仿真发动机明确具备推力偏转能力")
        capable.setChecked(motor.gimbal_capable)
        form.addRow(capable)
        note=QLabel("质量消耗：冲量比例 / 均匀圆柱近似。不会修改来源证据包。")
        note.setWordWrap(True);form.addRow(note)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Cancel)
        form.addRow(buttons);buttons.rejected.connect(dialog.reject)
        def apply():
            try:
                values={k:w.value() for k,w in editors.items()}
                for key in ("propellant_mass_kg","dry_mass_kg"):values[key]=values[key] or None
                edited=replace(motor,position_m=tuple(w.value() for w in xyz),rotation_bm_wxyz=json.loads(orientation.text()),gimbal_capable=capable.isChecked(),**values)
                self.Design_Commit(replace(self.design,motor=edited));dialog.accept()
            except ValueError as exc:note.setText(str(exc))
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(apply)
        dialog.exec()

    def Ork_Open(self):
        path,_=QFileDialog.getOpenFileName(self.window,"导入 OpenRocket","","OpenRocket (*.ork)")
        if path:
            try:
                candidate=Ork_Import(Path(path))
                if QMessageBox.question(self.window,"几何导入预览",f"{len(candidate.parts)} 个部件；{len(candidate.import_issues)} 项需补齐。\n替换当前装配？") == QMessageBox.StandardButton.Yes:
                    self.Design_Commit(candidate)
            except (ValueError,OSError) as exc:self.window._Error_Show(str(exc))

    def Issues_Review(self):
        if not self.design or not self.design.import_issues:
            return
        dialog=QDialog(self.window);dialog.setWindowTitle("记录人工审核与补充模型")
        layout=QVBoxLayout(dialog)
        layout.addWidget(QLabel("仅勾选已用显式输入替代并核对的项目；未完成项继续阻止运行。"))
        checks=[]
        for issue in self.design.import_issues:
            box=QCheckBox(issue);layout.addWidget(box);checks.append(box)
        reason=QLineEdit();reason.setPlaceholderText("填写替代模型、依据与审核说明（必填）")
        layout.addWidget(reason)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons);buttons.rejected.connect(dialog.reject)
        def apply():
            if len(reason.text().strip())<8:return
            accepted=[b.text() for b in checks if b.isChecked()]
            candidate=replace(self.design,import_issues=tuple(b.text() for b in checks if not b.isChecked()),
                assumptions=(*self.design.assumptions,"人工覆盖："+reason.text()+"；"+"；".join(accepted)))
            self.Design_Commit(candidate);dialog.accept()
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(apply)
        dialog.exec()

    def Phase_Show(self,phase):
        descriptions={"powered":"点火至燃尽。离轨是瞬时事件，不另建长期阶段。", "coast":"燃尽至顶点。跨阶段的共享控制实例不会重新初始化。", "descent":"顶点至落地。结束范围包含本阶段，落地终止计算。"}
        QMessageBox.information(self.window,"阶段 · "+phase,descriptions[phase])

    def Task_Edit(self):
        if not self.design:return
        dialog=QDialog(self.window);dialog.setWindowTitle("算法与连续范围")
        dialog.resize(560,620)
        layout=QVBoxLayout(dialog);scroll=QScrollArea();scroll.setWidgetResizable(True)
        content=QWidget();form=QFormLayout(content);scroll.setWidget(content);layout.addWidget(scroll);combos={}
        c=self.design.control
        for key,label,choices in (("estimator","状态估计",("none","ins","sf6","kf6","eskf15","eskf20","inekf15","inekf20")),
                ("controller","控制器",("none","pid","lqr")),("actuator","执行机构",ACTUATORS),
                ("start_phase","开始",("powered","coast","descent")),("end_phase","结束（含）",("powered","coast","descent"))):
            box=QComboBox()
            for choice in choices:box.addItem(LABELS[choice],choice)
            box.setCurrentIndex(box.findData(getattr(c,key)));form.addRow(label,box);combos[key]=box
        numbers={}
        for key,label in (("kp","PID Kp · Nm/rad"),("ki","PID Ki · Nm/(rad·s)"),("kd","PID Kd · Nm·s/rad"),("torque_limit_nm","力矩上限 N·m"),
                          ("period_us","控制周期 µs"),
                          ("lqr_q_angle","LQR Q角度"),("lqr_q_rate","LQR Q角速度"),("lqr_r","LQR R")):
            widget=_Number(getattr(c,key));form.addRow(label,widget);numbers[key]=widget
        note=QLabel("控制仅绕 Body Y；输入为真实C估计姿态+陀螺。\nKF6姿态来自INS，不是KF6自身输出。增强核要求同时间GNSS；迟到量测会拒绝。\n执行机构仅为仿真模型；未接实物驱动。")
        note.setWordWrap(True);form.addRow(note)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Cancel);layout.addWidget(buttons)
        buttons.rejected.connect(dialog.reject)
        def apply():
            try:
                values={k:w.currentData() for k,w in combos.items()}|{k:w.value() for k,w in numbers.items()}
                values["period_us"]=int(values["period_us"])
                self.Design_Commit(replace(self.design,control=replace(c,**values)));dialog.accept()
            except ValueError as exc:note.setText(str(exc))
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(apply);dialog.exec()

    def _Fields_Edit(self,attribute,title,labels):
        if not self.design:return
        original=getattr(self.design,attribute)
        dialog=QDialog(self.window);dialog.setWindowTitle(title)
        layout=QVBoxLayout(dialog);scroll=QScrollArea();scroll.setWidgetResizable(True)
        content=QWidget();form=QFormLayout(content);scroll.setWidget(content);layout.addWidget(scroll)
        dialog.resize(560,600);editors={}
        for key,label in labels:
            value=getattr(original,key)
            if isinstance(value,(tuple,list)):
                row=QWidget();row_layout=QHBoxLayout(row);row_layout.setContentsMargins(0,0,0,0)
                widgets=[_Number(v,-1000000,1000000,10 if "rotation" in key else 6) for v in value]
                for widget in widgets:row_layout.addWidget(widget)
                editors[key]=widgets;form.addRow(label,row)
            else:
                widget=_Number(value,-1000000 if key=="launch_tilt_deg" else 0.,1000000,
                               0 if type(value) is int else 12 if key=="magnetic_std_t" else 6)
                editors[key]=widget;form.addRow(label,widget)
        error=QLabel();error.setWordWrap(True);layout.addWidget(error)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons);buttons.rejected.connect(dialog.reject)
        def apply():
            try:
                values={k:tuple(item.value() for item in w) if isinstance(w,list) else int(w.value()) if type(getattr(original,k)) is int else w.value() for k,w in editors.items()}
                self.Design_Commit(replace(self.design,**{attribute:replace(original,**values)}));dialog.accept()
            except ValueError as exc:error.setText(str(exc))
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(apply);dialog.exec()

    def Scenario_Edit(self):
        self._Fields_Edit("scenario","场景与气动近似",(("duration_s","时长 s"),("step_us","RK4 步长 µs"),
            ("seed","随机种子"),("launch_tilt_deg","导轨倾角 deg"),("rail_length_m","导轨长度 m"),
            ("wind_enu_mps","风 ENU / m/s"),("wind_shear_per_s","每米高度风梯度 /s"),("wind_gust_mps","确定性阵风幅值 m/s"),
            ("gravity_mps2","重力 m/s²"),("cp_body_m","压力中心 Body / m"),
            ("reference_area_m2","参考面积 m²"),("reference_length_m","参考长度 m"),
            ("drag_coefficient","阻力系数"),("normal_slope_per_rad","法向斜率 /rad"),("damping_coefficient","角速度阻尼系数")))

    def Sensors_Edit(self):
        self._Fields_Edit("sensors","模拟传感器 · 测量与到达时间分离",(("imu_us","IMU 周期 µs"),
            ("imu_delay_us","IMU 延迟 µs"),("gnss_us","GNSS 周期 µs"),("gnss_delay_us","GNSS 延迟 µs"),
            ("auxiliary_us","气压 / 磁场周期 µs"),("auxiliary_delay_us","气压 / 磁场延迟 µs"),
            ("pressure_std_pa","气压噪声标准差 Pa"),("magnetic_std_t","磁场噪声标准差 T"),
            ("rotation_bs_wxyz","传感器 → Body 四元数 wxyz"),
            ("accel_bias_mps2","加速度偏置 m/s²"),("gyro_bias_radps","陀螺偏置 rad/s"),
            ("accel_noise_std_mps2","离散加速度噪声标准差 m/s²"),("gyro_noise_std_radps","离散陀螺噪声标准差 rad/s"),
            ("position_std_m","GNSS 位置标准差 m"),("velocity_std_mps","GNSS 速度标准差 m/s")))

    def Actuator_Edit(self):
        if not self.design:return
        kind=self.design.control.actuator
        common=[]
        if kind in ("fin","rcs"):common.append(("actuator_position_m","安装位置 Body / m"))
        if kind in ("gimbal","fin","rcs"):common.append(("response_s","响应时间常数 s"))
        options={"gimbal":(("angle_limit_rad","偏转上限 rad"),("rate_limit_radps","变化率 rad/s")),
            "fin":(("fin_area_m2","舵面积 m²"),("fin_slope_per_rad","法向系数斜率 /rad"),("angle_limit_rad","偏转上限 rad"),("rate_limit_radps","变化率 rad/s")),
            "wheel":(("wheel_inertia_kg_m2","轮轴惯量 kg·m²"),("wheel_speed_limit_radps","轮速上限 rad/s")),
            "rcs":(("rcs_force_n","单只推力 N"),("rcs_propellant_kg","气体资源 kg"),("rcs_isp_s","比冲 s"),("minimum_pulse_s","最小脉冲 s"))}
        self._Fields_Edit("control",LABELS[kind]+" · 仿真模型",tuple(common)+options[kind])

    def Run_Start(self):
        if self.busy or not self.design:return
        try:Design_Validate(self.design)
        except ValueError as exc:self.window._Error_Show(str(exc));return
        if len(self.window.session.project.flight_runs)>=10:
            self.window._Error_Show("已保留10次运行，请导出结果并另建工程。");return
        snapshot=copy.deepcopy(self.design)
        self._cancel.clear();self._job=None;self._progress=0
        def progress(value):
            with self._lock:self._progress=value
        def work():
            try:outcome=("success",Simulation_Run(snapshot,self._cancel.is_set,progress))
            except SimulationCancelled as exc:outcome=("cancelled",str(exc))
            except Exception as exc:outcome=("failed",f"{type(exc).__name__}: {exc}")
            with self._lock:self._job=outcome
        self._thread=threading.Thread(target=work,name="TreeDiagram-6DoF",daemon=False)
        self._thread.start();self.run_button.setEnabled(False);self.cancel_button.setEnabled(True)
        for action in self.window.file_actions[:2]:action.setEnabled(False)
        self.run_status.setText("运行中 · 使用已提交快照；可继续查看模型。")

    def Run_Cancel(self):
        self._cancel.set();self.run_status.setText("正在取消；等待当前有界计算步结束。")

    def Job_Poll(self):
        if not self.busy:return
        with self._lock:outcome,progress=self._job,self._progress
        self.progress.setValue(progress)
        if outcome is None or self._thread.is_alive():return
        self._thread.join();self._thread=None
        state,value=outcome
        if state=="success" and not self._cancel.is_set():
            project=self.window.session.project
            self.window.session.Project_Set(replace(project,flight_runs=(*project.flight_runs,value)))
            self.run_status.setText(f"完成 · 最高 {value['summary']['maximum_altitude_m']:.2f} m · 已保存独立输入快照")
            self.window.navigation.setCurrentRow(3)
        else:self.run_status.setText("已取消；已有结果保留。" if self._cancel.is_set() else str(value))
        self.cancel_button.setEnabled(False)
        for action in self.window.file_actions[:2]:action.setEnabled(True)
        self.Refresh();self.window._View_RefreshStatus()

    def Results_Refresh(self,*_):
        if self._refreshing:return
        runs=self.window.session.project.flight_runs
        index=self.run_select.currentData()
        if index is None or not runs:
            self.result_view.design=None;self.result_view.rows=[];self.result_view.update()
            self.signal_view.series=[];self.signal_view.update();return
        run=runs[index];rows=run["rows"]
        self.result_view.design=Design_Decode(run["design"]);self.result_view.rows=rows
        self.timeline.setMaximum(len(rows)-1)
        self.Replay_Seek(self.timeline.value())
        stale=not self.design or Design_Digest(self.design)!=run["input_digest"]
        self.result_info.setText(f"{'历史配置 · 当前模型已改变' if stale else '当前配置结果'} | 最高 {run['summary']['maximum_altitude_m']:.2f} m | {run['summary']['duration_s']:.3f} s | {'已落地' if run['summary']['landed'] else '达到配置时长'}")
        signal=self.signal_select.currentIndex();times=[r["time_s"] for r in rows]
        series=[];unit="m"
        if signal==0:
            series=[("真值高度",times,[r["position_enu_m"][2] for r in rows])]
            selected=[r for r in rows if r["estimate_position_enu_m"] is not None]
            if selected:series.append(("估计高度",[r["time_s"] for r in selected],[r["estimate_position_enu_m"][2] for r in selected]))
        elif signal in (1,2):
            key="position_enu_m" if signal==1 else "velocity_enu_mps";unit="m" if signal==1 else "m/s"
            series=[(label,times,[r[key][i] for r in rows]) for i,label in enumerate(("East","North","Up"))]
        elif signal==3:
            unit="deg";angles=[]
            from .geometry import Quaternion_Matrix
            for r in rows:
                matrix=Quaternion_Matrix(r["q_nb"])
                angles.append(np.degrees([np.arctan2(matrix[2,1],matrix[2,2]),np.arcsin(np.clip(-matrix[2,0],-1,1)),np.arctan2(matrix[1,0],matrix[0,0])]))
            series=[(label,times,[a[i] for a in angles]) for i,label in enumerate(("Roll","Pitch","Yaw"))]
        elif signal==4:
            selected=[r for r in rows if r["estimate_position_enu_m"] is not None]
            series=[("估计误差范数",[r["time_s"] for r in selected],[np.linalg.norm(np.array(r["estimate_position_enu_m"])-r["position_enu_m"]) for r in selected])]
        elif signal==5:
            unit="N·m";series=[(label,times,[r[key] for r in rows]) for key,label in (("control_request_nm","请求"),("actuator_actual_nm","实际"))]
        else:
            actuator=run["design"]["control"]["actuator"]
            key,unit={"wheel":("wheel_momentum_nms","N·m·s"),"rcs":("rcs_used_kg","kg")}.get(actuator,("deflection_rad","rad"))
            series=[(actuator,times,[r[key] for r in rows])]
        comparison=self.compare.currentData()
        if comparison is not None and comparison>=0 and signal==0:
            other=runs[comparison]["rows"]
            series.append(("对比真值高度",[r["time_s"] for r in other],[r["position_enu_m"][2] for r in other]))
        self.signal_view.series,self.signal_view.units=series,unit;self.signal_view.update()
        self.events.setPlainText("\n".join(f"{e['time_s']:.6f} s  {e['event']}" for e in run["events"])+"\n"+"\n".join(run["diagnostics"]))

    def Replay_Seek(self,value):
        self.result_view.index=value;self.result_view.update()

    def Result_Export(self):
        index=self.run_select.currentData()
        if index is None:return
        path,_=QFileDialog.getSaveFileName(self.window,"导出结果","run.tdrun.json","Run (*.tdrun.json)")
        if path:
            try:Run_Save(Path(path),self.window.session.project.flight_runs[index])
            except (ValueError,OSError) as exc:self.window._Error_Show(str(exc))

    def Parameters_Export(self):
        index=self.run_select.currentData()
        if index is None:return
        path,_=QFileDialog.getSaveFileName(self.window,"导出参数包","tuning.sstuning.json","Tuning (*.sstuning.json)")
        if path:
            try:
                from .export import Parameters_ExportRun
                Parameters_ExportRun(self.window.session.project.flight_runs[index],Path(path))
            except (ValueError,OSError,RuntimeError) as exc:self.window._Error_Show(str(exc))
