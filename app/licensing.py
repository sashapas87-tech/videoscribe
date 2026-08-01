"""Офлайн-лицензирование по схеме «один ключ — один компьютер».

Как это работает:
- У программы зашит ОТКРЫТЫЙ ключ Ed25519 (проверять подписи).
- ЗАКРЫТЫЙ ключ есть только у продавца (в keygen.py). Подделать лицензию
  без него нельзя.
- Machine ID вычисляется из стабильного идентификатора Windows (MachineGuid).
  Лицензия подписывается именно под этот ID, поэтому ключ с одного компьютера
  не подойдёт к другому.

Формат лицензионного ключа (одна строка, можно вставлять/копировать):
    base64url(payload) + "." + base64url(signature)
где payload = "machine_id|name|issued|expiry" (expiry пустой = бессрочно).
"""
from __future__ import annotations

import base64
import hashlib
import platform
import sys
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional, Tuple

from .config import app_data_dir
from .i18n import tr

# --- Открытый ключ продавца (безопасно хранить в открытом виде) -----------
PUBLIC_KEY_B64 = "kFZ/wTOXSAdhMeDIN4LZHtJsMAmjJm3Slp+sBHJOkbI="

_SALT = b"VideoScribe-hwid-v1"
TRIAL_LIMIT_SEC = 180  # до активации распознаём только первые 3 минуты файла


# ======================= Machine ID =======================================

def _raw_machine_id() -> str:
    """Сырой аппаратный идентификатор компьютера."""
    parts = []
    if sys.platform == "win32":
        try:
            import winreg  # type: ignore
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0),
            )
            val, _ = winreg.QueryValueEx(key, "MachineGuid")
            winreg.CloseKey(key)
            if val:
                parts.append(str(val))
        except Exception:
            pass
    if not parts:
        # Запасной вариант (не-Windows или недоступный реестр)
        parts.append(platform.node())
        parts.append(str(uuid.getnode()))  # MAC-адрес
    return "|".join(parts)


def current_machine_id() -> str:
    """Человекочитаемый ID компьютера: VS-XXXX-XXXX-XXXX-XXXX."""
    digest = hashlib.sha256(_SALT + _raw_machine_id().encode("utf-8", "replace")).hexdigest()
    h = digest[:16].upper()
    return "VS-" + "-".join(h[i:i + 4] for i in range(0, 16, 4))


# ======================= Проверка ключа ===================================

def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


@dataclass
class LicenseInfo:
    licensed: bool
    machine_id: str
    name: str = ""
    expiry: str = ""       # "" = бессрочно
    error: str = ""

    @property
    def status_text(self) -> str:
        if self.licensed:
            who = f" · {self.name}" if self.name else ""
            exp = tr(" · до {}").format(self.expiry) if self.expiry else tr(" · бессрочно")
            return tr("Активировано") + who + exp
        return tr("Пробный режим (первые 3 минуты каждого файла)")


def _verify_token(token: str, machine_id: str) -> LicenseInfo:
    """Проверить подпись и привязку ключа к этому компьютеру."""
    token = (token or "").strip().replace("\n", "").replace("\r", "").replace(" ", "")
    if not token or "." not in token:
        return LicenseInfo(False, machine_id, error=tr("Пустой или неполный ключ."))
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
    except ImportError:
        return LicenseInfo(False, machine_id,
                           error=tr("Не установлен пакет cryptography (pip install -r requirements.txt)."))

    try:
        payload_b64, sig_b64 = token.split(".", 1)
        payload = _b64url_decode(payload_b64)
        signature = _b64url_decode(sig_b64)
    except Exception:
        return LicenseInfo(False, machine_id, error=tr("Ключ повреждён или скопирован не полностью."))

    try:
        pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(PUBLIC_KEY_B64))
        pub.verify(signature, payload)
    except InvalidSignature:
        return LicenseInfo(False, machine_id, error=tr("Подпись ключа неверна — ключ поддельный или испорчен."))
    except Exception as e:
        return LicenseInfo(False, machine_id, error=tr("Не удалось проверить ключ: {}").format(e))

    try:
        fields = payload.decode("utf-8").split("|")
        lic_machine = fields[0]
        name = fields[1] if len(fields) > 1 else ""
        expiry = fields[3] if len(fields) > 3 else ""
    except Exception:
        return LicenseInfo(False, machine_id, error=tr("Ключ имеет неизвестный формат."))

    if lic_machine != machine_id:
        return LicenseInfo(False, machine_id,
                           error=tr("Этот ключ выдан для другого компьютера.\nКлюч действует только на том ПК, чей Machine ID был указан при покупке."))

    if expiry:
        try:
            if date.fromisoformat(expiry) < date.today():
                return LicenseInfo(False, machine_id, name=name, expiry=expiry,
                                   error=tr("Срок действия ключа истёк ({}).").format(expiry))
        except ValueError:
            pass

    return LicenseInfo(True, machine_id, name=name, expiry=expiry)


# ======================= Хранение состояния ================================

def _license_path() -> Path:
    return app_data_dir() / "license.key"


def load_status() -> LicenseInfo:
    """Прочитать сохранённую лицензию и перепроверить её на этом компьютере."""
    mid = current_machine_id()
    p = _license_path()
    if not p.exists():
        return LicenseInfo(False, mid)
    try:
        token = p.read_text(encoding="utf-8")
    except Exception:
        return LicenseInfo(False, mid)
    return _verify_token(token, mid)


def activate(token: str) -> Tuple[bool, LicenseInfo]:
    """Проверить ключ и, если верный, сохранить его. Вернуть (успех, инфо)."""
    mid = current_machine_id()
    info = _verify_token(token, mid)
    if info.licensed:
        try:
            _license_path().write_text(token.strip(), encoding="utf-8")
        except Exception as e:
            return False, LicenseInfo(False, mid, error=tr("Ключ верный, но не удалось сохранить: {}").format(e))
    return info.licensed, info


def is_licensed() -> bool:
    return load_status().licensed
