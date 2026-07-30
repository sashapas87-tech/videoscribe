"""Работа с ffmpeg: поиск бинарника, извлечение/конвертация аудио, тишина, нарезка."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from .models import AppError

ProgressCb = Optional[Callable[[float], None]]  # 0..100

_FFMPEG_CACHE: Optional[str] = None

# Скрыть консольные окна дочерних процессов на Windows
_POPEN_FLAGS = {}
if sys.platform == "win32":
    _POPEN_FLAGS["creationflags"] = 0x08000000  # CREATE_NO_WINDOW


def find_ffmpeg() -> str:
    """Ищем ffmpeg: рядом с exe (bin/) -> imageio-ffmpeg -> PATH."""
    global _FFMPEG_CACHE
    if _FFMPEG_CACHE:
        return _FFMPEG_CACHE

    candidates: List[str] = []
    exe_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) \
        else Path(__file__).resolve().parent.parent.parent
    name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    candidates.append(str(exe_dir / "bin" / name))

    for c in candidates:
        if Path(c).is_file():
            _FFMPEG_CACHE = c
            return c

    try:
        import imageio_ffmpeg  # type: ignore
        _FFMPEG_CACHE = imageio_ffmpeg.get_ffmpeg_exe()
        return _FFMPEG_CACHE
    except Exception:
        pass

    found = shutil.which("ffmpeg")
    if found:
        _FFMPEG_CACHE = found
        return found

    raise AppError(
        "Не найден ffmpeg. Установите зависимости (pip install -r requirements.txt) "
        "или положите ffmpeg.exe в папку bin рядом с программой."
    )


def _run(args: List[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        **_POPEN_FLAGS, **kw
    )


_DUR_RE = re.compile(r"Duration:\s*(\d+):(\d\d):(\d\d(?:\.\d+)?)")


def get_duration(path: str) -> float:
    """Длительность медиафайла в секундах (парсинг вывода ffmpeg -i)."""
    proc = _run([find_ffmpeg(), "-hide_banner", "-i", path])
    text = proc.stderr.decode("utf-8", errors="replace")
    m = _DUR_RE.search(text)
    if not m:
        raise AppError(f"Не удалось определить длительность файла: {Path(path).name}")
    h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return h * 3600 + mi * 60 + s


def _run_with_progress(args: List[str], total_duration: float, progress: ProgressCb,
                       cancelled: Optional[Callable[[], bool]] = None) -> None:
    """Запуск ffmpeg с '-progress pipe:1' и отчётом о проценте выполнения."""
    proc = subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **_POPEN_FLAGS
    )
    assert proc.stdout is not None
    try:
        for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").strip()
            if cancelled and cancelled():
                proc.kill()
                from .models import JobCancelled
                raise JobCancelled()
            if line.startswith("out_time_ms=") and total_duration > 0 and progress:
                try:
                    us = int(line.split("=", 1)[1])
                    progress(min(100.0, us / 1_000_000 / total_duration * 100))
                except ValueError:
                    pass
    finally:
        proc.stdout.close()
    stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
    code = proc.wait()
    if code != 0:
        tail = "\n".join(stderr.strip().splitlines()[-5:])
        raise AppError(f"Ошибка ffmpeg:\n{tail}")


def extract_wav(src: str, dst: str, progress: ProgressCb = None,
                cancelled: Optional[Callable[[], bool]] = None) -> None:
    """Извлечь аудиодорожку в WAV 16 кГц моно (формат для Whisper и pyannote)."""
    dur = get_duration(src)
    args = [
        find_ffmpeg(), "-hide_banner", "-y", "-i", src,
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        "-progress", "pipe:1", "-nostats", "-loglevel", "error",
        dst,
    ]
    _run_with_progress(args, dur, progress, cancelled)
    if not Path(dst).is_file() or Path(dst).stat().st_size < 1000:
        raise AppError("В файле не найдена аудиодорожка.")


def encode_chunk_mp3(src_wav: str, start: float, end: float, dst_mp3: str,
                     bitrate: str = "48k") -> None:
    """Вырезать фрагмент [start, end) из WAV и сжать в MP3 (для облачного API)."""
    args = [
        find_ffmpeg(), "-hide_banner", "-y",
        "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", src_wav,
        "-ac", "1", "-ar", "16000", "-b:a", bitrate,
        "-loglevel", "error", dst_mp3,
    ]
    proc = _run(args)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.decode("utf-8", "replace").strip().splitlines()[-5:])
        raise AppError(f"Ошибка сжатия аудио:\n{tail}")


_SIL_START_RE = re.compile(r"silence_start:\s*([\d.]+)")
_SIL_END_RE = re.compile(r"silence_end:\s*([\d.]+)")


def detect_silences(wav: str, noise_db: int = -35, min_dur: float = 0.4) -> List[Tuple[float, float]]:
    """Найти интервалы тишины (для аккуратной нарезки длинного аудио)."""
    args = [
        find_ffmpeg(), "-hide_banner", "-i", wav,
        "-af", f"silencedetect=noise={noise_db}dB:d={min_dur}",
        "-f", "null", "-",
    ]
    proc = _run(args)
    text = proc.stderr.decode("utf-8", errors="replace")
    silences: List[Tuple[float, float]] = []
    cur_start: Optional[float] = None
    for line in text.splitlines():
        ms = _SIL_START_RE.search(line)
        if ms:
            cur_start = float(ms.group(1))
            continue
        me = _SIL_END_RE.search(line)
        if me and cur_start is not None:
            silences.append((cur_start, float(me.group(1))))
            cur_start = None
    return silences
