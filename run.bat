@echo off
REM TikTok Downloader Bot - Start Script for Windows

echo Starting TikTok Downloader Bot...

REM Check if virtual environment exists
if not exist ".venv" (
    echo Virtual environment not found. Creating...
    python -m venv .venv
)

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Check if dependencies are installed
python -c "import aiogram" 2>nul
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r requirements.txt
)

REM Check if .env exists
if not exist ".env" (
    echo Error: .env file not found!
    echo Please create .env file from .env.example and set BOT_TOKEN
    pause
    exit /b 1
)

REM Run bot
echo Bot is running... Press Ctrl+C to stop
python -m bot.main
pause
