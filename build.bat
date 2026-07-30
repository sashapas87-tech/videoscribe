@echo off
rem Build standalone VideoScribe.exe (PyInstaller). Run on Windows.
cd /d "%~dp0"

where py >nul 2>&1
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PY% -m venv .venv || (echo Failed to create venv & pause & exit /b 1)
)
call ".venv\Scripts\activate.bat"

python -m pip install --upgrade pip
pip install -r requirements.txt || (echo Dependency install failed & pause & exit /b 1)
pip install pyinstaller pillow || (echo PyInstaller install failed & pause & exit /b 1)
python scripts\prepare_assets.py || (echo Asset preparation failed & pause & exit /b 1)

echo Building (several minutes)...
pyinstaller videoscribe.spec --noconfirm --clean
if errorlevel 1 (
    echo BUILD FAILED
    pause
    exit /b 1
)

echo.
echo Done! Application folder: dist\VideoScribe
echo Run: dist\VideoScribe\VideoScribe.exe
echo Note: the exe build does not include speaker diarization (torch is too big).
echo       For diarization use run.bat + install-diarization.bat
pause
