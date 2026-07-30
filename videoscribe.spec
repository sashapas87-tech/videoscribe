# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for VideoScribe (build on Windows: build.bat or CI)
from PyInstaller.utils.hooks import collect_all

datas = [("assets", "assets")]
binaries = []
hiddenimports = []

# Пакеты с данными/бинарниками, которые нужно собрать целиком.
# av/onnxruntime/ctranslate2 обычно подхватываются хуками, но собираем
# явно (в try) для надёжности на разных версиях.
for pkg in ["faster_whisper", "imageio_ffmpeg", "docx", "fpdf",
            "av", "onnxruntime", "ctranslate2"]:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Диаризация (torch/pyannote) в exe не пакуется - слишком тяжёлая.
    # Для диаризации запускайте программу из исходников (run.bat).
    excludes=["torch", "torchaudio", "pyannote", "matplotlib", "tkinter",
              "IPython", "jupyter", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="VideoScribe",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon="assets/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="VideoScribe",
)
