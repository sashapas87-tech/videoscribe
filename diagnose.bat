@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1

echo ============================================== > diagnose.txt
echo VideoScribe — диагностика запуска >> diagnose.txt
echo Папка: %CD% >> diagnose.txt
echo ============================================== >> diagnose.txt

if exist ".venv\Scripts\python.exe" (set "PYEXE=.venv\Scripts\python.exe") else (set "PYEXE=python")
echo Python: %PYEXE% >> diagnose.txt
"%PYEXE%" --version >> diagnose.txt 2>&1

echo. >> diagnose.txt
echo --- Проверка файлов --- >> diagnose.txt
if exist "run.bat" (echo [OK] run.bat найден >> diagnose.txt) else (echo [ОШИБКА] run.bat НЕ найден — diagnose.bat лежит не в папке программы! >> diagnose.txt)
if exist "main.py" (echo [OK] main.py найден >> diagnose.txt) else (echo [ОШИБКА] main.py НЕ найден >> diagnose.txt)
if exist "app\i18n.py" (echo [OK] app\i18n.py найден >> diagnose.txt) else (echo [ОШИБКА] app\i18n.py НЕ найден — архив с переводами распакован не в ту папку >> diagnose.txt)
findstr /c:"_report_startup_error" main.py >nul 2>&1
if %errorlevel%==0 (echo [OK] main.py — новая версия с окном ошибок >> diagnose.txt) else (echo [ОШИБКА] main.py — СТАРАЯ версия: вы заменили файл не в этой папке >> diagnose.txt)

echo. >> diagnose.txt
echo --- Запуск программы (если откроется окно — просто закройте его) --- >> diagnose.txt
"%PYEXE%" main.py >> diagnose.txt 2>&1
echo Код выхода: %errorlevel% >> diagnose.txt

cls
type diagnose.txt
echo.
echo ==============================================
echo Отчёт сохранён в файл: %CD%\diagnose.txt
echo Пришлите этот файл или скриншот данного окна.
echo ==============================================
pause
