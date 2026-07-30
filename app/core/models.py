"""Модели данных: слова, сегменты, транскрипт."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class Word:
    start: float
    end: float
    text: str
    speaker: Optional[str] = None


@dataclass
class Segment:
    start: float
    end: float
    text: str
    speaker: Optional[str] = None
    words: List[Word] = field(default_factory=list)


@dataclass
class Transcript:
    segments: List[Segment] = field(default_factory=list)
    language: Optional[str] = None
    duration: float = 0.0
    title: str = ""
    source: str = ""
    engine: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))

    @property
    def has_speakers(self) -> bool:
        return any(s.speaker for s in self.segments)

    @property
    def speakers(self) -> List[str]:
        seen: List[str] = []
        for s in self.segments:
            if s.speaker and s.speaker not in seen:
                seen.append(s.speaker)
        return seen

    def full_text(self, with_speakers: bool = True) -> str:
        """Сплошной текст. При наличии спикеров — с абзацами по репликам."""
        if self.has_speakers and with_speakers:
            lines: List[str] = []
            cur_speaker: Optional[str] = None
            buf: List[str] = []
            for s in self.segments:
                if s.speaker != cur_speaker:
                    if buf:
                        lines.append((f"{cur_speaker}: " if cur_speaker else "") + " ".join(buf))
                    cur_speaker = s.speaker
                    buf = []
                buf.append(s.text.strip())
            if buf:
                lines.append((f"{cur_speaker}: " if cur_speaker else "") + " ".join(buf))
            return "\n\n".join(lines)
        return " ".join(s.text.strip() for s in self.segments if s.text.strip())


@dataclass
class JobSpec:
    """Задание на транскрибацию."""
    source_type: str  # "url" | "file"
    source: str
    language: Optional[str] = None      # None = автоопределение
    translate_to_en: bool = False       # задача Whisper: перевод на английский
    diarize: bool = False               # определять спикеров
    num_speakers: Optional[int] = None  # None = авто


class JobCancelled(Exception):
    """Задание отменено пользователем."""


class AppError(Exception):
    """Ошибка с понятным пользователю сообщением."""
