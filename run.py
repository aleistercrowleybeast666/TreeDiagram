"""从源码启动；不安装包、不复制环境。"""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from treediagram.app import App_Main

if __name__ == "__main__":
    raise SystemExit(App_Main())

