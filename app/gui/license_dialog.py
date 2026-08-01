"""Окно активации: показывает Machine ID, принимает лицензионный ключ."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QPushButton, QVBoxLayout,
)

from .. import licensing
from ..i18n import tr
from .style import theme_colors

SUPPORT_EMAIL = "sashapas81@gmail.com"


class LicenseDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Активация VideoScribe"))
        self.setMinimumWidth(560)
        self.info = licensing.load_status()

        root = QVBoxLayout(self)
        root.setSpacing(12)

        # --- статус ---
        self.lbl_status = QLabel()
        self.lbl_status.setWordWrap(True)
        root.addWidget(self.lbl_status)

        # --- Machine ID ---
        box = QFrame()
        tc = theme_colors()
        box.setStyleSheet("QFrame{background:%s;border:1px solid %s;border-radius:8px}"
                          % (tc["field"], tc["border"]))
        bl = QVBoxLayout(box)
        bl.addWidget(QLabel(tr("ID этого компьютера (Machine ID):")))
        row = QHBoxLayout()
        self.ed_mid = QLineEdit(self.info.machine_id)
        self.ed_mid.setReadOnly(True)
        f = self.ed_mid.font()
        f.setFamily("Consolas")
        f.setPointSize(f.pointSize() + 2)
        self.ed_mid.setFont(f)
        btn_copy = QPushButton(tr("Копировать"))
        btn_copy.clicked.connect(self._copy_mid)
        row.addWidget(self.ed_mid, 1)
        row.addWidget(btn_copy)
        bl.addLayout(row)
        root.addWidget(box)

        # --- инструкция покупки ---
        link_color = tc["link"]
        mail_link = f"<a href='mailto:{SUPPORT_EMAIL}' style='color:{link_color}'>{SUPPORT_EMAIL}</a>"
        steps = QLabel(
            tr("<b>Как получить ключ:</b><br>1. Нажмите «Копировать» и отправьте этот Machine ID на почту {} с темой «Покупка VideoScribe».<br>2. В ответ придёт лицензионный ключ именно для этого компьютера.<br>3. Вставьте ключ в поле ниже и нажмите «Активировать».").format(mail_link)
        )
        steps.setOpenExternalLinks(True)
        steps.setWordWrap(True)
        steps.setStyleSheet("color:" + tc["muted2"])
        root.addWidget(steps)

        # --- ввод ключа ---
        root.addWidget(QLabel(tr("Лицензионный ключ:")))
        self.ed_key = QPlainTextEdit()
        self.ed_key.setPlaceholderText(tr("Вставьте сюда ключ из письма…"))
        self.ed_key.setFixedHeight(84)
        root.addWidget(self.ed_key)

        actions = QHBoxLayout()
        btn_file = QPushButton(tr("Загрузить файл .lic…"))
        btn_file.clicked.connect(self._load_file)
        actions.addWidget(btn_file)
        actions.addStretch(1)
        self.btn_close = QPushButton(tr("Продолжить в пробном режиме"))
        self.btn_close.clicked.connect(self.reject)
        self.btn_activate = QPushButton(tr("Активировать"))
        self.btn_activate.setObjectName("primary")
        self.btn_activate.clicked.connect(self._activate)
        actions.addWidget(self.btn_close)
        actions.addWidget(self.btn_activate)
        root.addLayout(actions)

        self._refresh_status()

    # ------------------------------------------------------------------

    def _refresh_status(self):
        tc = theme_colors()
        if self.info.licensed:
            self.lbl_status.setText(
                f"<span style='color:{tc['ok']};font-size:15px'>" + tr("✓ Программа активирована.") + "</span>"
                f"<br><span style='color:{tc['muted2']}'>{self.info.status_text}</span>"
            )
            self.ed_key.setEnabled(False)
            self.btn_activate.setEnabled(False)
            self.btn_close.setText(tr("Закрыть"))
        else:
            self.lbl_status.setText(
                f"<span style='color:{tc['warn']};font-size:15px'>" + tr("⚠ Пробный режим") + "</span>"
                f"<br><span style='color:{tc['muted2']}'>" + tr("Без активации распознаётся только первые 3 минуты каждого файла. Активируйте программу, чтобы снять ограничение.") + "</span>"
            )

    def _copy_mid(self):
        QGuiApplication.clipboard().setText(self.info.machine_id)
        QMessageBox.information(self, tr("Скопировано"),
                               tr("Machine ID скопирован.\nВставьте его в письмо на {}").format(SUPPORT_EMAIL))

    def _load_file(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Файл лицензии"), "",
                                              tr("Лицензия (*.lic *.key *.txt);;Все файлы (*.*)"))
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.ed_key.setPlainText(f.read().strip())
            except Exception as e:
                QMessageBox.warning(self, tr("Файл"), tr("Не удалось прочитать файл:\n{}").format(e))

    def _activate(self):
        key = self.ed_key.toPlainText().strip()
        if not key:
            QMessageBox.warning(self, tr("Активация"), tr("Вставьте лицензионный ключ."))
            return
        ok, info = licensing.activate(key)
        self.info = info
        if ok:
            self._refresh_status()
            QMessageBox.information(self, tr("Активация"),
                                   tr("Готово! Программа активирована на этом компьютере.\nОграничение пробного режима снято."))
            self.accept()
        else:
            QMessageBox.critical(self, tr("Активация не удалась"), info.error or tr("Неверный ключ."))
