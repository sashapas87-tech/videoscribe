"""Облачный движок: OpenAI и Groq (OpenAI-совместимый API).

Длинное аудио автоматически режется на части по паузам (лимит API ~25 МБ),
результаты склеиваются со смещением таймкодов.

Особенности облачных лимитов, которые учитывает движок:
- контекстный промпт между частями ограничен провайдером по БАЙТАМ UTF-8
  (у Groq ~896), поэтому хвост текста режется по байтам, а не по символам;
- при 429 (превышение квоты) читаем Retry-After / текст ошибки и ждём
  сброса часовой квоты с отсчётом, вместо того чтобы падать;
- исчерпание дневного лимита распознаётся сразу и объясняется словами;
- если ошибка случилась в середине длинной записи, уже распознанные части
  не пропадают — возвращается частичный результат с пометкой.
"""
from __future__ import annotations

import re
import tempfile
import time
from pathlib import Path
from typing import List, Optional

import requests

from ..core import chunking, ffmpeg_utils
from ..core.models import AppError, JobCancelled, Segment, Transcript, Word
from .base import EngineCallbacks, TranscriptionEngine
from ..i18n import tr

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

# Groq ограничивает контекстный промпт 896 «символами», считая длину в байтах
# UTF-8: кириллическая буква занимает 2 байта, так что 600 русских символов —
# это ~1080 байт и ошибка 400. Режем хвост по байтам и с запасом.
PROMPT_MAX_BYTES = 700

# Максимальное суммарное ожидание сброса лимитов (429) на один кусок аудио.
# Часовая квота бесплатного тарифа Groq успевает освободиться.
MAX_RATE_WAIT_SEC = 70 * 60

_WAIT_RE = re.compile(r"try again in\s+(?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", re.IGNORECASE)


def trim_prompt_tail(text: str, max_bytes: int = PROMPT_MAX_BYTES) -> str:
    """Хвост текста не длиннее max_bytes в UTF-8, обрезанный по границе слова.

    Провайдеры считают длину промпта в байтах, а не в символах, поэтому
    срез вида text[-600:] для кириллицы превышает лимит почти вдвое.
    """
    text = " ".join(text.split())
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text
    tail = raw[-max_bytes:].decode("utf-8", errors="ignore")
    sp = tail.find(" ")
    if sp != -1:
        tail = tail[sp + 1:]
    return tail.strip()


def parse_retry_after(resp) -> Optional[float]:
    """Сколько секунд просит подождать провайдер (заголовок или текст ошибки)."""
    headers = resp.headers or {}
    hdr = headers.get("retry-after") or headers.get("Retry-After")
    if hdr:
        try:
            return max(0.0, float(hdr))
        except (TypeError, ValueError):
            pass
    m = _WAIT_RE.search(resp.text or "")
    if m:
        h, mi, s = m.group(1), m.group(2), m.group(3)
        return float(h or 0) * 3600 + float(mi or 0) * 60 + float(s)
    return None


def _is_daily_limit(body: str) -> bool:
    """Ответ 429 говорит об исчерпании ДНЕВНОЙ квоты (ждать час бессмысленно)."""
    low = (body or "").lower()
    return "per day" in low or "(asd)" in low or "(rpd)" in low or "(tpd)" in low


def _api_error(provider_label: str, status: int, body: str) -> AppError:
    if status == 401:
        return AppError(tr("{}: неверный API-ключ (401). Проверьте ключ в настройках.").format(provider_label))
    if status == 429:
        return AppError(tr("{}: превышен лимит запросов (429). Подождите и повторите.\n{}").format(provider_label, body[:300]))
    if status == 413:
        return AppError(tr("{}: файл слишком большой (413).").format(provider_label))
    return AppError(tr("{}: ошибка API {}:\n{}").format(provider_label, status, body[:300]))


