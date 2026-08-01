"""Локальный движок: faster-whisper (CTranslate2), модели tiny…large-v3.

Максимальная точность — large-v3 (та же модель, что использует TurboScribe).
Работает полностью офлайн после первого скачивания модели.
"""
from __future__ import annotations

import logging
from typing import Optional

from ..config import models_dir
from ..core.models import AppError, JobCancelled, Segment, Transcript, Word
from .base import EngineCallbacks, TranscriptionEngine
from ..i18n import tr

log = logging.getLogger(__name__)


def detect_device(preferred: str = "auto") -> str:
    """auto -> cuda при наличии, иначе cpu."""
    if preferred in ("cpu", "cuda"):
        return preferred
    try:
        import ctranslate2  # type: ignore
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda"
    except Exception:
        pass
    return "cpu"


class LocalWhisperEngine(TranscriptionEngine):
    name = "local"

    def __init__(self, model_name: str = "small", device: str = "auto",
                 vad_filter: bool = True):
        self.model_name = model_name
        self.device_pref = device
        self.vad_filter = vad_filter
        self._model = None
        self._loaded_key = None

    # -- модель ---------------------------------------------------------

    def _load_model(self, cb: EngineCallbacks):
        device = detect_device(self.device_pref)
        key = (self.model_name, device)
        if self._model is not None and self._loaded_key == key:
            return self._model

        try:
            from faster_whisper import WhisperModel  # type: ignore
        except ImportError:
            raise AppError(tr("Не установлен faster-whisper. Выполните: pip install -r requirements.txt"))

        compute = "float16" if device == "cuda" else "int8"
        cb.stage(tr("Загрузка модели"))
        cb.progress(None)
        cb.message(tr("Модель {} ({}). При первом запуске модель скачивается — это может занять время.").format(self.model_name, device))
        try:
            self._model = WhisperModel(
                self.model_name,
                device=device,
                compute_type=compute,
                download_root=str(models_dir()),
            )
        except Exception as e:
            if device == "cuda":
                # Нет CUDA/cuDNN — откатываемся на CPU
                log.warning("CUDA недоступна (%s), переключаюсь на CPU", e)
                cb.message(tr("GPU недоступен, использую CPU…"))
                self._model = WhisperModel(
                    self.model_name, device="cpu", compute_type="int8",
                    download_root=str(models_dir()),
                )
                device = "cpu"
            else:
                txt = str(e)
                if "Connection" in txt or "connect" in txt.lower() or "resolve" in txt.lower():
                    raise AppError(tr("Не удалось скачать модель: нет доступа к huggingface.co. Проверьте интернет и повторите."))
                raise AppError(tr("Не удалось загрузить модель {}:\n{}").format(self.model_name, txt[:400]))
        self._loaded_key = (self.model_name, device)
        return self._model

    # -- транскрибация ----------------------------------------------------

    def transcribe(self, wav_path: str, *,
                   language: Optional[str] = None,
                   task: str = "transcribe",
                   cb: Optional[EngineCallbacks] = None) -> Transcript:
        cb = cb or EngineCallbacks()
        model = self._load_model(cb)

        cb.stage(tr("Транскрибация"))
        cb.progress(0.0)

        try:
            seg_iter, info = model.transcribe(
                wav_path,
                language=language or None,
                task=task,
                beam_size=5,
                word_timestamps=True,
                vad_filter=self.vad_filter,
                vad_parameters={"min_silence_duration_ms": 500},
            )
        except Exception as e:
            raise AppError(tr("Ошибка транскрибации:\n{}").format(str(e)[:400]))

        total = float(info.duration or 0)
        segments = []
        try:
            for s in seg_iter:
                if cb.is_cancelled():
                    raise JobCancelled()
                words = [Word(start=float(w.start), end=float(w.end), text=w.word)
                         for w in (s.words or [])]
                text = s.text.strip()
                if not text:
                    continue
                segments.append(Segment(
                    start=float(s.start), end=float(s.end), text=text, words=words,
                ))
                if total > 0:
                    cb.progress(min(99.0, float(s.end) / total * 100))
                    mm, ss = divmod(int(s.end), 60)
                    hh, mm = divmod(mm, 60)
                    done_ts = f"{hh:02d}:{mm:02d}:{ss:02d}"
                    total_ts = f"{int(total)//3600:02d}:{int(total)%3600//60:02d}:{int(total)%60:02d}"
                    cb.message(tr("Распознано {} из {}").format(done_ts, total_ts))
        except JobCancelled:
            raise
        except Exception as e:
            raise AppError(tr("Ошибка при распознавании:\n{}").format(str(e)[:400]))

        cb.progress(100.0)
        lang = "en" if task == "translate" else (info.language or language)
        return Transcript(
            segments=segments,
            language=lang,
            duration=total,
            engine=f"faster-whisper {self.model_name} ({self._loaded_key[1] if self._loaded_key else 'cpu'})",
        )
