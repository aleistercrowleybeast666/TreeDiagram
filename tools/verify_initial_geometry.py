"""Observe the real App_Main startup without adjusting its initial geometry."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument("--expect-fit", action="store_true")
parser.add_argument("--rapid-close", action="store_true")
args = parser.parse_args()
output = args.output.resolve()
output.mkdir(parents=True, exist_ok=False)
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QTimer, qVersion
from PySide6.QtWidgets import QApplication
from treediagram import app as application

record = {
    "source_sha256": hashlib.sha256(Path(application.__file__).read_bytes()).hexdigest(),
    "qt": qVersion(), "python": sys.executable,
    "entry": "treediagram.app.App_Main", "fit_calls": [], "errors": [],
    "initial_geometry_changed_by_probe": False, "user_project_opened": False,
    "settings": "The application has no persisted GUI settings; empty default project",
}
original_show = application.MainWindow.show
original_fit = getattr(application, "App_ConstrainInitialGeometry", None)


def Rectangle_Get(rectangle):
    return [rectangle.x(), rectangle.y(), rectangle.width(), rectangle.height()]


def Snapshot_Get(window):
    available = window.screen().availableGeometry()
    frame = window.frameGeometry()
    status = window.statusBar()
    return {
        "dpr": window.devicePixelRatioF(), "available": Rectangle_Get(available),
        "frame": Rectangle_Get(frame), "client": Rectangle_Get(window.geometry()),
        "contained": available.contains(frame), "maximized": window.isMaximized(),
        "status_contained": all(available.contains(status.mapToGlobal(point))
                                for point in (status.rect().topLeft(), status.rect().bottomRight())),
        "overflow": {"right": max(0, frame.right() - available.right()),
                     "bottom": max(0, frame.bottom() - available.bottom())},
    }


def Fit_Observe(window):
    before = Snapshot_Get(window)
    original_fit(window)
    record["fit_calls"].append({"before": before, "after": Snapshot_Get(window)})


if original_fit is not None:
    application.App_ConstrainInitialGeometry = Fit_Observe


def Callback_Guard(function):
    def Invoke():
        try:
            function()
        except Exception:
            record["errors"].append(traceback.format_exc())
            QApplication.instance().exit(91)
    return Invoke


def View_Change(window):
    record["first_show"] = Snapshot_Get(window)
    if args.expect_fit:
        assert record["first_show"]["contained"] and record["first_show"]["status_contained"]
        assert len(record["fit_calls"]) == 2
    record["project_before_view"] = repr(window.session.project)
    window.theme_combo.setCurrentIndex(1)
    window.navigation.setCurrentRow(2)
    window.navigation.setCurrentRow(0)


def Run_Finish(window):
    record["after_view"] = Snapshot_Get(window)
    assert record["after_view"]["frame"] == record["first_show"]["frame"]
    assert record.pop("project_before_view") == repr(window.session.project)
    assert not window.session.dirty
    if args.expect_fit:
        assert len(record["fit_calls"]) == 2
    record["normal_close_accepted"] = window.close()
    assert record["normal_close_accepted"]


def Window_Show(window):
    record["platform"] = QApplication.platformName()
    record["before_show"] = Snapshot_Get(window)
    original_show(window)
    if args.rapid_close:
        def Close():
            record["normal_close_accepted"] = window.close()
        QTimer.singleShot(0, window, Callback_Guard(Close))
    else:
        QTimer.singleShot(1200, window, Callback_Guard(lambda: View_Change(window)))
        QTimer.singleShot(2400, window, Callback_Guard(lambda: Run_Finish(window)))
    QTimer.singleShot(15000, QApplication.instance(), lambda: QApplication.instance().exit(93))


application.MainWindow.show = Window_Show
try:
    sys.argv = [str(ROOT / "run.py")]
    code = application.App_Main()
    record["exit_code"] = code
    assert code == 0 and not record["errors"]
except Exception:
    record["errors"].append(traceback.format_exc())
    code = 90
(output / "receipt.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"exit": code, "first_show": record.get("first_show"), "errors": record["errors"]}, ensure_ascii=False), flush=True)
raise SystemExit(code)
