@echo off
chcp 65001 >nul
rem VideoScribe — запуск из исходников. Первая установка библиотек: install.bat
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" goto :run
if exist ".venv\Scripts\python.exe" goto :runconsole

if not exist "install.bat" goto :noinstall
echo Библиотеки ещё не установлены — запускаю установщик...
call install.bat
if exist ".venv\Scripts\pythonw.exe" goto :run
exit /b 1

:run
".venv\Scripts\python.exe" scripts\prepare_assets.py --quiet >nul 2>&1
start "" ".venv\Scripts\pythonw.exe" main.py
exit /b 0

:runconsole
".venv\Scripts\python.exe" scripts\prepare_assets.py --quiet >nul 2>&1
".venv\Scripts\python.exe" main.py
exit /b 0

:noinstall
echo Библиотеки не установлены, а установщик install.bat не найден рядом.
echo Скачайте install.bat, положите в эту папку и запустите его.
pause
exit /b 1
