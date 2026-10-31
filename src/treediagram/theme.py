"""TreeDiagram 独立主题；配色与布局参照 FLP，不导入相邻工程。"""
from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication, QWidget


def Theme_Apply(app: QApplication, dark: bool) -> None:
    # Windows 的 offscreen Qt 平台不枚举系统字体，显式引用原字体文件即可。
    # 不复制字体，也不创建额外字体缓存/环境。
    if "Microsoft YaHei UI" not in QFontDatabase.families() and sys.platform == "win32":
        font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "msyh.ttc"
        if font_path.is_file():
            QFontDatabase.addApplicationFont(str(font_path))
    brand = "#0B2447" if dark else "#123A78"
    hover = "#163B6C" if dark else "#1C4F94"
    accent = "#3B82F6" if dark else "#2F6FED"
    background = "#0F172A" if dark else "#F4F6FA"
    surface = "#182235" if dark else "#FFFFFF"
    alternate = "#1E293B" if dark else "#E7ECF4"
    text = "#E5E7EB" if dark else "#172033"
    muted = "#94A3B8" if dark else "#64748B"
    border = "#475569" if dark else "#D7DFEB"
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    palette = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, background), (QPalette.ColorRole.WindowText, text),
        (QPalette.ColorRole.Base, surface), (QPalette.ColorRole.AlternateBase, alternate),
        (QPalette.ColorRole.Text, text), (QPalette.ColorRole.Button, surface),
        (QPalette.ColorRole.ButtonText, text), (QPalette.ColorRole.Highlight, accent),
        (QPalette.ColorRole.HighlightedText, "#FFFFFF"),
        (QPalette.ColorRole.ToolTipBase, surface), (QPalette.ColorRole.ToolTipText, text),
        (QPalette.ColorRole.PlaceholderText, muted),
    ):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(f"""
        QMainWindow, QWidget#centralRoot, QStackedWidget, QScrollArea,
        QScrollArea > QWidget > QWidget {{ background: {background}; color: {text}; }}
        QDialog, QMessageBox, QFileDialog {{ background: {surface}; color: {text}; }}
        QLabel, QCheckBox {{ background: transparent; color: {text}; }}
        QLabel#muted {{ color: {muted}; }}
        QFrame#headerBar, QFrame#sidebar {{ background: {brand}; border: none; }}
        QFrame#headerBar QLabel {{ color: #FFFFFF; }}
        QLabel#headerTitle {{ font-size: 20px; font-weight: 700; }}
        QLabel#headerVersion, QLabel#headerStage {{ color: #DCEAFF; }}
        QLabel#pageTitle {{ font-size: 20px; font-weight: 600; }}
        QComboBox#headerCombo {{ background: {hover}; color: #FFFFFF;
            border: 1px solid #6F91BE; min-width: 78px; }}
        QComboBox#headerCombo:hover {{ background: {accent}; }}
        QAbstractItemView#headerComboPopup {{ background: {brand}; color: #FFFFFF;
            selection-background-color: {accent}; selection-color: #FFFFFF; outline: none; }}
        QAbstractItemView#headerComboPopup::item {{ background: {brand}; color: #FFFFFF; min-height: 28px; padding: 3px 6px; }}
        QAbstractItemView#headerComboPopup::item:selected {{ background: {accent}; color: #FFFFFF; }}
        QListWidget#navigation {{ background: {brand}; color: #FFFFFF; border: none; outline: none; font-size: 14px; }}
        QListWidget#navigation::item {{ padding: 13px 14px; margin: 0; border-bottom: 1px solid {hover}; }}
        QListWidget#navigation::item:hover {{ background: {hover}; }}
        QListWidget#navigation::item:selected {{ background: {accent}; color: #FFFFFF; }}
        QGroupBox {{ background: {surface}; color: {text}; border: 1px solid {border};
            border-radius: 6px; margin-top: 12px; padding: 12px; font-weight: 600; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px; color: {accent}; }}
        QLineEdit, QPlainTextEdit, QComboBox, QTableWidget {{ background: {surface}; color: {text};
            border: 1px solid {border}; border-radius: 4px; selection-background-color: {accent}; selection-color: #FFFFFF; }}
        QLineEdit, QComboBox {{ min-height: 25px; padding: 3px 6px; }}
        QPlainTextEdit {{ padding: 6px; }}
        QHeaderView::section {{ background: {alternate}; color: {text}; padding: 6px;
            border: none; border-bottom: 1px solid {border}; }}
        QTableWidget {{ gridline-color: {border}; alternate-background-color: {alternate}; }}
        QTableWidget::item:selected {{ background: {accent}; color: #FFFFFF; }}
        QTabWidget::pane {{ border: 1px solid {border}; background: {surface}; }}
        QTabBar::tab {{ background: {brand}; color: #FFFFFF; padding: 8px 16px; }}
        QTabBar::tab:selected {{ background: {accent}; color: #FFFFFF; }}
        QTabBar::tab:hover {{ background: {hover}; }}
        QPushButton {{ background: {surface}; color: {text}; border: 1px solid {border}; padding: 6px 14px; border-radius: 4px; }}
        QPushButton:hover {{ border-color: {accent}; background: {alternate}; }}
        QMenuBar, QMenu {{ background: {brand}; color: #FFFFFF; }}
        QMenuBar::item:selected, QMenu::item:selected {{ background: {accent}; color: #FFFFFF; }}
        QMenu::item {{ padding: 7px 28px 7px 14px; }}
        QMenu::separator {{ height: 1px; background: #315A94; margin: 4px; }}
        QStatusBar {{ background: {alternate}; color: {text}; }}
        QScrollArea {{ border: none; }}
    """)


def Caption_Apply(window: QWidget, dark: bool) -> None:
    if sys.platform != "win32" or QApplication.platformName() == "offscreen":
        return
    try:
        setter = ctypes.windll.dwmapi.DwmSetWindowAttribute
        setter.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
        setter.restype = ctypes.c_long
        for attribute, value in ((35, 0x47240B if dark else 0x783A12), (36, 0xFFFFFF)):
            color = ctypes.c_uint(value)
            setter(int(window.winId()), attribute, ctypes.byref(color), ctypes.sizeof(color))
    except (OSError, AttributeError):
        pass

