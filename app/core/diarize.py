"""Диаризация (кто из спикеров говорит) через pyannote.audio 3.1.

Выполняется локально и совмещается с транскриптом по таймкодам,
поэтому работает с обоими движками (локальным и облачным).
Требует бесплатный токен Hugging Face и принятые условия моделей:
  https://huggingface.co/pyannote/speaker-diarization-3.1
  https://huggingface.co/pyannote/segmentation-3.0
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from ..config import models_dir
from ..core.models import AppError, Segment, Transcript
from ..engines.base import EngineCallbacks
from ..i18n import tr

Turn = Tuple[float, float, str]  # (start, end, raw_label)

_PIPELINE_ID = "pyannote/speaker-diarization-3.1"
_pipeline_cache = {}


def is_available() -> bool:
    """Установлены ли pyannote.audio и torch."""
    try:
        import pyannote.audio  # noqa: F401  # type: ignore
        import torch  # noqa: F401  # type: ignore
        return True
    except Exception:
        return False


def run_diarization(wav_path: str, hf_token: str,
                    num_speakers: Optional[int] = None,
                    cb: Optional[EngineCallbacks] = None) -> List[Turn]:
    cb = cb or EngineCallbacks()
    if not is_available():
        raise AppError(
            tr("Для определения спикеров нужны пакеты torch и pyannote.audio.\nУстановите их: pip install -r requirements-diarization.txt")
        )
    if not hf_token.strip():
        raise AppError(
            tr("Для определения спикеров нужен токен Hugging Face (бесплатно).\nДобавьте его в Настройках и примите условия моделей pyannote.")
        )

    import torch  # type: ignore
    from pyannote.audio import Pipeline  # type: ignore

    cb.stage(tr("Диаризация"))
    cb.progress(None)
    cb.message(tr("Загрузка модели диаризации (при первом запуске скачивается ~1 ГБ)…"))

    token = hf_token.strip()
    pipe = _pipeline_cache.get(token)
    if pipe is None:
        try:
            pipe = Pipeline.from_pretrained(
                _PIPELINE_ID,
                use_auth_token=token,
                cache_dir=str(models_dir() / "pyannote"),
            )
        except Exception as e:
            txt = str(e)
            if "401" in txt or "403" in txt or "gated" in txt.lower() or "access" in txt.lower():
                raise AppError(
                    tr("Hugging Face не принял токен или не приняты условия моделей.\n1) Проверьте токен в Настройках.\n2) Примите условия на страницах:\n   huggingface.co/pyannote/speaker-diarization-3.1\n   huggingface.co/pyannote/segmentation-3.0")
                )
            raise AppError(tr("Не удалось загрузить модель диаризации:\n{}").format(txt[:400]))
        if pipe is None:
            raise AppError(
                tr("Hugging Face вернул пустую модель. Скорее всего, не приняты условия использования pyannote/speaker-diarization-3.1 — откройте страницу модели и нажмите 'Agree and access repository'.")
            )
        if torch.cuda.is_available():
            try:
                pipe.to(torch.device("cuda"))
            except Exception:
                pass
        _pipeline_cache[token] = pipe

    def hook(step_name, step_artifact, file=None, total=None, completed=None):
        if completed is not None and total:
            cb.progress(min(99.0, completed / total * 100))
        cb.message(tr("Диаризация: {}").format(step_name))

    cb.message(tr("Анализ спикеров…"))
    try:
        kwargs = {}
        if num_speakers:
            kwargs["num_speakers"] = int(num_speakers)
        annotation = pipe(wav_path, hook=hook, **kwargs)
    except Exception as e:
        raise AppError(tr("Ошибка диаризации:\n{}").format(str(e)[:400]))

    turns: List[Turn] = []
    for turn, _, label in annotation.itertracks(yield_label=True):
        turns.append((float(turn.start), float(turn.end), str(label)))
    turns.sort(key=lambda t: t[0])
    cb.progress(100.0)
    return turns


# -- слияние с транскриптом ------------------------------------------------


def _speaker_at(turns: List[Turn], t: float) -> Optional[str]:
    """Метка спикера в момент времени t (допуск 0.7 c до ближайшего интервала)."""
    best: Optional[str] = None
    best_dist = 0.7
    for s, e, label in turns:
        if s <= t < e:
            return label
        dist = s - t if t < s else t - e
        if 0 <= dist < best_dist:
            best_dist = dist
            best = label
        if s > t + 1.0:
            break
    return best


def _overlap_speaker(turns: List[Turn], start: float, end: float) -> Optional[str]:
    """Спикер с максимальным пересечением с интервалом [start, end]."""
    acc = {}
    for s, e, label in turns:
        ov = min(end, e) - max(start, s)
        if ov > 0:
            acc[label] = acc.get(label, 0.0) + ov
        if s > end:
            break
    if not acc:
        return _speaker_at(turns, (start + end) / 2)
    return max(acc.items(), key=lambda kv: kv[1])[0]


def _join_words(words) -> str:
    if any(x.text.startswith(" ") for x in words):
        return "".join(x.text for x in words).strip()
    return " ".join(x.text.strip() for x in words).strip()


def merge_speakers(transcript: Transcript, turns: List[Turn]) -> Transcript:
    """Разметить сегменты спикерами; сегменты со сменой спикера внутри — разделить."""
    if not turns:
        return transcript

    new_segments: List[Segment] = []
    for seg in transcript.segments:
        if seg.words:
            for w in seg.words:
                w.speaker = _speaker_at(turns, (w.start + w.end) / 2)
            # заполняем пропуски соседними значениями
            last = None
            for w in seg.words:
                if w.speaker is None:
                    w.speaker = last
                else:
                    last = w.speaker
            nxt = None
            for w in reversed(seg.words):
                if w.speaker is None:
                    w.speaker = nxt
                else:
                    nxt = w.speaker
            # группируем подряд идущие слова одного спикера
            groups: List[List] = []
            for w in seg.words:
                if groups and groups[-1][0].speaker == w.speaker:
                    groups[-1].append(w)
                else:
                    groups.append([w])
            if len(groups) == 1:
                seg.speaker = groups[0][0].speaker or _overlap_speaker(turns, seg.start, seg.end)
                new_segments.append(seg)
            else:
                for g in groups:
                    text = _join_words(g)
                    if not text:
                        continue
                    new_segments.append(Segment(
                        start=g[0].start, end=g[-1].end, text=text,
                        speaker=g[0].speaker, words=list(g),
                    ))
        else:
            seg.speaker = _overlap_speaker(turns, seg.start, seg.end)
            new_segments.append(seg)

    # человекочитаемые имена в порядке появления
    mapping = {}
    for s in new_segments:
        if s.speaker and s.speaker not in mapping:
            mapping[s.speaker] = tr("Спикер {}").format(len(mapping) + 1)
    for s in new_segments:
        if s.speaker:
            s.speaker = mapping[s.speaker]
        for w in s.words:
            if w.speaker:
                w.speaker = mapping.get(w.speaker, w.speaker)

    transcript.segments = new_segments
    return transcript
