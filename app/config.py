"""Настройки приложения: загрузка/сохранение JSON в каталоге пользователя."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, asdict, fields
from pathlib import Path

from .i18n import tr

APP_NAME = "VideoScribe"


def app_data_dir() -> Path:
    """Каталог данных приложения (Windows: %APPDATA%/VideoScribe)."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home())
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def models_dir() -> Path:
    d = app_data_dir() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def default_output_dir() -> str:
    docs = Path.home() / "Documents"
    return str((docs if docs.exists() else Path.home()) / APP_NAME)


def assets_dir() -> Path:
    """Каталог assets: рядом с exe (PyInstaller) или с корнем проекта."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass and (Path(meipass) / "assets").exists():
            return Path(meipass) / "assets"
        return Path(sys.executable).parent / "assets"
    return Path(__file__).resolve().parent.parent / "assets"


@dataclass
class AppConfig:
    # Движок: "local" | "cloud"
    engine: str = "local"
    # Локальный движок
    local_model: str = "small"          # tiny/base/small/medium/large-v2/large-v3
    device: str = "auto"                # auto/cpu/cuda
    vad_filter: bool = True
    # Облачный движок
    cloud_provider: str = "groq"        # groq/openai
    groq_api_key: str = ""
    openai_api_key: str = ""
    # Диаризация
    hf_token: str = ""
    # Общее
    default_language: str = ""          # "" = авто, иначе код ISO ("ru", "en", ...)
    output_dir: str = ""
    # Последние значения UI
    last_diarize: bool = False
    last_translate_en: bool = False
    # Язык интерфейса: "auto" | "ru" | "uk" | "en"
    ui_lang: str = "auto"
    # Тема интерфейса: "dark" | "light"
    ui_theme: str = "dark"

    def __post_init__(self):
        if not self.output_dir:
            self.output_dir = default_output_dir()

    # -- persistence ---------------------------------------------------

    @classmethod
    def _path(cls) -> Path:
        return app_data_dir() / "config.json"

    @classmethod
    def load(cls) -> "AppConfig":
        p = cls._path()
        if p.exists():
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
                known = {f.name for f in fields(cls)}
                return cls(**{k: v for k, v in raw.items() if k in known})
            except Exception:
                pass
        return cls()

    def save(self) -> None:
        try:
            self._path().write_text(
                json.dumps(asdict(self), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    # -- helpers -------------------------------------------------------

    def active_api_key(self) -> str:
        return self.groq_api_key if self.cloud_provider == "groq" else self.openai_api_key

    def engine_label(self) -> str:
        if self.engine == "local":
            return tr("Локальный Whisper ({})").format(self.local_model)
        prov = "Groq" if self.cloud_provider == "groq" else "OpenAI"
        return tr("Облачный API ({})").format(prov)


# Языки для выпадающих списков: (название, код)
LANGUAGES = [
    ("Авто", ""),
    ("Русский", "ru"),
    ("Українська", "uk"),
    ("English", "en"),
    ("Deutsch", "de"),
    ("Français", "fr"),
    ("Español", "es"),
    ("Italiano", "it"),
    ("Polski", "pl"),
    ("Português", "pt"),
    ("Türkçe", "tr"),
    ("Қазақша", "kk"),
    ("中文", "zh"),
    ("日本語", "ja"),
    ("한국어", "ko"),
    ("العربية", "ar"),
    ("हिन्दी", "hi"),
    ("Nederlands", "nl"),
    ("Čeština", "cs"),
]

# Модели faster-whisper: (id, подпись)
WHISPER_MODELS = [
    ("tiny", "tiny — ~75 МБ, самая быстрая, низкая точность"),
    ("base", "base — ~140 МБ, быстрая"),
    ("small", "small — ~460 МБ, хороший баланс"),
    ("medium", "medium — ~1.5 ГБ, высокая точность"),
    ("large-v2", "large-v2 — ~3 ГБ, очень высокая точность"),
    ("large-v3", "large-v3 — ~3 ГБ, максимальная точность (как TurboScribe)"),
]