class CloudEngine(TranscriptionEngine):
    name = "cloud"

    def __init__(self, provider: str, api_key: str):
        if provider not in PROVIDERS:
            raise AppError(tr("Неизвестный провайдер: {}").format(provider))
        if not api_key.strip():
            raise AppError(tr("Не задан API-ключ облачного провайдера. Откройте Настройки и вставьте ключ."))
        self.provider = provider
        self.meta = PROVIDERS[provider]
        self.api_key = api_key.strip()

    # -- HTTP -------------------------------------------------------------

    def _wait_rate_limit(self, seconds: float, cb: EngineCallbacks) -> None:
        """Подождать сброса квоты, показывая отсчёт и реагируя на отмену."""
        deadline = time.monotonic() + seconds
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                break
            if cb.is_cancelled():
                raise JobCancelled()
            mm, ss = divmod(int(left) + 1, 60)
            cb.message(tr("Достигнут лимит {} — ждём сброса квоты: {:02d}:{:02d}").format(self.meta['label'], mm, ss))
            time.sleep(min(1.0, left))
        cb.message(tr("Лимит снят, продолжаем…"))

    def _post_audio(self, endpoint: str, mp3_path: str, data: dict,
                    cb: EngineCallbacks) -> dict:
        url = f"{self.meta['base_url']}/{endpoint}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        label = self.meta["label"]

        net_errors = 0          # сетевые сбои подряд
        server_retries = 0      # ответы 5xx подряд
        rate_waited = 0.0       # суммарное ожидание лимитов (429)
        dropped_words = False   # уже отключили пословные таймкоды
        dropped_prompt = False  # уже отключили контекстный промпт

        while True:
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
                net_errors += 1
                if net_errors > 3:
                    raise AppError(tr("Нет соединения с {}: {}").format(label, e))
                time.sleep(2 * net_errors)
                continue

            if resp.status_code == 200:
                return resp.json()

            body = resp.text or ""

            if resp.status_code == 400:
                # Провайдер не поддерживает пословные таймкоды — повторяем без них
                if not dropped_words and "timestamp_granularities" in body \
                        and "timestamp_granularities[]" in data:
                    dropped_words = True
                    data = {k: v for k, v in data.items() if k != "timestamp_granularities[]"}
                    data["timestamp_granularities[]"] = ["segment"]
                    continue
                # Промпт отклонён (например, слишком длинный) — повторяем без него:
                # чуть хуже связность на стыке частей, но транскрибация продолжится
                if not dropped_prompt and "prompt" in data and "prompt" in body.lower():
                    dropped_prompt = True
                    data = {k: v for k, v in data.items() if k != "prompt"}
                    continue

            if resp.status_code == 429:
                if _is_daily_limit(body):
                    raise AppError(
                        tr("{}: исчерпан дневной лимит аудио (429).\nНа бесплатном тарифе Groq можно распознать до 8 часов аудио в сутки. Продолжите завтра, подключите платный тариф или выберите локальный движок в настройках.").format(label)
                    )
                wait = parse_retry_after(resp)
                wait = (wait + 2.0) if wait is not None else 60.0  # небольшой запас
                if rate_waited + wait > MAX_RATE_WAIT_SEC:
                    mins = max(1, int(wait // 60))
                    raise AppError(
                        tr("{}: превышен лимит запросов (429). Провайдер просит подождать ещё ~{} мин — это слишком долго. Повторите позже или подключите платный тариф.\n{}").format(label, mins, body[:200])
                    )
                self._wait_rate_limit(wait, cb)
                rate_waited += wait
                continue

            if resp.status_code in (500, 502, 503, 504):
                server_retries += 1
                if server_retries <= 3:
                    time.sleep(3 * server_retries)
                    continue

            raise _api_error(label, resp.status_code, body)

    # -- транскрибация ------------------------------------------------------

    def transcribe(self, wav_path: str, *,
                   language: Optional[str] = None,
                   task: str = "transcribe",
                   cb: Optional[EngineCallbacks] = None) -> Transcript:
        cb = cb or EngineCallbacks()

        duration = ffmpeg_utils.get_duration(wav_path)

        cb.stage(tr("Подготовка аудио"))
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
                cb.stage(tr("Транскрибация (облако)"))
                if len(chunks) > 1:
                    cb.message(tr("Часть {} из {}…").format(i + 1, len(chunks)))
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
                    tail = trim_prompt_tail(prev_tail)
                    if tail:
                        data["prompt"] = tail

                try:
                    payload = self._post_audio(endpoint, mp3, data, cb)
                except AppError as e:
                    if not segments:
                        raise
                    # Не теряем уже распознанное: возвращаем частичный результат
                    done_min = int(start // 60)
                    segments.append(Segment(
                        start=start, end=start,
                        text=tr("⚠ Транскрибация прервана на части {} из {} (распознано около {} мин). Причина: {}").format(i + 1, len(chunks), done_min, e),
                    ))
                    cb.message(tr("Ошибка облачного API — сохранён частичный результат."))
                    break

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
