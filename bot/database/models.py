"""Database models and schema definitions."""

from datetime import datetime
from typing import Optional


# SQL Schema
SCHEMA = """
-- Users table
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Downloads table
CREATE TABLE IF NOT EXISTS downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    video_url TEXT NOT NULL,
    file_size INTEGER,
    duration INTEGER,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (user_id)
);

-- Statistics table (aggregated data)
CREATE TABLE IF NOT EXISTS statistics (
    user_id INTEGER PRIMARY KEY,
    total_downloads INTEGER DEFAULT 0,
    total_size INTEGER DEFAULT 0,
    last_download_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (user_id)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_downloads_user_id ON downloads(user_id);
CREATE INDEX IF NOT EXISTS idx_downloads_created_at ON downloads(created_at);
CREATE INDEX IF NOT EXISTS idx_statistics_user_id ON statistics(user_id);
"""


class User:
    """User model."""
    
    def __init__(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        created_at: Optional[datetime] = None
    ):
        self.user_id = user_id
        self.username = username
        self.first_name = first_name
        self.last_name = last_name
        self.created_at = created_at or datetime.now()
    
    def __repr__(self) -> str:
        return f"User(user_id={self.user_id}, username={self.username})"


class Download:
    """Download record model."""
    
    def __init__(
        self,
        user_id: int,
        video_url: str,
        success: bool,
        file_size: Optional[int] = None,
        duration: Optional[int] = None,
        error_message: Optional[str] = None,
        created_at: Optional[datetime] = None
    ):
        self.user_id = user_id
        self.video_url = video_url
        self.success = success
        self.file_size = file_size
        self.duration = duration
        self.error_message = error_message
        self.created_at = created_at or datetime.now()
    
    def __repr__(self) -> str:
        status = "success" if self.success else "failed"
        return f"Download(user_id={self.user_id}, status={status})"


class UserStatistics:
    """User statistics model."""
    
    def __init__(
        self,
        user_id: int,
        total_downloads: int = 0,
        total_size: int = 0,
        last_download_at: Optional[datetime] = None
    ):
        self.user_id = user_id
        self.total_downloads = total_downloads
        self.total_size = total_size
        self.last_download_at = last_download_at
    
    def __repr__(self) -> str:
        return f"UserStatistics(user_id={self.user_id}, downloads={self.total_downloads})"
