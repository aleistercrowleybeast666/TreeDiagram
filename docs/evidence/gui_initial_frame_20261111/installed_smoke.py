from pathlib import Path
import hashlib
import json
import os
import sys
import traceback
import zipfile

root = Path('D:/python_software/TreeDiagram')
work = root / '.test-tmp/gui-initial-frame-20261111'
target = work / 'installed'
sys.path.insert(0, str(target))
os.environ['TREEDIAGRAM_CACHE'] = str(work / 'installed-native-cache')
assert not Path(os.environ['TREEDIAGRAM_CACHE']).exists()
import treediagram
from treediagram import app as application
from treediagram.algorithms.native import Native_Load
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

assert Path(treediagram.__file__).resolve().is_relative_to(target.resolve())
assert Path(application.__file__).resolve().is_relative_to(target.resolve())
wheel = root / 'dist/gui-initial-frame-20261111/treediagram_workbench-0.1.0-py3-none-any.whl'
matched = {}
with zipfile.ZipFile(wheel) as archive:
    expected = {p.relative_to(root / 'src').as_posix(): p for p in (root / 'src/treediagram').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    actual = {name for name in archive.namelist() if name.startswith('treediagram/') and not name.endswith('/')}
    assert actual == set(expected)
    for name, path in expected.items():
        contents = path.read_bytes()
        assert archive.read(name) == contents
        assert (target / name).read_bytes() == contents
        matched[name] = hashlib.sha256(contents).hexdigest()
library = Native_Load()
library_path = Path(library._name)
build = json.loads(library_path.with_name('build.json').read_text())
assert build['returncode'] == 0 and not build['stderr']
record = {
    'wheel': str(wheel), 'bytes': wheel.stat().st_size,
    'sha256': hashlib.sha256(wheel.read_bytes()).hexdigest(),
    'isolated_python': sys.flags.isolated,
    'installed_from': str(Path(treediagram.__file__).resolve()),
    'matched_sources': matched,
    'native_implementation': library._treediagram_identity,
    'library_sha256': hashlib.sha256(library_path.read_bytes()).hexdigest(),
    'fresh_build': build,
    'errors': [],
}
original_show = application.MainWindow.show

def Finish(window):
    try:
        available = window.screen().availableGeometry()
        frame = window.frameGeometry()
        record['native_gui'] = {
            'platform': QApplication.platformName(), 'dpr': window.devicePixelRatioF(),
            'available': [available.x(), available.y(), available.width(), available.height()],
            'frame': [frame.x(), frame.y(), frame.width(), frame.height()],
            'contained': available.contains(frame),
        }
        assert record['native_gui']['platform'] == 'windows'
        assert record['native_gui']['contained']
        record['normal_close'] = window.close()
        assert record['normal_close']
    except Exception:
        record['errors'].append(traceback.format_exc())
        QApplication.instance().exit(90)

def Show(window):
    original_show(window)
    QTimer.singleShot(1200, window, lambda: Finish(window))

application.MainWindow.show = Show
sys.argv = [str(target / 'treediagram/app.py')]
record['exit_code'] = application.App_Main()
(work / 'packaging.json').write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'sources': len(matched), 'wheel_sha256': record['sha256'], 'native_gui': record.get('native_gui'), 'exit_code': record['exit_code'], 'errors': record['errors']}), flush=True)
assert record['exit_code'] == 0 and not record['errors']
