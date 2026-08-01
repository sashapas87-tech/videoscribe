"""Окно настроек: движок, модели, ключи API, диаризация, сохранение."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QRadioButton, QVBoxLayout, QWidget,
)

from ..config import LANGUAGES, WHISPER_MODELS, AppConfig
from ..core import diarize
from ..i18n import tr


def _key_row(edit: QLineEdit) -> QWidget:
    """Поле ключа с кнопкой показать/скрыть."""
    edit.setEchoMode(QLineEdit.Password)
    btn = QPushButton("👁")
    btn.setFixedWidth(34)
    btn.setCheckable(True)

    def toggle(checked):
        edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)

    btn.toggled.connect(toggle)
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(edit, 1)
    lay.addWidget(btn)
    return w


class SettingsDialog(QDialog):
    def __init__(self, cfg: AppConfig, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle(tr("Настройки"))
        self.setMinimumWidth(560)

        root = QVBoxLayout(self)
        root.setSpacing(10)

        # --- Движок -----------------------------------------------------
        g_engine = QGroupBox(tr("Движок транскрибации"))
        v = QVBoxLayout(g_engine)

        self.rb_local = QRadioButton(tr("Локальный Whisper — офлайн и бесплатно (faster-whisper)"))
        self.rb_cloud = QRadioButton(tr("Облачный API — быстро, нужен API-ключ"))
        v.addWidget(self.rb_local)

        local_form = QFormLayout()
        local_form.setContentsMargins(24, 0, 0, 8)
        self.cmb_model = QComboBox()
        for mid, label in WHISPER_MODELS:
            self.cmb_model.addItem(tr(label), mid)
        self.cmb_device = QComboBox()
        self.cmb_device.addItem(tr("Авто (GPU, если доступен)"), "auto")
        self.cmb_device.addItem("CPU", "cpu")
        self.cmb_device.addItem("GPU (NVIDIA CUDA)", "cuda")
        self.chk_vad = QCheckBox(tr("Фильтр тишины (VAD) — убирает галлюцинации на паузах"))
        local_form.addRow(tr("Модель:"), self.cmb_model)
        local_form.addRow(tr("Устройство:"), self.cmb_device)
        local_form.addRow("", self.chk_vad)
        v.addLayout(local_form)

        v.addWidget(self.rb_cloud)
        cloud_form = QFormLayout()
        cloud_form.setContentsMargins(24, 0, 0, 0)
        self.cmb_provider = QComboBox()
        self.cmb_provider.addItem(tr("Groq — whisper-large-v3, быстрый и дешёвый"), "groq")
        self.cmb_provider.addItem("OpenAI — whisper-1", "openai")
        self.ed_groq = QLineEdit()
        self.ed_openai = QLineEdit()
        keys_hint = QLabel(
            tr('Ключи: <a href="https://console.groq.com/keys">console.groq.com/keys</a> · <a href="https://platform.openai.com/api-keys">platform.openai.com/api-keys</a>')
        )
        keys_hint.setOpenExternalLinks(True)
        cloud_form.addRow(tr("Провайдер:"), self.cmb_provider)
        cloud_form.addRow(tr("Ключ Groq:"), _key_row(self.ed_groq))
        cloud_form.addRow(tr("Ключ OpenAI:"), _key_row(self.ed_openai))
        cloud_form.addRow("", keys_hint)
        v.addLayout(cloud_form)
        root.addWidget(g_engine)

        # --- Диаризация ---------------------------------------------------
        g_diar = QGroupBox(tr("Определение спикеров (диаризация)"))
        f = QFormLayout(g_diar)
        self.ed_hf = QLineEdit()
        f.addRow(tr("Токен Hugging Face:"), _key_row(self.ed_hf))
        status = tr("установлены") if diarize.is_available() else \
            tr("не установлены — выполните install-diarization.bat")
        diar_hint = QLabel(
            tr('Пакеты pyannote/torch: <b>{}</b>.<br>Токен: <a href="https://huggingface.co/settings/tokens">huggingface.co/settings/tokens</a> (бесплатно). Затем примите условия моделей:<br><a href="https://huggingface.co/pyannote/speaker-diarization-3.1">speaker-diarization-3.1</a> и <a href="https://huggingface.co/pyannote/segmentation-3.0">segmentation-3.0</a>').format(status)
        )
        diar_hint.setOpenExternalLinks(True)
        diar_hint.setWordWrap(True)
        f.addRow("", diar_hint)
        root.addWidget(g_diar)

        # --- Общее ---------------------------------------------------------
        g_common = QGroupBox(tr("Общее"))
        f2 = QFormLayout(g_common)
        self.cmb_ui_theme = QComboBox()
        self.cmb_ui_theme.addItem(tr("Тёмная"), "dark")
        self.cmb_ui_theme.addItem(tr("Светлая"), "light")
        self.cmb_ui_lang = QComboBox()
        for label, code in ((tr("Авто (как в системе)"), "auto"), ("Русский", "ru"),
                            ("Українська", "uk"), ("English", "en")):
            self.cmb_ui_lang.addItem(label, code)
        self.cmb_lang = QComboBox()
        for name, code in LANGUAGES:
            self.cmb_lang.addItem(tr(name), code)
        self.ed_outdir = QLineEdit()
        btn_browse = QPushButton(tr("Обзор…"))

        def browse():
            d = QFileDialog.getExistingDirectory(self, tr("Папка для сохранения"),
                                                 self.ed_outdir.text())
            if d:
                self.ed_outdir.setText(d)

        btn_browse.clicked.connect(browse)
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.ed_outdir, 1)
        rl.addWidget(btn_browse)
        f2.addRow(tr("Тема интерфейса:"), self.cmb_ui_theme)
        f2.addRow(tr("Язык интерфейса:"), self.cmb_ui_lang)
        f2.addRow(tr("Язык видео по умолчанию:"), self.cmb_lang)
        f2.addRow(tr("Папка сохранения:"), row)
        root.addWidget(g_common)

        note = QLabel(tr("Ключи хранятся локально в файле настроек на этом компьютере."))
        note.setObjectName("hint")
        root.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(tr("Сохранить"))
        buttons.button(QDialogButtonBox.Cancel).setText(tr("Отмена"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._load()

    # -------------------------------------------------------------------

    def _load(self):
        c = self.cfg
        (self.rb_local if c.engine == "local" else self.rb_cloud).setChecked(True)
        i = self.cmb_model.findData(c.local_model)
        self.cmb_model.setCurrentIndex(max(0, i))
        i = self.cmb_device.findData(c.device)
        self.cmb_device.setCurrentIndex(max(0, i))
        self.chk_vad.setChecked(c.vad_filter)
        i = self.cmb_provider.findData(c.cloud_provider)
        self.cmb_provider.setCurrentIndex(max(0, i))
        self.ed_groq.setText(c.groq_api_key)
        self.ed_openai.setText(c.openai_api_key)
        self.ed_hf.setText(c.hf_token)
        i = self.cmb_lang.findData(c.default_language)
        self.cmb_lang.setCurrentIndex(max(0, i))
        i = self.cmb_ui_lang.findData(getattr(c, "ui_lang", "auto") or "auto")
        self.cmb_ui_lang.setCurrentIndex(max(0, i))
        i = self.cmb_ui_theme.findData(getattr(c, "ui_theme", "dark") or "dark")
        self.cmb_ui_theme.setCurrentIndex(max(0, i))
        self.ed_outdir.setText(c.output_dir)

    def accept(self):
        c = self.cfg
        c.engine = "local" if self.rb_local.isChecked() else "cloud"
        c.local_model = self.cmb_model.currentData()
        c.device = self.cmb_device.currentData()
        c.vad_filter = self.chk_vad.isChecked()
        c.cloud_provider = self.cmb_provider.currentData()
        c.groq_api_key = self.ed_groq.text().strip()
        c.openai_api_key = self.ed_openai.text().strip()
        c.hf_token = self.ed_hf.text().strip()
        c.default_language = self.cmb_lang.currentData()
        if self.ed_outdir.text().strip():
            c.output_dir = self.ed_outdir.text().strip()
        new_theme = self.cmb_ui_theme.currentData()
        if new_theme != getattr(c, "ui_theme", "dark"):
            c.ui_theme = new_theme
            from PySide6.QtWidgets import QApplication
            from .style import apply_style
            apply_style(QApplication.instance(), new_theme)
        new_ui_lang = self.cmb_ui_lang.currentData()
        if new_ui_lang != c.ui_lang:
            c.ui_lang = new_ui_lang
            QMessageBox.information(
                self, tr("Язык интерфейса"),
                tr("Язык интерфейса изменится после перезапуска программы."))
        c.save()
        super().accept()
