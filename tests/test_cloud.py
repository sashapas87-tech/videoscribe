"""Тесты облачного движка без сети и GUI: промпт, лимиты 429, частичный результат.

Воспроизводит и проверяет исправление ошибки Groq API 400
"prompt length must be 896 characters or fewer" на длинных русскоязычных видео.

Запуск из корня проекта:  python tests/test_cloud.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core import ffmpeg_utils  # noqa: E402
from app.core.models import AppError  # noqa: E402
from app.engines import cloud  # noqa: E402
from app.engines.base import EngineCallbacks  # noqa: E402

OK = []
FAIL = []


def check(name, fn):
    try:
        fn()
        OK.append(name)
        print(f"  [OK] {name}")
    except Exception as e:
        FAIL.append((name, e))
        print(f"  [FAIL] {name}: {e}")


# ---------- заглушки ----------

class FakeResp:
    def __init__(self, status, body="", headers=None, payload=None):
        self.status_code = status
        self._payload = payload
        self.text = body or (json.dumps(payload, ensure_ascii=False) if payload is not None else "")
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeTime:
    """Виртуальные часы: sleep продвигает время мгновенно."""

    def __init__(self):
        self.now = 1000.0
        self.slept = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, s):
        self.now += s
        self.slept += s


RU = ("Это длинный русский текст про важные вещи и разные события, который "
      "накапливается как контекст для следующего куска аудио. ")


def ru_text(n_chars: int) -> str:
    s = RU * (n_chars // len(RU) + 1)
    return s[:n_chars]


def payload(chunk_len: float, text: str) -> dict:
    return {
        "language": "russian",
        "segments": [{"start": 0.0, "end": float(chunk_len), "text": text}],
        "words": [],
    }


def stub_ffmpeg(duration: float) -> None:
    """Подменяем ffmpeg: движку нужны только длительность, паузы и файл-кусок."""
    ffmpeg_utils.get_duration = lambda p: duration
    ffmpeg_utils.detect_silences = lambda p, **kw: []
    ffmpeg_utils.encode_chunk_mp3 = (
        lambda src, s, e, dst, **kw: Path(dst).write_bytes(b"mp3")
    )


def fresh_time() -> FakeTime:
    ft = FakeTime()
    cloud.time = ft
    return ft


# ---------- юнит-тесты ----------

def t_trim_prompt_tail():
    text = ru_text(600)
    norm = " ".join(text.split())
    # именно сценарий из бага: 600 русских символов -> ~1080 байт > 896
    assert len(text.encode("utf-8")) > 896, "исходный хвост должен превышать лимит Groq"
    out = cloud.trim_prompt_tail(text)
    assert out, "обрезанный хвост не должен быть пустым"
    assert len(out.encode("utf-8")) <= cloud.PROMPT_MAX_BYTES, "хвост не влез в лимит"
    assert norm.endswith(out), "хвост должен быть окончанием исходного текста"
    assert not out.startswith(" ") and "  " not in out
    # короткий текст возвращается как есть
    assert cloud.trim_prompt_tail("привет мир") == "привет мир"
    # одно сверхдлинное «слово» без пробелов не приводит к пустому промпту
    assert cloud.trim_prompt_tail("ы" * 2000)


def t_parse_retry_after():
    assert cloud.parse_retry_after(FakeResp(429, headers={"retry-after": "7"})) == 7.0
    r = cloud.parse_retry_after(FakeResp(
        429, body='{"error":{"message":"Rate limit reached. Please try again in 9m26.847s."}}'))
    assert r is not None and abs(r - 566.847) < 0.01, r
    r = cloud.parse_retry_after(FakeResp(429, body="try again in 1h2m3.5s"))
    assert r is not None and abs(r - 3723.5) < 0.01, r
    assert cloud.parse_retry_after(FakeResp(429, body="без подсказки")) is None


def t_daily_detect():
    assert cloud._is_daily_limit("... on seconds of audio per day (ASD): Limit 28800 ...")
    assert not cloud._is_daily_limit("... on seconds of audio per hour (ASH): Limit 7200 ...")


# ---------- интеграционные тесты движка (сеть и ffmpeg подменены) ----------

def t_prompt_within_groq_limit():
    """Регрессия: на мультичастном русском видео промпт всегда <= 896 байт."""
    stub_ffmpeg(3 * 1200 + 100)  # 4 куска по плану нарезки
    fresh_time()
    sent = []

    def fake_post(url, headers=None, data=None, files=None, timeout=None):
        sent.append(dict(data))
        return FakeResp(200, payload=payload(1200, ru_text(400)))

    cloud.requests.post = fake_post
    t = cloud.CloudEngine("groq", "key").transcribe("fake.wav", cb=EngineCallbacks())
    prompts = [d["prompt"] for d in sent if "prompt" in d]
    assert len(sent) == 4, f"ожидалось 4 запроса, было {len(sent)}"
    assert len(prompts) == 3, "промпт должен идти со 2-го куска"
    over = [len(p.encode("utf-8")) for p in prompts if len(p.encode("utf-8")) > 896]
    assert not over, f"промпт превышает лимит Groq: {over} байт"
    assert len(t.segments) == 4
    assert t.segments[1].start >= 1199, "таймкоды 2-го куска должны быть сдвинуты"


def t_prompt_400_fallback():
    """Страховка: на 400 про промпт повтор без промпта (ошибка со скриншота)."""
    stub_ffmpeg(1500)  # 2 куска
    fresh_time()
    calls = []
    err_body = ('{"error":{"message":"prompt length must be 896 characters or fewer, '
                'but provided prompt contains 1080 characters","type":"invalid_request_error"}}')

    def fake_post(url, headers=None, data=None, files=None, timeout=None):
        calls.append(dict(data))
        if "prompt" in data:
            return FakeResp(400, body=err_body)
        return FakeResp(200, payload=payload(750, ru_text(300)))

    cloud.requests.post = fake_post
    t = cloud.CloudEngine("groq", "key").transcribe("fake.wav", cb=EngineCallbacks())
    assert len(calls) == 3, f"ожидалось 3 запроса (с промптом и повтор без), было {len(calls)}"
    assert "prompt" in calls[1] and "prompt" not in calls[2]
    assert len(t.segments) == 2, "оба куска должны быть распознаны"


def t_429_hourly_wait():
    """Часовая квота: ждём время из ответа и продолжаем, а не падаем."""
    stub_ffmpeg(600)
    ft = fresh_time()
    msgs = []
    state = {"n": 0}
    body = ('{"error":{"message":"Rate limit reached for model whisper-large-v3 on '
            'seconds of audio per hour (ASH). Please try again in 2m0.0s."}}')

    def fake_post(url, **kw):
        state["n"] += 1
        if state["n"] == 1:
            return FakeResp(429, headers={"retry-after": "120"}, body=body)
        return FakeResp(200, payload=payload(600, "обычный текст"))

    cloud.requests.post = fake_post
    t = cloud.CloudEngine("groq", "key").transcribe(
        "fake.wav", cb=EngineCallbacks(message=msgs.append))
    assert state["n"] == 2, "после ожидания должен быть повторный запрос"
    assert ft.slept >= 120, f"ожидание меньше Retry-After: {ft.slept}"
    assert any("лимит" in m.lower() for m in msgs), "нет сообщения об ожидании квоты"
    assert len(t.segments) == 1


def t_429_daily_message():
    """Дневная квота: сразу понятная ошибка, без многочасового ожидания."""
    stub_ffmpeg(600)
    ft = fresh_time()
    body = ('{"error":{"message":"Rate limit reached for model whisper-large-v3 on '
            'seconds of audio per day (ASD): Limit 28800, Used 28800. '
            'Please try again in 4h13m2.5s."}}')
    cloud.requests.post = lambda url, **kw: FakeResp(429, body=body)
    try:
        cloud.CloudEngine("groq", "key").transcribe("fake.wav", cb=EngineCallbacks())
        raise AssertionError("ожидалась AppError")
    except AppError as e:
        assert "дневной лимит" in str(e).lower(), e
    assert ft.slept < 5, "при дневном лимите ждать не нужно"


def t_429_too_long_wait():
    """Запрошенное ожидание больше разумного порога — честная ошибка."""
    stub_ffmpeg(600)
    fresh_time()
    cloud.requests.post = lambda url, **kw: FakeResp(429, body="Please try again in 2h30m0.0s.")
    try:
        cloud.CloudEngine("groq", "key").transcribe("fake.wav", cb=EngineCallbacks())
        raise AssertionError("ожидалась AppError")
    except AppError as e:
        assert "слишком долго" in str(e).lower(), e


def t_partial_result():
    """Ошибка в середине длинной записи не уничтожает уже распознанное."""
    stub_ffmpeg(2000)  # 2 куска
    fresh_time()
    state = {"n": 0}

    def fake_post(url, **kw):
        state["n"] += 1
        if state["n"] == 1:
            return FakeResp(200, payload=payload(1100, ru_text(200)))
        return FakeResp(500, body="internal error")

    cloud.requests.post = fake_post
    t = cloud.CloudEngine("groq", "key").transcribe("fake.wav", cb=EngineCallbacks())
    assert len(t.segments) == 2, "текст 1-й части + пометка об обрыве"
    assert "прервана" in t.segments[-1].text.lower(), t.segments[-1].text
    assert t.segments[0].text.strip(), "распознанный текст 1-й части сохранён"


def t_first_chunk_error_raises():
    """Если не распознано ничего — ошибка показывается как раньше."""
    stub_ffmpeg(600)
    fresh_time()
    cloud.requests.post = lambda url, **kw: FakeResp(401, body="bad key")
    try:
        cloud.CloudEngine("groq", "key").transcribe("fake.wav", cb=EngineCallbacks())
        raise AssertionError("ожидалась AppError")
    except AppError as e:
        assert "401" in str(e)


def main():
    print("Юнит-тесты:")
    check("промпт: обрезка по байтам UTF-8", t_trim_prompt_tail)
    check("429: разбор времени ожидания", t_parse_retry_after)
    check("429: распознавание дневного лимита", t_daily_detect)

    print("Движок (сеть и ffmpeg подменены):")
    check("регрессия: промпт кириллицы всегда <= 896 байт", t_prompt_within_groq_limit)
    check("страховка: повтор без промпта при 400", t_prompt_400_fallback)
    check("429 (час): ожидание и продолжение", t_429_hourly_wait)
    check("429 (день): понятная ошибка сразу", t_429_daily_message)
    check("429: отказ при слишком долгом ожидании", t_429_too_long_wait)
    check("частичный результат при ошибке в середине", t_partial_result)
    check("ошибка на первом куске пробрасывается", t_first_chunk_error_raises)

    print(f"\nИтого: OK={len(OK)}, FAIL={len(FAIL)}")
    for name, e in FAIL:
        print(f"  FAIL {name}: {e}")
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
