"""VideoScribe — транскрибация видео и аудио (YouTube-ссылки и локальные файлы).

Запуск:  python main.py   (или run.bat на Windows)
"""
from __future__ import annotations

import sys


def _report_startup_error(text: str) -> None:
    """Показать ошибку запуска даже без консоли (pythonw) и сохранить её в лог."""
    log_path = ""
    try:
        import os
        from pathlib import Path
        base = os.environ.get("APPDATA") or str(Path.home())
        d = Path(base) / "VideoScribe"
        d.mkdir(parents=True, exist_ok=True)
        p = d / "startup-error.log"
        p.write_text(text, encoding="utf-8")
        log_path = str(p)
    except Exception:
        pass

    msg = ("Программа не смогла запуститься. / The app failed to start.\n\n"
           + text[-1200:])
    if log_path:
        msg += "\n\nЛог сохранён: " + log_path

    shown = False
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, "VideoScribe — ошибка запуска", 0x10)
            shown = True
        except Exception:
            pass
    if not shown:
        try:
            if sys.stderr:
                print(msg, file=sys.stderr)
        except Exception:
            pass


def main() -> int:
    from PySide6.QtWidgets import QApplication

    # Язык интерфейса — до создания окон
    from app import i18n
    from app.config import AppConfig
    cfg = AppConfig.load()
    i18n.set_language(cfg.ui_lang)

    from app.gui.main_window import MainWindow
    from app.gui.style import apply_style

    app = QApplication(sys.argv)
    app.setApplicationName("VideoScribe")
    app.setOrganizationName("VideoScribe")
    apply_style(app, cfg.ui_theme)

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
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        import traceback
        _report_startup_error(traceback.format_exc())
        sys.exit(1)
