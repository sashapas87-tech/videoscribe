"""Подготовка ресурсов приложения: шрифты DejaVu (для PDF) и иконка.

Запускается автоматически из run.bat, build.bat и CI. Повторный запуск безопасен:
уже существующие файлы не трогаются. Сеть нужна только для первого скачивания шрифтов.
"""
from __future__ import annotations

import io
import sys
import urllib.request
import zipfile
from pathlib import Path

# Windows-консоль/CI может быть в cp1252 — печать кириллицы не должна ронять скрипт
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = ROOT / "assets" / "fonts"
DEJAVU_URL = ("https://github.com/dejavu-fonts/dejavu-fonts/releases/download/"
              "version_2_37/dejavu-fonts-ttf-2.37.zip")
FONT_FILES = ["DejaVuSans.ttf", "DejaVuSans-Bold.ttf"]

QUIET = "--quiet" in sys.argv


def log(msg: str) -> None:
    if not QUIET:
        try:
            print(msg)
        except UnicodeEncodeError:
            print(msg.encode("ascii", "replace").decode("ascii"))


def ensure_fonts() -> None:
    missing = [f for f in FONT_FILES if not (FONTS_DIR / f).is_file()]
    if not missing:
        log("Шрифты уже на месте.")
        return
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    log(f"Скачивание шрифтов DejaVu ({', '.join(missing)})…")
    req = urllib.request.Request(DEJAVU_URL, headers={"User-Agent": "VideoScribe-setup"})
    data = urllib.request.urlopen(req, timeout=120).read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            base = name.rsplit("/", 1)[-1]
            if base in FONT_FILES:
                (FONTS_DIR / base).write_bytes(z.read(name))
                log(f"  сохранён {base}")
    still = [f for f in FONT_FILES if not (FONTS_DIR / f).is_file()]
    if still:
        raise SystemExit(f"Не удалось получить шрифты: {still}")


def ensure_icon() -> None:
    png = ROOT / "assets" / "icon.png"
    ico = ROOT / "assets" / "icon.ico"
    if png.is_file() and ico.is_file():
        log("Иконка уже на месте.")
        return
    try:
        from PIL import Image, ImageDraw  # type: ignore
    except ImportError:
        log("Pillow не установлен — пропускаю генерацию иконки "
            "(нужна только для сборки exe: pip install pillow).")
        return
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8, 8, 248, 248], radius=56, fill=(61, 109, 242, 255))
    heights = [56, 104, 152, 104, 56]
    w, gap = 20, 16
    x = (256 - (5 * w + 4 * gap)) // 2
    for h in heights:
        y0 = 128 - h // 2
        d.rounded_rectangle([x, y0, x + w, y0 + h], radius=10, fill=(255, 255, 255, 255))
        x += w + gap
    png.parent.mkdir(parents=True, exist_ok=True)
    img.save(png)
    img.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                         (64, 64), (128, 128), (256, 256)])
    log("Иконка сгенерирована (assets/icon.png, assets/icon.ico).")


if __name__ == "__main__":
    ensure_fonts()
    ensure_icon()
    log("Ресурсы готовы.")
