"""Пайплайн задания: получение медиа -> аудио -> транскрибация -> диаризация."""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Optional

from ..config import AppConfig, app_data_dir
from ..engines.base import EngineCallbacks, TranscriptionEngine
from ..engines.cloud import CloudEngine
from ..engines.local_whisper import LocalWhisperEngine
from . import diarize, ffmpeg_utils, media
from .models import AppError, JobSpec, Transcript

# Кэш локального движка между заданиями — модель не перезагружается
_local_engine_cache: Optional[LocalWhisperEngine] = None


def build_engine(cfg: AppConfig) -> TranscriptionEngine:
    global _local_engine_cache
    if cfg.engine == "cloud":
        return CloudEngine(cfg.cloud_provider, cfg.active_api_key())
    e = _local_engine_cache
    if (e is None or e.model_name != cfg.local_model
            or e.device_pref != cfg.device or e.vad_filter != cfg.vad_filter):
        e = LocalWhisperEngine(cfg.local_model, cfg.device, cfg.vad_filter)
        _local_engine_cache = e
    return e


def run_job(spec: JobSpec, cfg: AppConfig, cb: EngineCallbacks) -> Transcript:
    """Выполнить задание целиком. Может занимать много времени — звать из фонового потока."""
    tmp = app_data_dir() / "tmp" / uuid.uuid4().hex[:12]
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        # 1. Исходный файл
        if spec.source_type == "url":
            cb.stage("Скачивание видео")
            cb.progress(0.0)
            src_path, title, _dur = media.download_audio(
                spec.source, str(tmp),
                progress=cb.progress, message=cb.message, cancelled=cb.is_cancelled,
            )
        else:
            p = Path(spec.source)
            if not p.is_file():
                raise AppError(f"Файл не найден: {spec.source}")
            src_path, title = str(p), p.stem

        # 2. Аудиодорожка WAV 16 кГц моно
        cb.stage("Извлечение аудио")
        cb.progress(0.0)
        wav = str(tmp / "audio.wav")
        ffmpeg_utils.extract_wav(src_path, wav, progress=cb.progress,
                                 cancelled=cb.is_cancelled)
        duration = ffmpeg_utils.get_duration(wav)

        # 3. Транскрибация
        engine = build_engine(cfg)
        task = "translate" if spec.translate_to_en else "transcribe"
        transcript = engine.transcribe(
            wav, language=spec.language or None, task=task, cb=cb,
        )

        # 4. Диаризация (локальная, работает с обоими движками)
        if spec.diarize and transcript.segments:
            turns = diarize.run_diarization(
                wav, cfg.hf_token, num_speakers=spec.num_speakers, cb=cb,
            )
            transcript = diarize.merge_speakers(transcript, turns)

        transcript.title = title
        transcript.source = spec.source
        if not transcript.duration:
            transcript.duration = duration
        cb.stage("Готово")
        cb.progress(100.0)
        return transcript
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
