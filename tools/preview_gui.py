"""渲染本项目自己的 GUI 截图；不读取桌面或其他应用。"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.dont_write_bytecode = True
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))

from PySide6.QtWidgets import QApplication
from treediagram.ui import MainWindow

app = QApplication([])
window = MainWindow()
output = root / ".qa"
output.mkdir(exist_ok=True)
window.show()
for theme, index in (("light", 0), ("dark", 1)):
    window.theme_combo.setCurrentIndex(index)
    for page, width, height, name in (
        (0, 1180, 780, "overview"), (2, 1180, 780, "placeholder"), (0, 920, 620, "compact"),
    ):
        window.resize(width, height)
        window.navigation.setCurrentRow(page)
        app.processEvents()
        target = output / f"{theme}-{name}.png"
        assert window.grab().save(str(target)), target
        print(target)
window.close()

