@echo off
REM tag-read launcher — requires Python 3.9+ and pyscard installed
REM Run this from the tag-read directory

cd /d "%~dp0"

python -c "import smartcard" 2>nul
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r requirements.txt
)

python main.py
