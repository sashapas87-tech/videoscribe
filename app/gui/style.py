"""Темы приложения (QSS): тёмная и светлая."""
from __future__ import annotations

from string import Template

_current_theme = "dark"

# Палитры. Ключи одинаковые — QSS собирается из шаблона подстановкой.
DARK = {
    "window": "#17181d",
    "text": "#e6e7eb",
    "muted": "#8b8e98",
    "muted2": "#a7aab4",
    "field": "#23242c",
    "border": "#33353f",
    "panel": "#1c1d24",
    "panel_border": "#2b2d36",
    "btn": "#2b2d36",
    "btn_border": "#3a3c47",
    "btn_hover": "#343641",
    "btn_pressed": "#23242c",
    "btn_disabled_text": "#6a6d78",
    "accent": "#3d6df2",
    "accent_hover": "#5480f4",
    "accent_focus": "#4f8cff",
    "primary_disabled_bg": "#2b3a63",
    "primary_disabled_text": "#8b8e98",
    "selection": "#2c3a5e",
    "hover_item": "#262833",
    "tab_text": "#9a9daa",
    "progress_text": "#cfd1d8",
    "group_title": "#b8bac4",
    "danger": "#ff7b7b",
    "ok": "#4ade80",
    "warn": "#facc15",
    "link": "#7c9bff",
}

LIGHT = {
    "window": "#f5f6f8",
    "text": "#1b1d23",
    "muted": "#6b6f7b",
    "muted2": "#565a66",
    "field": "#ffffff",
    "border": "#c9ccd4",
    "panel": "#ffffff",
    "panel_border": "#dcdee4",
    "btn": "#e9eaee",
    "btn_border": "#c9ccd4",
    "btn_hover": "#dfe1e7",
    "btn_pressed": "#d3d6dd",
    "btn_disabled_text": "#9aa0ab",
    "accent": "#3d6df2",
    "accent_hover": "#5480f4",
    "accent_focus": "#3d6df2",
    "primary_disabled_bg": "#b9c6ea",
    "primary_disabled_text": "#f2f4fa",
    "selection": "#dbe5ff",
    "hover_item": "#eceef2",
    "tab_text": "#6b6f7b",
    "progress_text": "#3a3d45",
    "group_title": "#4a4d57",
    "danger": "#c62828",
    "ok": "#16a34a",
    "warn": "#b45309",
    "link": "#2f5ce0",
}

THEMES = {"dark": DARK, "light": LIGHT}

_QSS = Template("""
* { font-family: "Segoe UI", "Inter", sans-serif; font-size: 13px; }

QMainWindow, QDialog { background: $window; }
QWidget { color: $text; }

QLabel#hint { color: $muted; font-size: 14px; }
QLabel#engineLabel { color: $muted; }
QLabel#jobInfo { color: $muted2; }

QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {
    background: $field; border: 1px solid $border; border-radius: 6px;
    padding: 6px 8px; selection-background-color: $accent;
}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus { border-color: $accent_focus; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: $field; border: 1px solid $border;
    selection-background-color: $accent;
}

QPushButton {
    background: $btn; border: 1px solid $btn_border; border-radius: 6px;
    padding: 7px 14px;
}
QPushButton:hover { background: $btn_hover; }
QPushButton:pressed { background: $btn_pressed; }
QPushButton:disabled { color: $btn_disabled_text; background: $btn_pressed; }
QPushButton#primary {
    background: $accent; border-color: $accent; color: white; font-weight: 600;
}
QPushButton#primary:hover { background: $accent_hover; }
QPushButton#primary:disabled { background: $primary_disabled_bg; color: $primary_disabled_text; }
QPushButton#danger { color: $danger; }

QListWidget {
    background: $panel; border: 1px solid $panel_border; border-radius: 8px;
    padding: 4px;
}
QListWidget::item { padding: 8px; border-radius: 6px; margin: 2px; }
QListWidget::item:selected { background: $selection; color: $text; }
QListWidget::item:hover { background: $hover_item; }

QTableWidget {
    background: $panel; border: 1px solid $panel_border; border-radius: 8px;
    gridline-color: $panel_border;
}
QTableWidget::item { padding: 4px; }
QTableWidget::item:selected { background: $selection; color: $text; }
QHeaderView::section {
    background: $field; border: none; border-bottom: 1px solid $border;
    padding: 6px; font-weight: 600;
}
QTableCornerButton::section { background: $field; border: none; }

QTabWidget::pane { border: 1px solid $panel_border; border-radius: 8px; top: -1px; }
QTabBar::tab {
    background: transparent; padding: 8px 16px; color: $tab_text;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected { color: $text; border-bottom-color: $accent_focus; }

QProgressBar {
    background: $field; border: 1px solid $border; border-radius: 6px;
    text-align: center; color: $progress_text; min-height: 14px; max-height: 16px;
}
QProgressBar::chunk { background: $accent; border-radius: 5px; }

QGroupBox {
    border: 1px solid $panel_border; border-radius: 8px; margin-top: 12px;
    padding: 10px; padding-top: 16px; font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: $group_title; }

QCheckBox, QRadioButton { spacing: 7px; }
QCheckBox::indicator, QRadioButton::indicator { width: 16px; height: 16px; }

QStatusBar { background: $panel; border-top: 1px solid $panel_border; }
QSplitter::handle { background: $panel_border; width: 2px; }
QScrollBar:vertical { background: transparent; width: 10px; }
QScrollBar::handle:vertical { background: $btn_border; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QToolTip { background: $btn; color: $text; border: 1px solid $btn_border; }
""")


def current_theme() -> str:
    return _current_theme


def theme_colors(theme: str | None = None) -> dict:
    """Палитра темы (по умолчанию — текущей). Для окон с ручными цветами."""
    return dict(THEMES.get(theme or _current_theme, DARK))


def apply_style(app, theme: str = "dark") -> None:
    """Применить тему к приложению. Можно вызывать повторно — тема сменится сразу."""
    global _current_theme
    _current_theme = theme if theme in THEMES else "dark"
    app.setStyle("Fusion")
    app.setStyleSheet(_QSS.substitute(**THEMES[_current_theme]))
