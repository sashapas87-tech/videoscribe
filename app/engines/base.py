"""Базовый интерфейс движка транскрибации."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional

from ..core.models import Transcript


class EngineCallbacks:
    """Колбэки прогресса, передаваемые движку."""

    def __init__(self,
                 stage: Optional[Callable[[str], None]] = None,
                 progress: Optional[Callable[[Optional[float]], None]] = None,
                 message: Optional[Callable[[str], None]] = None,
                 is_cancelled: Optional[Callable[[], bool]] = None):
        self.stage = stage or (lambda s: None)
        self.progress = progress or (lambda p: None)   # 0..100 или None (неопределённый)
        self.message = message or (lambda m: None)
        self.is_cancelled = is_cancelled or (lambda: False)


class TranscriptionEngine(ABC):
    """Движок: принимает WAV 16 кГц моно, возвращает Transcript."""

    name: str = "engine"

    @abstractmethod
    def transcribe(self, wav_path: str, *,
                   language: Optional[str] = None,
                   task: str = "transcribe",
                   cb: Optional[EngineCallbacks] = None) -> Transcript:
        ...
