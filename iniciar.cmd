@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Ambiente Python nao encontrado. Consulte a instalacao no README.md.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m factcheck
