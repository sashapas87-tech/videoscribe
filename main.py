"""VideoScribe — транскрибация видео и аудио (YouTube-ссылки и локальные файлы).

Запуск:  python main.py   (или run.bat на Windows)
"""
from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from app.gui.main_window import MainWindow
    from app.gui.style import apply_style

    app = QApplication(sys.argv)
    app.setApplicationName("VideoScribe")
    app.setOrganizationName("VideoScribe")
    apply_style(app)

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
