"""Получение исходного медиа: скачивание по ссылке (yt-dlp) или локальный файл."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Optional, Tuple

from .models import AppError, JobCancelled

VIDEO_AUDIO_EXTS = {
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".flv", ".m4v", ".ts", ".3gp",
    ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".wma",
}

URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def looks_like_url(text: str) -> bool:
    return bool(URL_RE.match(text.strip()))


def safe_filename(name: str, max_len: int = 80) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return (name[:max_len] or "transcript").strip()


class _CancelHook(Exception):
    pass


def download_audio(url: str, dest_dir: str,
                   progress: Optional[Callable[[float], None]] = None,
                   message: Optional[Callable[[str], None]] = None,
                   cancelled: Optional[Callable[[], bool]] = None) -> Tuple[str, str, float]:
    """Скачать аудиодорожку ролика по ссылке.

    Возвращает (путь к файлу, название ролика, длительность в секундах).
    Работает с YouTube и сотнями других сайтов, которые поддерживает yt-dlp.
    """
    try:
        import yt_dlp  # type: ignore
    except ImportError:
        raise AppError("Не установлен yt-dlp. Выполните: pip install -r requirements.txt")

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    def hook(d):
        if cancelled and cancelled():
            raise _CancelHook()
        if d.get("status") == "downloading" and progress:
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            got = d.get("downloaded_bytes")
            if total and got:
                progress(min(100.0, got / total * 100))

    ydl_opts = {
        # Только аудио — быстрее и не требует склейки видео+аудио
        "format": "bestaudio/best",
        "outtmpl": str(dest / "source.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
        "retries": 3,
        "socket_timeout": 30,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            if message:
                message("Получение информации о видео…")
            info = ydl.extract_info(url, download=False)
            if info.get("_type") == "playlist":
                entries = info.get("entries") or []
                if not entries:
                    raise AppError("По ссылке не найдено ни одного видео.")
                info = entries[0]
            title = info.get("title") or "video"
            duration = float(info.get("duration") or 0)
            if message:
                message(f"Скачивание: {title}")
            info = ydl.extract_info(url, download=True)
            if info.get("_type") == "playlist":
                info = (info.get("entries") or [info])[0]
            path = ydl.prepare_filename(info)
    except _CancelHook:
        raise JobCancelled()
    except AppError:
        raise
    except Exception as e:
        txt = str(e)
        if isinstance(e.__cause__, _CancelHook) or "_CancelHook" in txt:
            raise JobCancelled()
        low = txt.lower()
        if "private video" in low or "this video is private" in low:
            raise AppError("Видео приватное — доступ по этой ссылке закрыт.")
        if "confirm your age" in low or "age-restricted" in low or "age restricted" in low:
            raise AppError("Видео с возрастным ограничением — YouTube требует вход в аккаунт.")
        if "not a bot" in low or "sign in to confirm" in low:
            raise AppError("YouTube запросил антибот-проверку. Подождите немного и повторите, "
                           "либо скачайте видео вручную и откройте его как файл.")
        if "video unavailable" in low or "removed" in low:
            raise AppError("Видео недоступно или удалено.")
        if "unsupported url" in low:
            raise AppError("Ссылка не распознана. Проверьте адрес видео.")
        if ("getaddrinfo" in low or "resolve" in low or "connection" in low
                or "timed out" in low or "network" in low):
            raise AppError("Нет соединения с сервером. Проверьте интернет.")
        raise AppError(f"Не удалось скачать видео:\n{txt[:400]}")

    if not Path(path).is_file():
        # yt-dlp мог сменить расширение
        found = list(dest.glob("source.*"))
        if not found:
            raise AppError("Скачивание завершилось, но файл не найден.")
        path = str(found[0])

    return path, title, duration
