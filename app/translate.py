"""Перевод готового транскрипта на выбранный язык через облачный LLM.

Работает пакетами сегментов, сохраняет таймкоды и спикеров.
(Кроме этого, Whisper умеет переводить на английский прямо при транскрибации —
галочка в главном окне.)
"""
from __future__ import annotations

import copy
import json
import re
import time
from typing import Optional

import requests

from .core.models import AppError, JobCancelled, Transcript
from .engines.base import EngineCallbacks
from .engines.cloud import PROVIDERS
from .i18n import tr

BATCH_SIZE = 35

TRANSLATE_TARGETS = [
    ("Английский", "английский"),
    ("Русский", "русский"),
    ("Українська", "украинский"),
    ("Немецкий", "немецкий"),
    ("Французский", "французский"),
    ("Испанский", "испанский"),
    ("Итальянский", "итальянский"),
    ("Польский", "польский"),
    ("Португальский", "португальский"),
    ("Турецкий", "турецкий"),
    ("Китайский", "китайский"),
    ("Японский", "японский"),
]


def _chat(provider: str, api_key: str, messages: list, cb: EngineCallbacks) -> str:
    meta = PROVIDERS[provider]
    url = f"{meta['base_url']}/chat/completions"
    body = {
        "model": meta["llm_model"],
        "messages": messages,
        "temperature": 0.2,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    last = None
    for attempt in range(4):
        if cb.is_cancelled():
            raise JobCancelled()
        try:
            r = requests.post(url, headers=headers, json=body, timeout=300)
        except requests.RequestException as e:
            last = e
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
        if r.status_code == 401:
            raise AppError(tr("{}: неверный API-ключ (401).").format(meta['label']))
        if r.status_code in (429, 500, 502, 503) and attempt < 3:
            time.sleep(3 * (attempt + 1))
            continue
        raise AppError(tr("{}: ошибка API {}:\n{}").format(meta['label'], r.status_code, r.text[:300]))
    raise AppError(tr("Нет соединения с {}: {}").format(meta['label'], last))


def _parse_json_array(text: str) -> list:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("no JSON array")
    return json.loads(text[start:end + 1])


def translate_transcript(transcript: Transcript, target_lang: str,
                         provider: str, api_key: str,
                         cb: Optional[EngineCallbacks] = None) -> Transcript:
    """Вернуть копию транскрипта с переведённым текстом сегментов."""
    cb = cb or EngineCallbacks()
    if not api_key.strip():
        raise AppError(tr("Для перевода нужен API-ключ (Groq или OpenAI) — задайте его в Настройках."))

    result = copy.deepcopy(transcript)
    for s in result.segments:
        s.words = []  # пословные таймкоды после перевода не имеют смысла

    total = len(result.segments)
    cb.stage(tr("Перевод"))
    cb.progress(0.0)

    sys_prompt = (
        f"Ты профессиональный переводчик субтитров. Переведи текст каждого элемента на {target_lang} язык. "
        "Верни СТРОГО JSON-массив вида [{\"i\": 0, \"t\": \"перевод\"}] и ничего больше. "
        "Сохрани все элементы и их номера i, не объединяй и не пропускай. "
        "Сохраняй имена собственные, числа и термины. Пиши естественно."
    )

    for offset in range(0, total, BATCH_SIZE):
        if cb.is_cancelled():
            raise JobCancelled()
        batch = result.segments[offset:offset + BATCH_SIZE]
        payload = json.dumps(
            [{"i": i, "t": s.text} for i, s in enumerate(batch)],
            ensure_ascii=False,
        )
        content = _chat(provider, api_key.strip(), [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": payload},
        ], cb)
        try:
            items = _parse_json_array(content)
            m = {int(it["i"]): str(it["t"]) for it in items if "i" in it and "t" in it}
        except Exception:
            raise AppError(tr("Модель вернула некорректный ответ при переводе. Попробуйте ещё раз."))
        for i, s in enumerate(batch):
            if i in m and m[i].strip():
                s.text = m[i].strip()
        cb.progress(min(99.0, (offset + len(batch)) / total * 100))
        cb.message(tr("Переведено {} из {} сегментов").format(min(offset + len(batch), total), total))

    result.title = transcript.title + tr(" (перевод)")
    result.language = None
    result.engine = transcript.engine + tr(" + перевод LLM")
    cb.progress(100.0)
    return result
