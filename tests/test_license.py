"""Проверка логики лицензирования (без GUI)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "seller_private"))

from app import licensing  # noqa: E402
import keygen  # noqa: E402

OK, FAIL = [], []
def check(name, cond):
    (OK if cond else FAIL).append(name)
    print(("[OK]  " if cond else "[FAIL]") + " " + name)

# чистим прошлую лицензию
lic = licensing._license_path()
if lic.exists():
    lic.unlink()

mid = licensing.current_machine_id()
print("Machine ID:", mid)
check("формат Machine ID", mid.startswith("VS-") and len(mid) == 22)
check("Machine ID стабилен", mid == licensing.current_machine_id())

# до активации — пробный режим
check("до активации не licensed", licensing.is_licensed() is False)

# правильный ключ для этого ПК
key = keygen.make_key(mid, "test@buyer.com", "")
ok, info = licensing.activate(key)
check("активация верным ключом", ok and info.licensed)
check("лицензия сохранена", lic.exists())
check("после активации licensed", licensing.is_licensed() is True)
check("статус содержит имя", "test@buyer.com" in info.status_text)

# перезапуск (перечитать с диска)
check("лицензия читается заново", licensing.load_status().licensed)

# ключ для другого ПК
lic.unlink()
foreign = keygen.make_key("VS-0000-0000-0000-0000", "", "")
ok2, info2 = licensing.activate(foreign)
check("ключ чужого ПК отвергнут", (not ok2) and "другого компьютера" in info2.error)

# подделанный ключ (меняем символ в подписи)
bad = key[:-3] + ("A" if key[-1] != "A" else "B") + key[-2:]
ok3, info3 = licensing.activate(bad)
check("поддельная подпись отвергнута", not ok3)

# истёкший срок
expired = keygen.make_key(mid, "", "2000-01-01")
ok4, info4 = licensing.activate(expired)
check("истёкший ключ отвергнут", (not ok4) and "истёк" in info4.error)

# ключ со сроком в будущем
future = keygen.make_key(mid, "", "2099-01-01")
ok5, info5 = licensing.activate(future)
check("ключ со сроком в будущем принят", ok5 and info5.licensed)

# обрезка аудио для пробного режима
lic.unlink()
from app.core import ffmpeg_utils  # noqa: E402
import tempfile, subprocess
tmp = Path(tempfile.mkdtemp())
src = tmp / "src.wav"
subprocess.run([ffmpeg_utils.find_ffmpeg(), "-y", "-f", "lavfi", "-i",
                "sine=frequency=440:duration=300", "-ar", "16000", "-ac", "1",
                str(src)], capture_output=True)
dst = tmp / "trim.wav"
ffmpeg_utils.trim_wav(str(src), str(dst), 180)
dur = ffmpeg_utils.get_duration(str(dst))
check("обрезка до 180 c", 178 <= dur <= 182)

print(f"\nИтого: OK={len(OK)}, FAIL={len(FAIL)}")
sys.exit(1 if FAIL else 0)
