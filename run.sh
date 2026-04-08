#!/bin/bash

# TikTok Downloader Bot - Start Script

echo "Starting TikTok Downloader Bot..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Creating..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Check if dependencies are installed
if ! python -c "import aiogram" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install -r requirements.txt
fi

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "Error: .env file not found!"
    echo "Please create .env file from .env.example and set BOT_TOKEN"
    exit 1
fi

# Run bot
echo "Bot is running... Press Ctrl+C to stop"
python -m bot.main
