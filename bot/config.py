"""Configuration module for loading environment variables."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)


class Config:
    """Bot configuration from environment variables."""
    
    # Bot token
    BOT_TOKEN: str = os.getenv('BOT_TOKEN', '')
    
    # Admin user ID
    ADMIN_ID: int = int(os.getenv('ADMIN_ID', '0'))
    
    # Cache channel ID for inline mode (optional)
    CACHE_CHANNEL_ID: int = int(os.getenv('CACHE_CHANNEL_ID', '0')) if os.getenv('CACHE_CHANNEL_ID') else 0
    
    # File settings
    MAX_FILE_SIZE_MB: int = int(os.getenv('MAX_FILE_SIZE_MB', '50'))
    MAX_FILE_SIZE_BYTES: int = MAX_FILE_SIZE_MB * 1024 * 1024
    
    # Cleanup settings
    FILE_CLEANUP_INTERVAL: int = int(os.getenv('FILE_CLEANUP_INTERVAL', '10'))
    
    # Paths
    BASE_DIR: Path = Path(__file__).parent.parent
    DATABASE_PATH: str = str(BASE_DIR / os.getenv('DATABASE_PATH', 'data/bot.db'))
    DOWNLOADS_PATH: str = str(BASE_DIR / os.getenv('DOWNLOADS_PATH', 'downloads'))
    
    # Rate limiting
    RATE_LIMIT_REQUESTS: int = 10  # requests per minute
    RATE_LIMIT_PERIOD: int = 60   # seconds
    
    @classmethod
    def validate(cls) -> bool:
        """Validate that all required config values are set."""
        if not cls.BOT_TOKEN or cls.BOT_TOKEN == 'your_bot_token_here':
            raise ValueError("BOT_TOKEN is not set in .env file")
        return True


# Validate config on import
try:
    Config.validate()
except ValueError as e:
    print(f"Configuration error: {e}")
    print("Please create .env file from .env.example and set BOT_TOKEN")
