@echo off
cd /d "%~dp0"
python -c "import smartcard" 2>nul
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r requirements.txt
)
python main.py
