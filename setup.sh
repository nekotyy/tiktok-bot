#!/bin/bash

# Setup script for TikTok Downloader Bot

echo "==================================="
echo "TikTok Downloader Bot - Setup"
echo "==================================="
echo ""

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python version: $PYTHON_VERSION"

# Check if Python 3.10+
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
    echo "❌ Error: Python 3.10+ required (found $PYTHON_VERSION)"
    exit 1
fi

# Create virtual environment
echo ""
echo "Creating virtual environment..."
python3 -m venv venv
echo "✓ Virtual environment created"

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
echo "✓ Dependencies installed"

# Create .env if not exists
if [ ! -f ".env" ]; then
    echo ""
    echo "Creating .env file..."
    cp .env.example .env
    echo "✓ .env file created"
    echo ""
    echo "⚠️  IMPORTANT: Edit .env file and set your BOT_TOKEN"
    echo ""
    read -p "Do you have a bot token? (y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        read -p "Enter your bot token: " BOT_TOKEN
        sed -i "s/your_bot_token_here/$BOT_TOKEN/" .env
        echo "✓ Bot token saved"
    else
        echo ""
        echo "To get a bot token:"
        echo "1. Open Telegram and search for @BotFather"
        echo "2. Send /newbot command"
        echo "3. Follow instructions"
        echo "4. Copy the token and paste it in .env file"
    fi
else
    echo ""
    echo "✓ .env file already exists"
fi

# Create necessary directories
mkdir -p downloads data
echo "✓ Directories created"

echo ""
echo "==================================="
echo "Setup completed successfully! ✓"
echo "==================================="
echo ""
echo "Next steps:"
echo "1. Make sure BOT_TOKEN is set in .env file"
echo "2. Enable inline mode in @BotFather: /setinline"
echo "3. Run the bot: ./run.sh or python -m bot.main"
echo ""
