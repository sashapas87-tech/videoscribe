@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1

echo ==============================================
echo VideoScribe — установка библиотек.
echo НЕ ЗАКРЫВАЙТЕ это окно! Обычно 5–15 минут.
echo ==============================================
echo.

if not exist "requirements.txt" goto :wrongdir

echo [1/4] Создаю виртуальное окружение...
python -m venv .venv
if errorlevel 1 goto :fail

echo [2/4] Обновляю pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip

echo [3/4] Устанавливаю библиотеки программы — самый долгий шаг, наберитесь терпения...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo [4/4] Проверяю установку...
".venv\Scripts\python.exe" -c "import PySide6, faster_whisper, yt_dlp, requests, docx, fpdf, cryptography; print('Все библиотеки на месте!')"
if errorlevel 1 goto :fail

echo.
echo ==============================================
echo ГОТОВО! Теперь запускайте программу через run.bat
echo ==============================================
pause
exit /b 0

:wrongdir
echo ОШИБКА: рядом нет requirements.txt — положите install.bat в папку программы, туда же, где run.bat
pause
exit /b 1

:fail
echo.
echo ==============================================
echo ЧТО-ТО ПОШЛО НЕ ТАК. Сфотографируйте это окно целиком и пришлите.
echo ==============================================
pause
exit /b 1
