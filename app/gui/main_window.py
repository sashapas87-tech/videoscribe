"""Главное окно VideoScribe."""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import (
    QBrush, QColor, QDragEnterEvent, QDropEvent, QFont, QGuiApplication, QIcon,
    QPainter, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSplitter,
    QStackedWidget, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
    QWidget, QAbstractItemView, QHeaderView,
)

from ..config import LANGUAGES, AppConfig
from ..core import diarize
from ..core.media import VIDEO_AUDIO_EXTS, looks_like_url, safe_filename
from ..core.models import JobSpec, Transcript
from ..exporters.common import ts_short
from ..exporters.docx_pdf import export_docx, export_pdf
from ..exporters.text_formats import export_srt, export_txt, export_vtt
from ..translate import TRANSLATE_TARGETS
from .settings_dialog import SettingsDialog
from .workers import PipelineWorker, TranslateWorker

STATUS_ICONS = {
    "queued": "⏳", "running": "▶", "done": "✓", "error": "✗", "cancelled": "⊘",
}


def make_app_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QBrush(QColor("#3d6df2")))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(2, 2, 60, 60), 14, 14)
    pen = QPen(QColor("white"), 5)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    for i, h in enumerate((14, 26, 38, 26, 14)):
        x = 14 + i * 9
        p.drawLine(x, 32 - h // 2, x, 32 + h // 2)
    p.end()
    return QIcon(pm)


@dataclass
class JobState:
    id: str
    spec: JobSpec
    name: str
    status: str = "queued"           # queued/running/done/error/cancelled
    stage: str = "В очереди"
    transcript: Optional[Transcript] = None
    error: str = ""


class TranslateDialog(QDialog):
    """Выбор целевого языка перевода."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Перевод транскрипта")
        form = QFormLayout(self)
        self.cmb = QComboBox()
        for label, prompt in TRANSLATE_TARGETS:
            self.cmb.addItem(label, prompt)
        self.ed_custom = QLineEdit()
        self.ed_custom.setPlaceholderText("например: грузинский")
        form.addRow("Язык:", self.cmb)
        form.addRow("Или свой:", self.ed_custom)
        note = QLabel("Перевод выполняется через облачный API (Groq или OpenAI) —\n"
                      "нужен ключ в Настройках. Таймкоды и спикеры сохраняются.")
        note.setObjectName("hint")
        form.addRow(note)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Перевести")
        bb.button(QDialogButtonBox.Cancel).setText("Отмена")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def target(self):
        custom = self.ed_custom.text().strip()
        if custom:
            return custom.capitalize(), custom
        return self.cmb.currentText(), self.cmb.currentData()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = AppConfig.load()
        self.jobs: Dict[str, JobState] = {}
        self.pending: List[str] = []
        self.active_job_id: Optional[str] = None
        self.worker = None          # PipelineWorker | TranslateWorker
        self._filling_table = False

        self.setWindowTitle("VideoScribe — транскрибация видео и аудио")
        self.setWindowIcon(make_app_icon())
        self.resize(1120, 700)
        self.setAcceptDrops(True)

        self._build_ui()
        self._update_engine_label()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 8)
        root.setSpacing(8)

        # -- строка ввода
        row1 = QHBoxLayout()
        self.ed_url = QLineEdit()
        self.ed_url.setPlaceholderText(
            "Вставьте ссылку на YouTube (или другой сайт с видео) и нажмите «Транскрибировать»…")
        self.ed_url.returnPressed.connect(self._add_url_job)
        btn_go = QPushButton("Транскрибировать")
        btn_go.setObjectName("primary")
        btn_go.clicked.connect(self._add_url_job)
        btn_file = QPushButton("Открыть файл…")
        btn_file.clicked.connect(self._open_files)
        row1.addWidget(self.ed_url, 1)
        row1.addWidget(btn_go)
        row1.addWidget(btn_file)
        root.addLayout(row1)

        # -- строка опций
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Язык:"))
        self.cmb_lang = QComboBox()
        for name, code in LANGUAGES:
            self.cmb_lang.addItem(name, code)
        i = self.cmb_lang.findData(self.cfg.default_language)
        self.cmb_lang.setCurrentIndex(max(0, i))
        row2.addWidget(self.cmb_lang)

        self.chk_diarize = QCheckBox("Определять спикеров")
        self.chk_diarize.setChecked(self.cfg.last_diarize and diarize.is_available())
        self.chk_diarize.setToolTip(
            "Разметка «кто говорит» (pyannote). Требует установленных пакетов "
            "диаризации и токена Hugging Face в Настройках.")
        row2.addWidget(self.chk_diarize)

        self.cmb_speakers = QComboBox()
        self.cmb_speakers.addItem("Спикеров: авто", None)
        for n in range(2, 9):
            self.cmb_speakers.addItem(f"Спикеров: {n}", n)
        self.cmb_speakers.setEnabled(self.chk_diarize.isChecked())
        self.chk_diarize.toggled.connect(self.cmb_speakers.setEnabled)
        row2.addWidget(self.cmb_speakers)

        self.chk_translate_en = QCheckBox("Сразу перевести на английский")
        self.chk_translate_en.setChecked(self.cfg.last_translate_en)
        self.chk_translate_en.setToolTip(
            "Встроенный режим Whisper: распознать и перевести на английский за один проход.")
        row2.addWidget(self.chk_translate_en)

        row2.addStretch(1)
        self.lbl_engine = QLabel()
        self.lbl_engine.setObjectName("engineLabel")
        row2.addWidget(self.lbl_engine)
        btn_settings = QPushButton("⚙ Настройки")
        btn_settings.clicked.connect(self._open_settings)
        row2.addWidget(btn_settings)
        root.addLayout(row2)

        # -- основная область
        split = QSplitter(Qt.Horizontal)

        self.lst_jobs = QListWidget()
        self.lst_jobs.setMinimumWidth(250)
        self.lst_jobs.currentItemChanged.connect(lambda *_: self._render_selected())
        split.addWidget(self.lst_jobs)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()

        # страница-заглушка
        page_empty = QWidget()
        pe = QVBoxLayout(page_empty)
        self.lbl_empty = QLabel(
            "Добавьте ссылку на видео или перетащите файл в окно.\n\n"
            "Поддерживаются YouTube и сотни других сайтов,\n"
            "а также локальные видео- и аудиофайлы\n"
            "(MP4, MKV, AVI, MOV, MP3, WAV, M4A и др.)")
        self.lbl_empty.setObjectName("hint")
        self.lbl_empty.setAlignment(Qt.AlignCenter)
        pe.addStretch(1)
        pe.addWidget(self.lbl_empty)
        pe.addStretch(1)
        self.stack.addWidget(page_empty)

        # страница результата
        page_res = QWidget()
        pr = QVBoxLayout(page_res)
        pr.setContentsMargins(0, 0, 0, 0)
        self.lbl_info = QLabel()
        self.lbl_info.setObjectName("jobInfo")
        self.lbl_info.setWordWrap(True)
        pr.addWidget(self.lbl_info)

        self.tabs = QTabWidget()
        self.tbl = QTableWidget(0, 3)
        self.tbl.setHorizontalHeaderLabels(["Время", "Спикер", "Текст"])
        self.tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setWordWrap(True)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.itemChanged.connect(self._on_cell_edited)
        self.tabs.addTab(self.tbl, "Сегменты")

        self.txt_view = QPlainTextEdit()
        self.txt_view.setReadOnly(True)
        self.tabs.addTab(self.txt_view, "Текст")
        self.tabs.currentChanged.connect(self._refresh_text_tab)
        pr.addWidget(self.tabs, 1)

        exp = QHBoxLayout()
        for label, fmt in (("TXT", "txt"), ("SRT", "srt"), ("VTT", "vtt"),
                           ("DOCX", "docx"), ("PDF", "pdf")):
            b = QPushButton(f"Экспорт {label}")
            b.clicked.connect(lambda _=False, f=fmt: self._export(f))
            exp.addWidget(b)
        exp.addStretch(1)
        btn_tr = QPushButton("Перевести…")
        btn_tr.clicked.connect(self._translate_current)
        exp.addWidget(btn_tr)
        btn_copy = QPushButton("Копировать текст")
        btn_copy.clicked.connect(self._copy_all)
        exp.addWidget(btn_copy)
        pr.addLayout(exp)
        self.stack.addWidget(page_res)

        # страница статуса задания
        page_status = QWidget()
        ps = QVBoxLayout(page_status)
        self.lbl_status_big = QLabel()
        self.lbl_status_big.setObjectName("hint")
        self.lbl_status_big.setAlignment(Qt.AlignCenter)
        self.lbl_status_big.setWordWrap(True)
        ps.addStretch(1)
        ps.addWidget(self.lbl_status_big)
        ps.addStretch(1)
        self.stack.addWidget(page_status)

        rv.addWidget(self.stack)
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([280, 840])
        root.addWidget(split, 1)

        self.setCentralWidget(central)

        # -- статус-бар с прогрессом
        self.lbl_stage = QLabel("Готов к работе")
        self.bar = QProgressBar()
        self.bar.setFixedWidth(260)
        self.bar.setVisible(False)
        self.btn_cancel = QPushButton("Отменить")
        self.btn_cancel.setObjectName("danger")
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self._cancel_active)
        sb = self.statusBar()
        sb.addWidget(self.lbl_stage, 1)
        sb.addPermanentWidget(self.bar)
        sb.addPermanentWidget(self.btn_cancel)

    # ------------------------------------------------------- добавление задач

    def _current_options(self) -> dict:
        return {
            "language": self.cmb_lang.currentData() or None,
            "translate_to_en": self.chk_translate_en.isChecked(),
            "diarize": self.chk_diarize.isChecked(),
            "num_speakers": self.cmb_speakers.currentData(),
        }

    def _add_url_job(self):
        url = self.ed_url.text().strip()
        if not url:
            return
        if not looks_like_url(url):
            QMessageBox.warning(self, "Ссылка", "Это не похоже на ссылку. "
                                "Пример: https://www.youtube.com/watch?v=…")
            return
        if self.chk_diarize.isChecked() and not self._diarize_ready():
            return
        self.ed_url.clear()
        spec = JobSpec(source_type="url", source=url, **self._current_options())
        self._enqueue(spec, url)

    def _open_files(self):
        exts = " ".join(f"*{e}" for e in sorted(VIDEO_AUDIO_EXTS))
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Выберите видео или аудио", str(Path.home()),
            f"Видео и аудио ({exts});;Все файлы (*.*)")
        if paths and self.chk_diarize.isChecked() and not self._diarize_ready():
            return
        for p in paths:
            spec = JobSpec(source_type="file", source=p, **self._current_options())
            self._enqueue(spec, Path(p).name)

    def _diarize_ready(self) -> bool:
        if not diarize.is_available():
            QMessageBox.warning(
                self, "Диаризация",
                "Пакеты для определения спикеров не установлены.\n"
                "Запустите install-diarization.bat (или pip install -r "
                "requirements-diarization.txt), либо снимите галочку.")
            return False
        if not self.cfg.hf_token.strip():
            QMessageBox.warning(
                self, "Диаризация",
                "Нужен токен Hugging Face — добавьте его в Настройках\n"
                "(huggingface.co/settings/tokens, бесплатно)\n"
                "и примите условия моделей pyannote.")
            return False
        return True

    def _enqueue(self, spec: JobSpec, name: str):
        jid = uuid.uuid4().hex[:8]
        job = JobState(id=jid, spec=spec, name=name)
        self.jobs[jid] = job
        item = QListWidgetItem()
        item.setData(Qt.UserRole, jid)
        self.lst_jobs.addItem(item)
        self._update_item(job)
        self.lst_jobs.setCurrentItem(item)
        self.pending.append(jid)
        self._start_next()

    # ------------------------------------------------------------- очередь

    def _item_for(self, jid: str) -> Optional[QListWidgetItem]:
        for i in range(self.lst_jobs.count()):
            it = self.lst_jobs.item(i)
            if it.data(Qt.UserRole) == jid:
                return it
        return None

    def _update_item(self, job: JobState):
        it = self._item_for(job.id)
        if it:
            icon = STATUS_ICONS.get(job.status, "")
            title = job.transcript.title if job.transcript else job.name
            it.setText(f"{icon} {title}\n{job.stage}")

    def _start_next(self):
        if self.worker is not None or not self.pending:
            return
        jid = self.pending.pop(0)
        job = self.jobs.get(jid)
        if job is None:
            return self._start_next()
        self.active_job_id = jid
        job.status, job.stage = "running", "Запуск…"
        self._update_item(job)

        w = PipelineWorker(job.spec, self.cfg)
        self.worker = w
        w.sig_stage.connect(self._on_stage)
        w.sig_progress.connect(self._on_progress)
        w.sig_message.connect(self._on_message)
        w.sig_done.connect(self._on_done)
        w.sig_failed.connect(self._on_failed)
        w.sig_cancelled.connect(self._on_cancelled)
        w.finished.connect(self._on_worker_finished)
        self._set_busy(True)
        w.start()
        self._render_selected()

    def _set_busy(self, busy: bool):
        self.bar.setVisible(busy)
        self.btn_cancel.setVisible(busy)
        if not busy:
            self.lbl_stage.setText("Готов к работе")

    def _active_job(self) -> Optional[JobState]:
        return self.jobs.get(self.active_job_id) if self.active_job_id else None

    # сигналы воркера ----------------------------------------------------

    def _on_stage(self, stage: str):
        job = self._active_job()
        if job:
            job.stage = stage
            self._update_item(job)
        self.lbl_stage.setText(stage)
        self._render_selected(only_status=True)

    def _on_progress(self, value):
        if value is None:
            self.bar.setRange(0, 0)
        else:
            self.bar.setRange(0, 100)
            self.bar.setValue(int(value))

    def _on_message(self, msg: str):
        self.lbl_stage.setText(msg)

    def _on_done(self, transcript: Transcript):
        job = self._active_job()
        if job:
            job.transcript = transcript
            job.status, job.stage = "done", self._done_summary(transcript)
            self._update_item(job)

    def _on_failed(self, err: str):
        job = self._active_job()
        if job:
            job.status, job.stage, job.error = "error", "Ошибка", err
            self._update_item(job)

    def _on_cancelled(self):
        job = self._active_job()
        if job:
            job.status, job.stage = "cancelled", "Отменено"
            self._update_item(job)

    def _on_worker_finished(self):
        w = self.worker
        self.worker = None
        self.active_job_id = None
        if w:
            w.deleteLater()
        self._set_busy(False)
        self._render_selected()
        self._start_next()

    @staticmethod
    def _done_summary(t: Transcript) -> str:
        parts = [f"Готово · {ts_short(t.duration)}"]
        if t.language:
            parts.append(t.language)
        if t.has_speakers:
            parts.append(f"{len(t.speakers)} спикера(ов)")
        return " · ".join(parts)

    def _cancel_active(self):
        if self.worker:
            self.worker.cancel()
            self.lbl_stage.setText("Отмена…")

    # ------------------------------------------------------------ отображение

    def _selected_job(self) -> Optional[JobState]:
        it = self.lst_jobs.currentItem()
        return self.jobs.get(it.data(Qt.UserRole)) if it else None

    def _render_selected(self, only_status: bool = False):
        job = self._selected_job()
        if job is None:
            self.stack.setCurrentIndex(0)
            return
        if job.transcript is not None:
            if not only_status:
                self._fill_result(job)
            self.stack.setCurrentIndex(1)
        elif job.status == "error":
            self.lbl_status_big.setText(f"✗ Ошибка\n\n{job.error}")
            self.stack.setCurrentIndex(2)
        elif job.status == "cancelled":
            self.lbl_status_big.setText("⊘ Задание отменено")
            self.stack.setCurrentIndex(2)
        else:
            state = "Выполняется" if job.status == "running" else "В очереди"
            self.lbl_status_big.setText(f"{state}: {job.stage}")
            self.stack.setCurrentIndex(2)

    def _fill_result(self, job: JobState):
        t = job.transcript
        info = [f"<b>{t.title}</b>"]
        meta = [ts_short(t.duration), f"{len(t.segments)} сегм."]
        if t.language:
            meta.append(f"язык: {t.language}")
        if t.engine:
            meta.append(t.engine)
        info.append(" · ".join(meta))
        self.lbl_info.setText("<br>".join(info))

        self._filling_table = True
        try:
            has_sp = t.has_speakers
            self.tbl.setColumnHidden(1, not has_sp)
            self.tbl.setRowCount(len(t.segments))
            for r, s in enumerate(t.segments):
                it_time = QTableWidgetItem(f"{ts_short(s.start)}–{ts_short(s.end)}")
                it_time.setFlags(it_time.flags() & ~Qt.ItemIsEditable)
                self.tbl.setItem(r, 0, it_time)
                self.tbl.setItem(r, 1, QTableWidgetItem(s.speaker or ""))
                self.tbl.setItem(r, 2, QTableWidgetItem(s.text))
        finally:
            self._filling_table = False
        self._refresh_text_tab()

    def _refresh_text_tab(self, *_):
        job = self._selected_job()
        if job and job.transcript and self.tabs.currentIndex() == 1:
            self.txt_view.setPlainText(job.transcript.full_text())

    def _on_cell_edited(self, item: QTableWidgetItem):
        if self._filling_table:
            return
        job = self._selected_job()
        if not job or not job.transcript:
            return
        r, c = item.row(), item.column()
        if r >= len(job.transcript.segments):
            return
        seg = job.transcript.segments[r]
        if c == 2:
            seg.text = item.text()
        elif c == 1:
            seg.speaker = item.text().strip() or None

    # ------------------------------------------------------------- экспорт

    def _export(self, fmt: str):
        job = self._selected_job()
        if not job or not job.transcript:
            QMessageBox.information(self, "Экспорт", "Сначала выберите готовый транскрипт.")
            return
        t = job.transcript
        Path(self.cfg.output_dir).mkdir(parents=True, exist_ok=True)
        default = str(Path(self.cfg.output_dir) / f"{safe_filename(t.title)}.{fmt}")
        filters = {
            "txt": "Текст (*.txt)", "srt": "Субтитры SRT (*.srt)",
            "vtt": "Субтитры WebVTT (*.vtt)", "docx": "Документ Word (*.docx)",
            "pdf": "PDF (*.pdf)",
        }
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить как", default, filters[fmt])
        if not path:
            return
        try:
            {"txt": export_txt, "srt": export_srt, "vtt": export_vtt,
             "docx": export_docx, "pdf": export_pdf}[fmt](t, path)
        except Exception as e:
            QMessageBox.critical(self, "Экспорт", f"Не удалось сохранить файл:\n{e}")
            return
        self.lbl_stage.setText(f"Сохранено: {path}")
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle("Экспорт")
        box.setText(f"Файл сохранён:\n{path}")
        btn_open = box.addButton("Открыть папку", QMessageBox.ActionRole)
        box.addButton("ОК", QMessageBox.AcceptRole)
        box.exec()
        if box.clickedButton() is btn_open:
            self._open_folder(str(Path(path).parent))

    @staticmethod
    def _open_folder(path: str):
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    def _copy_all(self):
        job = self._selected_job()
        if job and job.transcript:
            QGuiApplication.clipboard().setText(job.transcript.full_text())
            self.lbl_stage.setText("Текст скопирован в буфер обмена.")

    # ------------------------------------------------------------- перевод

    def _translate_current(self):
        job = self._selected_job()
        if not job or not job.transcript:
            QMessageBox.information(self, "Перевод", "Сначала выберите готовый транскрипт.")
            return
        if self.worker is not None:
            QMessageBox.information(self, "Перевод", "Дождитесь завершения текущего задания.")
            return
        key = self.cfg.active_api_key()
        if not key:
            QMessageBox.warning(self, "Перевод",
                                "Для перевода нужен API-ключ Groq или OpenAI — задайте его в Настройках.")
            return
        dlg = TranslateDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        label, prompt_lang = dlg.target()

        src = job.transcript
        jid = uuid.uuid4().hex[:8]
        new_job = JobState(id=jid, spec=job.spec,
                           name=f"{src.title} → {label}",
                           status="running", stage=f"Перевод на {label}…")
        self.jobs[jid] = new_job
        item = QListWidgetItem()
        item.setData(Qt.UserRole, jid)
        self.lst_jobs.addItem(item)
        self._update_item(new_job)
        self.lst_jobs.setCurrentItem(item)

        self.active_job_id = jid
        w = TranslateWorker(src, prompt_lang, self.cfg.cloud_provider, key)
        self.worker = w
        w.sig_stage.connect(self._on_stage)
        w.sig_progress.connect(self._on_progress)
        w.sig_message.connect(self._on_message)
        w.sig_done.connect(self._on_done)
        w.sig_failed.connect(self._on_failed)
        w.sig_cancelled.connect(self._on_cancelled)
        w.finished.connect(self._on_worker_finished)
        self._set_busy(True)
        w.start()
        self._render_selected()

    # -------------------------------------------------------------- прочее

    def _open_settings(self):
        dlg = SettingsDialog(self.cfg, self)
        if dlg.exec() == QDialog.Accepted:
            self._update_engine_label()

    def _update_engine_label(self):
        self.lbl_engine.setText(f"Движок: {self.cfg.engine_label()}")

    # drag & drop ---------------------------------------------------------

    def dragEnterEvent(self, e: QDragEnterEvent):
        md = e.mimeData()
        if md.hasUrls() or (md.hasText() and looks_like_url(md.text())):
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent):
        md = e.mimeData()
        if md.hasUrls():
            for u in md.urls():
                if u.isLocalFile():
                    p = u.toLocalFile()
                    if Path(p).suffix.lower() in VIDEO_AUDIO_EXTS:
                        spec = JobSpec(source_type="file", source=p, **self._current_options())
                        self._enqueue(spec, Path(p).name)
                elif looks_like_url(u.toString()):
                    spec = JobSpec(source_type="url", source=u.toString(),
                                   **self._current_options())
                    self._enqueue(spec, u.toString())
        elif md.hasText() and looks_like_url(md.text()):
            spec = JobSpec(source_type="url", source=md.text().strip(),
                           **self._current_options())
            self._enqueue(spec, md.text().strip())

    def closeEvent(self, e):
        if self.worker is not None:
            r = QMessageBox.question(
                self, "Выход",
                "Задание ещё выполняется. Прервать и выйти?",
                QMessageBox.Yes | QMessageBox.No)
            if r != QMessageBox.Yes:
                e.ignore()
                return
            self.worker.cancel()
            self.worker.wait(3000)
        self.cfg.last_diarize = self.chk_diarize.isChecked()
        self.cfg.last_translate_en = self.chk_translate_en.isChecked()
        self.cfg.default_language = self.cmb_lang.currentData()
        self.cfg.save()
        e.accept()
