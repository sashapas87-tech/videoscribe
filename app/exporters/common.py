"""Общие помощники экспорта: таймкоды и группировка сегментов в абзацы."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..core.models import Segment, Transcript


def ts_srt(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def ts_vtt(t: float) -> str:
    return ts_srt(t).replace(",", ".")


def ts_short(t: float) -> str:
    """[Ч:]ММ:СС для текстовых форматов."""
    t = int(t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


@dataclass
class Block:
    """Абзац для читаемых форматов (TXT/DOCX/PDF)."""
    start: float
    end: float
    speaker: Optional[str]
    texts: List[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(x.strip() for x in self.texts if x.strip())


def group_blocks(segments: List[Segment], max_gap: float = 2.5,
                 max_len: float = 75.0) -> List[Block]:
    """Сгруппировать сегменты в абзацы: по спикеру, паузам и длительности."""
    blocks: List[Block] = []
    for s in segments:
        b = blocks[-1] if blocks else None
        if (b is not None and b.speaker == s.speaker
                and s.start - b.end <= max_gap
                and s.end - b.start <= max_len):
            b.texts.append(s.text)
            b.end = s.end
        else:
            blocks.append(Block(start=s.start, end=s.end, speaker=s.speaker, texts=[s.text]))
    return blocks


def meta_lines(t: Transcript) -> List[str]:
    """Строки метаданных для шапки документов."""
    lines = []
    if t.source:
        lines.append(f"Источник: {t.source}")
    if t.duration:
        lines.append(f"Длительность: {ts_short(t.duration)}")
    if t.language:
        lines.append(f"Язык: {t.language}")
    if t.engine:
        lines.append(f"Движок: {t.engine}")
    lines.append(f"Создано: {t.created_at} — VideoScribe")
    return lines
