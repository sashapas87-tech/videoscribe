"""Смоук-тест ядра без GUI: медиа -> аудио -> транскрибация -> экспорт.

Запуск из корня проекта:  python tests/smoke_core.py [url_or_file]
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core import chunking, diarize, ffmpeg_utils, media  # noqa: E402
from app.core.models import Transcript  # noqa: E402
from app.engines.base import EngineCallbacks  # noqa: E402
from app.engines.local_whisper import LocalWhisperEngine  # noqa: E402
from app.exporters.docx_pdf import export_docx, export_pdf  # noqa: E402
from app.exporters.text_formats import export_srt, export_txt, export_vtt  # noqa: E402

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


def main():
    source = sys.argv[1] if len(sys.argv) > 1 else "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    tmp = Path(tempfile.mkdtemp(prefix="vs_smoke_"))
    print(f"tmp: {tmp}")

    cb = EngineCallbacks(
        stage=lambda s: print(f"  -- этап: {s}"),
        message=lambda m: print(f"     {m}"),
    )

    # 1. Получение исходника
    state = {}

    def get_media():
        if media.looks_like_url(source):
            path, title, dur = media.download_audio(source, str(tmp / "dl"))
            state.update(src=path, title=title)
            print(f"     скачано: {title!r} -> {Path(path).name} ({dur:.0f}s)")
        else:
            state.update(src=source, title=Path(source).stem)

    check("media: получение исходника", get_media)
    if "src" not in state:
        report()
        return

    # 2. Извлечение WAV
    wav = str(tmp / "audio.wav")

    def extract():
        ffmpeg_utils.extract_wav(state["src"], wav)
        dur = ffmpeg_utils.get_duration(wav)
        assert dur > 1, "слишком короткое аудио"
        state["dur"] = dur
        print(f"     WAV: {dur:.1f}s, {Path(wav).stat().st_size // 1024} КБ")

    check("ffmpeg: извлечение WAV 16кГц моно", extract)
    if "dur" not in state:
        report()
        return

    # 3. Нарезка (юнит: тишина + план чанков)
    def chunks():
        sil = ffmpeg_utils.detect_silences(wav)
        plan_long = chunking.plan_chunks(3 * 3600, [(i * 300, i * 300 + 2) for i in range(1, 36)])
        assert all(e - s <= chunking.MAX_CHUNK_SEC + 1 for s, e in plan_long)
        assert abs(plan_long[-1][1] - 3 * 3600) < 0.01
        assert chunking.plan_chunks(60, []) == [(0.0, 60)]
        print(f"     пауз найдено: {len(sil)}; план 3ч -> {len(plan_long)} части")

    check("chunking: тишина и план нарезки", chunks)

    # 4. Транскрибация локальной моделью tiny
    state["t"] = None

    def transcribe():
        eng = LocalWhisperEngine("tiny", "cpu", vad_filter=True)
        t = eng.transcribe(wav, language=None, cb=cb)
        assert t.segments, "нет сегментов"
        assert t.segments[0].words, "нет пословных таймкодов"
        state["t"] = t
        t.title = state["title"]
        t.source = source
        print(f"     язык={t.language}, сегментов={len(t.segments)}")
        print(f"     текст: {t.full_text()[:160]!r}")

    check("faster-whisper tiny: транскрибация", transcribe)
    t = state.get("t")
    if not t:
        report()
        return

    # 5. Слияние спикеров (синтетические интервалы вместо pyannote)
    def merge():
        mid = t.duration / 2
        turns = [(0.0, mid, "SPEAKER_00"), (mid, t.duration + 1, "SPEAKER_01")]
        import copy
        t2 = diarize.merge_speakers(copy.deepcopy(t), turns)
        assert t2.has_speakers, "спикеры не назначены"
        names = t2.speakers
        assert names and names[0] == "Спикер 1", names
        state["t2"] = t2
        print(f"     спикеры: {names}, сегментов: {len(t2.segments)}")

    check("diarize: слияние меток спикеров", merge)

    # 6. Экспортеры
    exp = state.get("t2") or t
    out = tmp / "export"
    out.mkdir(exist_ok=True)

    def make_export(fn, ext):
        def run():
            p = out / f"result.{ext}"
            fn(exp, str(p))
            size = p.stat().st_size
            assert size > 100, f"файл подозрительно мал: {size} байт"
            print(f"     result.{ext}: {size} байт")
        return run

    check("export TXT", make_export(export_txt, "txt"))
    check("export SRT", make_export(export_srt, "srt"))
    check("export VTT", make_export(export_vtt, "vtt"))
    check("export DOCX", make_export(export_docx, "docx"))
    check("export PDF", make_export(export_pdf, "pdf"))

    # 7. Контроль формата SRT/VTT
    def check_srt():
        text = (out / "result.srt").read_text(encoding="utf-8")
        assert "-->" in text and text.lstrip().startswith("1"), text[:80]
        vtt = (out / "result.vtt").read_text(encoding="utf-8")
        assert vtt.startswith("WEBVTT"), vtt[:20]

    check("формат SRT/VTT", check_srt)

    state["out"] = out
    report()
    print(f"\nЭкспорт: {out}")


def report():
    print(f"\nИтого: OK={len(OK)}, FAIL={len(FAIL)}")
    for name, e in FAIL:
        print(f"  FAIL {name}: {e}")
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
