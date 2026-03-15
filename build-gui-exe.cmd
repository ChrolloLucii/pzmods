@echo off
setlocal
set "SCRIPT_DIR=%~dp0"

if not exist "%SCRIPT_DIR%.venv\Scripts\python.exe" (
  echo [.venv not found] Create venv first.
  echo Run:
  echo   python -m venv .venv
  echo   .\.venv\Scripts\python.exe -m pip install -e .
  exit /b 1
)

"%SCRIPT_DIR%.venv\Scripts\python.exe" -m pip install pyinstaller
"%SCRIPT_DIR%.venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed --name pzmods-gui "%SCRIPT_DIR%pzmods_gui_main.py"

echo Done. EXE is in dist\pzmods-gui.exe
