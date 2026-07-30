"""Экспорт в TXT, SRT и VTT."""
from __future__ import annotations

from pathlib import Path

from ..core.models import Transcript
from .common import group_blocks, meta_lines, ts_short, ts_srt, ts_vtt


def export_txt(t: Transcript, path: str, timestamps: bool = True) -> None:
    lines = []
    if t.title:
        lines.append(t.title)
    lines.extend(meta_lines(t))
    lines.append("")
    for b in group_blocks(t.segments):
        prefix = f"[{ts_short(b.start)}] " if timestamps else ""
        speaker = f"{b.speaker}: " if b.speaker else ""
        lines.append(f"{prefix}{speaker}{b.text}")
        lines.append("")
    Path(path).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def export_srt(t: Transcript, path: str) -> None:
    out = []
    for i, s in enumerate(t.segments, 1):
        text = s.text.strip()
        if s.speaker:
            text = f"{s.speaker}: {text}"
        out.append(f"{i}\n{ts_srt(s.start)} --> {ts_srt(max(s.end, s.start + 0.3))}\n{text}\n")
    Path(path).write_text("\n".join(out), encoding="utf-8")


def export_vtt(t: Transcript, path: str) -> None:
    out = ["WEBVTT", ""]
    for s in t.segments:
        text = s.text.strip()
        if s.speaker:
            text = f"<v {s.speaker}>{text}</v>"
        out.append(f"{ts_vtt(s.start)} --> {ts_vtt(max(s.end, s.start + 0.3))}\n{text}\n")
    Path(path).write_text("\n".join(out), encoding="utf-8")
