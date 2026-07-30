@echo off
rem Optional: install speaker diarization packages (torch + pyannote, ~2 GB)
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo Run run.bat first to create the environment.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"
echo Installing diarization packages (this downloads ~2 GB, please wait)...
pip install -r requirements-diarization.txt
if errorlevel 1 (
    echo Install failed. Check your internet connection and try again.
) else (
    echo Done. Also needed:
    echo  1. Free Hugging Face token: https://huggingface.co/settings/tokens
    echo  2. Accept model terms:
    echo     https://huggingface.co/pyannote/speaker-diarization-3.1
    echo     https://huggingface.co/pyannote/segmentation-3.0
    echo  3. Paste the token in VideoScribe Settings.
)
pause
