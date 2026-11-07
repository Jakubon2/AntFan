@echo off
rem Vytvori samostatny dist\AntFan.exe (neni potreba instalovat Python na cilovem PC)
cd /d "%~dp0"
if not exist .venv (
    py -3 -m venv .venv || python -m venv .venv
)
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt pyinstaller
.venv\Scripts\pyinstaller --noconfirm --onefile --windowed --name AntFan ^
    --collect-all libusb_package --collect-submodules openant ^
    AntFan.pyw
echo.
echo Hotovo: dist\AntFan.exe
pause
