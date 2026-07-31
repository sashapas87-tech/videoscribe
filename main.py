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

    # При первом запуске без активации — окно с Machine ID и полем для ключа
    try:
        from app import licensing
        if not licensing.load_status().licensed:
            from app.gui.license_dialog import LicenseDialog
            LicenseDialog(win).exec()
            win._update_license_label()
    except Exception:
        pass

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
