"""Облачный движок: OpenAI и Groq (OpenAI-совместимый API).

Длинное аудио автоматически режется на части по паузам (лимит API ~25 МБ),
результаты склеиваются со смещением таймкодов.
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import List, Optional

import requests

from ..core import chunking, ffmpeg_utils
from ..core.models import AppError, JobCancelled, Segment, Transcript, Word
from .base import EngineCallbacks, TranscriptionEngine

PROVIDERS = {
    "groq": {
        "label": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "stt_model": "whisper-large-v3",
        "llm_model": "llama-3.3-70b-versatile",
        "keys_url": "https://console.groq.com/keys",
    },
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "stt_model": "whisper-1",
        "llm_model": "gpt-4o-mini",
        "keys_url": "https://platform.openai.com/api-keys",
    },
}

_RETRY_STATUSES = {429, 500, 502, 503, 504}


def _api_error(provider_label: str, status: int, body: str) -> AppError:
    if status == 401:
        return AppError(f"{provider_label}: неверный API-ключ (401). Проверьте ключ в настройках.")
    if status == 429:
        return AppError(f"{provider_label}: превышен лимит запросов (429). Подождите и повторите.")
    if status == 413:
        return AppError(f"{provider_label}: файл слишком большой (413).")
    return AppError(f"{provider_label}: ошибка API {status}:\n{body[:300]}")


class CloudEngine(TranscriptionEngine):
    name = "cloud"

    def __init__(self, provider: str, api_key: str):
        if provider not in PROVIDERS:
            raise AppError(f"Неизвестный провайдер: {provider}")
        if not api_key.strip():
            raise AppError("Не задан API-ключ облачного провайдера. Откройте Настройки и вставьте ключ.")
        self.provider = provider
        self.meta = PROVIDERS[provider]
        self.api_key = api_key.strip()

    # -- HTTP -------------------------------------------------------------

    def _post_audio(self, endpoint: str, mp3_path: str, data: dict,
                    cb: EngineCallbacks) -> dict:
        url = f"{self.meta['base_url']}/{endpoint}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        last_err: Optional[Exception] = None
        for attempt in range(4):
            if cb.is_cancelled():
                raise JobCancelled()
            try:
                with open(mp3_path, "rb") as f:
                    resp = requests.post(
                        url, headers=headers, data=data,
                        files={"file": (Path(mp3_path).name, f, "audio/mpeg")},
                        timeout=900,
                    )
            except requests.RequestException as e:
                last_err = e
                time.sleep(2 * (attempt + 1))
                continue
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 400 and "timestamp_granularities" in resp.text and \
                    "timestamp_granularities[]" in data:
                # Провайдер не поддерживает пословные таймкоды — повторяем без них
                data = {k: v for k, v in data.items() if k != "timestamp_granularities[]"}
                data["timestamp_granularities[]"] = ["segment"]
                continue
            if resp.status_code in _RETRY_STATUSES and attempt < 3:
                time.sleep(3 * (attempt + 1))
                continue
            raise _api_error(self.meta["label"], resp.status_code, resp.text)
        raise AppError(f"Нет соединения с {self.meta['label']}: {last_err}")

    # -- транскрибация ------------------------------------------------------

    def transcribe(self, wav_path: str, *,
                   language: Optional[str] = None,
                   task: str = "transcribe",
                   cb: Optional[EngineCallbacks] = None) -> Transcript:
        cb = cb or EngineCallbacks()

        duration = ffmpeg_utils.get_duration(wav_path)

        cb.stage("Подготовка аудио")
        cb.progress(None)
        silences = ffmpeg_utils.detect_silences(wav_path) if duration > chunking.MAX_CHUNK_SEC else []
        chunks = chunking.plan_chunks(duration, silences)

        endpoint = "audio/translations" if task == "translate" else "audio/transcriptions"

        segments: List[Segment] = []
        detected_lang: Optional[str] = None
        prev_tail = ""

        with tempfile.TemporaryDirectory(prefix="vscloud_") as tmp:
            for i, (start, end) in enumerate(chunks):
                if cb.is_cancelled():
                    raise JobCancelled()
                cb.stage("Транскрибация (облако)")
                if len(chunks) > 1:
                    cb.message(f"Часть {i + 1} из {len(chunks)}…")
                cb.progress(start / duration * 100 if duration else None)

                mp3 = str(Path(tmp) / f"chunk_{i:03d}.mp3")
                ffmpeg_utils.encode_chunk_mp3(wav_path, start, end, mp3)

                data = {
                    "model": self.meta["stt_model"],
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": ["segment", "word"],
                    "temperature": "0",
                }
                if task != "translate" and language:
                    data["language"] = language
                if prev_tail:
                    data["prompt"] = prev_tail[-600:]

                payload = self._post_audio(endpoint, mp3, data, cb)

                if not detected_lang:
                    detected_lang = payload.get("language")

                words_all = [
                    Word(start=float(w["start"]) + start, end=float(w["end"]) + start,
                         text=w.get("word") or w.get("text") or "")
                    for w in (payload.get("words") or [])
                ]
                wi = 0
                for s in payload.get("segments") or []:
                    text = (s.get("text") or "").strip()
                    if not text:
                        continue
                    s_start = float(s["start"]) + start
                    s_end = float(s["end"]) + start
                    seg_words: List[Word] = []
                    while wi < len(words_all) and words_all[wi].start < s_end - 0.01:
                        if words_all[wi].end > s_start:
                            seg_words.append(words_all[wi])
                        wi += 1
                    segments.append(Segment(start=s_start, end=s_end, text=text, words=seg_words))

                if segments:
                    prev_tail = " ".join(x.text for x in segments[-6:])

        cb.progress(100.0)
        lang_map = {"russian": "ru", "english": "en", "ukrainian": "uk"}
        if detected_lang:
            detected_lang = lang_map.get(detected_lang.lower(), detected_lang)
        return Transcript(
            segments=segments,
            language="en" if task == "translate" else (detected_lang or language),
            duration=duration,
            engine=f"{self.meta['label']} {self.meta['stt_model']}",
        )
