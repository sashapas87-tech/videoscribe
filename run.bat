@echo off
rem VideoScribe - run from source (creates venv on first run)
cd /d "%~dp0"

where py >nul 2>&1
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")

%PY% --version >nul 2>&1
if errorlevel 1 (
    echo Python not found. Install Python 3.10+ from https://www.python.org/downloads/
    echo IMPORTANT: check "Add python.exe to PATH" during installation.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PY% -m venv .venv || (echo Failed to create venv & pause & exit /b 1)
    call ".venv\Scripts\activate.bat"
    python -m pip install --upgrade pip
    echo Installing dependencies (first run only, several minutes)...
    pip install -r requirements.txt || (echo Dependency install failed & pause & exit /b 1)
) else (
    call ".venv\Scripts\activate.bat"
)

python scripts\prepare_assets.py --quiet

start "" /b pythonw main.py 2>nul || python main.py
exit /b 0
