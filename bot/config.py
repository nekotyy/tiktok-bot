"""Configuration module for loading environment variables."""

import os
from pathlib import Path
from urllib.parse import quote
from typing import Set
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)


def _get_int_env(name: str, default: int = 0) -> int:
    """Read an integer env var without crashing on placeholders."""
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == '':
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


class Config:
    """Bot configuration from environment variables."""
    
    # Bot token
    BOT_TOKEN: str = os.getenv('BOT_TOKEN', '')
    
    # Admin user ID
    ADMIN_ID: int = _get_int_env('ADMIN_ID', 0)
    
    # Cache channel ID for inline mode (optional)
    CACHE_CHANNEL_ID: int = _get_int_env('CACHE_CHANNEL_ID', 0)

    # Chat/channel whitelist. Empty means "allow everywhere".
    ALLOWED_CHAT_IDS: Set[int] = set()

    # If True, bot works in any chat where it receives messages (any group/channel
    # where the bot is a member). If False, only ALLOWED_CHAT_IDS are permitted.
    AUTO_ALLOW_MEMBER_CHATS: bool = (
        os.getenv('AUTO_ALLOW_MEMBER_CHATS', 'true').lower() in ('1', 'true', 'yes')
    )
    
    # File settings
    MAX_FILE_SIZE_MB: int = _get_int_env('MAX_FILE_SIZE_MB', 50)
    MAX_FILE_SIZE_BYTES: int = MAX_FILE_SIZE_MB * 1024 * 1024

    # Cleanup settings
    FILE_CLEANUP_INTERVAL: int = _get_int_env('FILE_CLEANUP_INTERVAL', 10)
    
    # Paths
    BASE_DIR: Path = Path(__file__).parent.parent
    DATABASE_PATH: str = str(BASE_DIR / os.getenv('DATABASE_PATH', 'data/bot.db'))
    DOWNLOADS_PATH: str = str(BASE_DIR / os.getenv('DOWNLOADS_PATH', 'downloads'))

    # Optional network settings for yt-dlp, gallery-dl, and Instagram embed.
    YTDLP_PROXY: str = os.getenv('YTDLP_PROXY', '').strip()
    YTDLP_IMPERSONATE: str = os.getenv('YTDLP_IMPERSONATE', '').strip()
    
    # Rate limiting
    RATE_LIMIT_REQUESTS: int = 10  # requests per minute
    RATE_LIMIT_PERIOD: int = 60   # seconds

    @staticmethod
    def _parse_id_list(raw_value: str) -> Set[int]:
        """Parse comma/newline/space separated Telegram IDs."""
        if not raw_value:
            return set()

        allowed_ids: Set[int] = set()
        normalized = raw_value.replace('\n', ',').replace(';', ',').replace(' ', ',')
        for item in normalized.split(','):
            value = item.strip()
            if not value:
                continue
            allowed_ids.add(int(value))
        return allowed_ids

    @classmethod
    def is_chat_allowed(cls, chat_id: int) -> bool:
        """Return True when the chat is allowed to use the bot."""
        if cls.AUTO_ALLOW_MEMBER_CHATS:
            return True
        if not cls.ALLOWED_CHAT_IDS:
            return True
        return chat_id in cls.ALLOWED_CHAT_IDS
    
    @classmethod
    def validate(cls) -> bool:
        """Validate that all required config values are set."""
        if not cls.BOT_TOKEN or cls.BOT_TOKEN == 'your_bot_token_here':
            raise ValueError("BOT_TOKEN is not set in .env file")
        return True

    @classmethod
    def get_database_url(cls) -> str:
        """Return SQLAlchemy-compatible database URL for Alembic."""
        db_path = Path(cls.DATABASE_PATH).resolve()
        normalized_path = db_path.as_posix()
        return f"sqlite:///{quote(normalized_path, safe='/:')}"


# Validate config on import
try:
    Config.ALLOWED_CHAT_IDS = Config._parse_id_list(os.getenv('ALLOWED_CHAT_IDS', ''))
    Config.validate()
except ValueError as e:
    print(f"Configuration error: {e}")
    print("Please create .env file from .env.example and set BOT_TOKEN")
