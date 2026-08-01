"""Фоновые потоки: транскрибация и перевод не блокируют интерфейс."""
from __future__ import annotations

import threading
import traceback

from PySide6.QtCore import QThread, Signal

from ..config import AppConfig
from ..core.models import AppError, JobCancelled, JobSpec, Transcript
from ..core.pipeline import run_job
from ..engines.base import EngineCallbacks
from ..translate import translate_transcript
from ..i18n import tr


class _BaseWorker(QThread):
    sig_stage = Signal(str)
    sig_progress = Signal(object)   # float 0..100 или None (неопределённый)
    sig_message = Signal(str)
    sig_done = Signal(object)       # Transcript
    sig_failed = Signal(str)
    sig_cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def _callbacks(self) -> EngineCallbacks:
        return EngineCallbacks(
            stage=self.sig_stage.emit,
            progress=self.sig_progress.emit,
            message=self.sig_message.emit,
            is_cancelled=self._cancel.is_set,
        )

    def _work(self) -> Transcript:  # переопределяется
        raise NotImplementedError

    def run(self):
        try:
            self.sig_done.emit(self._work())
        except JobCancelled:
            self.sig_cancelled.emit()
        except AppError as e:
            self.sig_failed.emit(str(e))
        except Exception:
            self.sig_failed.emit(tr("Непредвиденная ошибка:\n") + traceback.format_exc(limit=5))


class PipelineWorker(_BaseWorker):
    def __init__(self, spec: JobSpec, cfg: AppConfig, parent=None):
        super().__init__(parent)
        self.spec = spec
        self.cfg = cfg

    def _work(self) -> Transcript:
        return run_job(self.spec, self.cfg, self._callbacks())


class TranslateWorker(_BaseWorker):
    def __init__(self, transcript: Transcript, target_lang: str,
                 provider: str, api_key: str, parent=None):
        super().__init__(parent)
        self.transcript = transcript
        self.target_lang = target_lang
        self.provider = provider
        self.api_key = api_key

    def _work(self) -> Transcript:
        return translate_transcript(
            self.transcript, self.target_lang,
            self.provider, self.api_key, self._callbacks(),
        )
