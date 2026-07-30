"""Нарезка длинного аудио на части для облачного API (лимит ~25 МБ на запрос).

Точки разреза подбираются по паузам в речи, чтобы не резать слова.
"""
from __future__ import annotations

from typing import List, Tuple

# При MP3 48 кбит/с моно: 1 секунда ~ 6 КБ. 20 минут ~ 7 МБ — с большим запасом.
MAX_CHUNK_SEC = 20 * 60
SEARCH_WINDOW_SEC = 120  # ищем паузу не дальше этого окна до целевой точки


def plan_chunks(duration: float,
                silences: List[Tuple[float, float]],
                max_chunk: float = MAX_CHUNK_SEC) -> List[Tuple[float, float]]:
    """Разбить [0, duration] на интервалы не длиннее max_chunk.

    Разрезы стараемся ставить в середины пауз (silences — интервалы тишины).
    """
    if duration <= max_chunk:
        return [(0.0, duration)]

    midpoints = sorted((s + e) / 2 for s, e in silences)
    chunks: List[Tuple[float, float]] = []
    pos = 0.0
    while duration - pos > max_chunk:
        target = pos + max_chunk
        # лучшая пауза в окне (target - SEARCH_WINDOW, target]
        best = None
        for m in midpoints:
            if pos + 60 < m <= target:  # минимум 60 сек на кусок
                if m > target - SEARCH_WINDOW_SEC:
                    best = m
            elif m > target:
                break
        cut = best if best is not None else target
        chunks.append((pos, cut))
        pos = cut
    chunks.append((pos, duration))
    return chunks
