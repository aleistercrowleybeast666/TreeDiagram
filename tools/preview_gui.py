"""渲染本项目自己的 GUI 截图；不读取桌面或其他应用。"""
import os
import sys
import argparse
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.dont_write_bytecode = True
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from treediagram.ui import MainWindow
from treediagram.design import Design_CreateExample
from treediagram.results import Run_Load
from dataclasses import replace

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path)
parser.add_argument("--run", type=Path)
args = parser.parse_args()
app = QApplication([])
window = MainWindow()
output = args.output or root / "docs/evidence/20261101" / ("scale-"+os.environ.get("QT_SCALE_FACTOR","1"))
output.mkdir(exist_ok=True,parents=True)
window.show()
window.workbench.Design_Commit(Design_CreateExample("pid"))
result_path=args.run or root/".qa/20261101/pid.tdrun.json"
if result_path.exists():
    run=Run_Load(result_path)
    window.session.Project_Set(replace(window.session.project,design=run["design"],flight_runs=(run,)))
    window.workbench.Refresh()
for theme, index in (("light", 0), ("dark", 1)):
    window.theme_combo.setCurrentIndex(index)
    for page, width, height, name in (
        (1, 1180, 780, "model"), (2, 1180, 780, "task"), (3,1180,780,"results"), (1, 920, 620, "compact"),
    ):
        window.resize(width, height)
        window.navigation.setCurrentRow(page)
        app.processEvents()
        target = output / f"offscreen-{theme}-{name}.png"
        assert window.grab().save(str(target)), target
        print(target)
    window.resize(1180, 780)
    for name, show in (("algorithm-dialog", window.workbench.Task_Edit),
                       ("motor-source", window.workbench.Motor_SourceShow)):
        def capture_dialog(name=name):
            dialog = app.activeModalWidget()
            assert dialog is not None
            target = output / f"offscreen-{theme}-{name}.png"
            assert dialog.grab().save(str(target)), target
            print(target)
            dialog.reject()
        QTimer.singleShot(100, capture_dialog)
        show()
window.session.dirty=False
window.close()

