"""Тёмная тема приложения (QSS)."""
from __future__ import annotations

QSS = """
* { font-family: "Segoe UI", "Inter", sans-serif; font-size: 13px; }

QMainWindow, QDialog { background: #17181d; }
QWidget { color: #e6e7eb; }

QLabel#hint { color: #8b8e98; font-size: 14px; }
QLabel#engineLabel { color: #8b8e98; }
QLabel#jobInfo { color: #a7aab4; }

QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {
    background: #23242c; border: 1px solid #33353f; border-radius: 6px;
    padding: 6px 8px; selection-background-color: #3d6df2;
}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus { border-color: #4f8cff; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: #23242c; border: 1px solid #33353f;
    selection-background-color: #3d6df2;
}

QPushButton {
    background: #2b2d36; border: 1px solid #3a3c47; border-radius: 6px;
    padding: 7px 14px;
}
QPushButton:hover { background: #343641; }
QPushButton:pressed { background: #23242c; }
QPushButton:disabled { color: #6a6d78; background: #23242c; }
QPushButton#primary {
    background: #3d6df2; border-color: #3d6df2; color: white; font-weight: 600;
}
QPushButton#primary:hover { background: #5480f4; }
QPushButton#primary:disabled { background: #2b3a63; color: #8b8e98; }
QPushButton#danger { color: #ff7b7b; }

QListWidget {
    background: #1c1d24; border: 1px solid #2b2d36; border-radius: 8px;
    padding: 4px;
}
QListWidget::item { padding: 8px; border-radius: 6px; margin: 2px; }
QListWidget::item:selected { background: #2c3a5e; }
QListWidget::item:hover { background: #262833; }

QTableWidget {
    background: #1c1d24; border: 1px solid #2b2d36; border-radius: 8px;
    gridline-color: #2b2d36;
}
QTableWidget::item { padding: 4px; }
QTableWidget::item:selected { background: #2c3a5e; color: #e6e7eb; }
QHeaderView::section {
    background: #23242c; border: none; border-bottom: 1px solid #33353f;
    padding: 6px; font-weight: 600;
}
QTableCornerButton::section { background: #23242c; border: none; }

QTabWidget::pane { border: 1px solid #2b2d36; border-radius: 8px; top: -1px; }
QTabBar::tab {
    background: transparent; padding: 8px 16px; color: #9a9daa;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected { color: #e6e7eb; border-bottom-color: #4f8cff; }

QProgressBar {
    background: #23242c; border: 1px solid #33353f; border-radius: 6px;
    text-align: center; color: #cfd1d8; min-height: 14px; max-height: 16px;
}
QProgressBar::chunk { background: #3d6df2; border-radius: 5px; }

QGroupBox {
    border: 1px solid #2b2d36; border-radius: 8px; margin-top: 12px;
    padding: 10px; padding-top: 16px; font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #b8bac4; }

QCheckBox, QRadioButton { spacing: 7px; }
QCheckBox::indicator, QRadioButton::indicator { width: 16px; height: 16px; }

QStatusBar { background: #1c1d24; border-top: 1px solid #2b2d36; }
QSplitter::handle { background: #2b2d36; width: 2px; }
QScrollBar:vertical { background: transparent; width: 10px; }
QScrollBar::handle:vertical { background: #3a3c47; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QToolTip { background: #2b2d36; color: #e6e7eb; border: 1px solid #3a3c47; }
"""


def apply_style(app) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
