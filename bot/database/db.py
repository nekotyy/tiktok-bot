"""Database operations module."""

import aiosqlite
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

from .models import SCHEMA, User, Download, UserStatistics

logger = logging.getLogger(__name__)


class Database:
    """Database manager for bot operations."""
    
    def __init__(self, db_path: str):
        """Initialize database manager.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._ensure_directory()
    
    def _ensure_directory(self):
        """Ensure database directory exists."""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
    
    async def init_db(self):
        """Initialize database schema."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.executescript(SCHEMA)
                await db.commit()
                logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    async def add_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None
    ) -> bool:
        """Add or update user in database.
        
        Args:
            user_id: Telegram user ID
            username: Telegram username
            first_name: User's first name
            last_name: User's last name
            
        Returns:
            True if successful
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    INSERT INTO users (user_id, username, first_name, last_name)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        username = excluded.username,
                        first_name = excluded.first_name,
                        last_name = excluded.last_name
                    """,
                    (user_id, username, first_name, last_name)
                )
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to add user {user_id}: {e}")
            return False
    
    async def log_download(
        self,
        user_id: int,
        video_url: str,
        success: bool,
        file_size: Optional[int] = None,
        duration: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """Log download attempt.
        
        Args:
            user_id: Telegram user ID
            video_url: TikTok video URL
            success: Whether download was successful
            file_size: File size in bytes
            duration: Video duration in seconds
            error_message: Error message if failed
            
        Returns:
            True if successful
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Log download
                await db.execute(
                    """
                    INSERT INTO downloads (user_id, video_url, success, file_size, duration, error_message)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, video_url, success, file_size, duration, error_message)
                )
                
                # Update statistics if successful
                if success:
                    await db.execute(
                        """
                        INSERT INTO statistics (user_id, total_downloads, total_size, last_download_at)
                        VALUES (?, 1, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(user_id) DO UPDATE SET
                            total_downloads = total_downloads + 1,
                            total_size = total_size + ?,
                            last_download_at = CURRENT_TIMESTAMP
                        """,
                        (user_id, file_size or 0, file_size or 0)
                    )
                
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to log download for user {user_id}: {e}")
            return False
    
    async def get_user_stats(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user statistics.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Dictionary with user statistics or None
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                # Get statistics
                async with db.execute(
                    """
                    SELECT 
                        s.total_downloads,
                        s.total_size,
                        s.last_download_at,
                        u.created_at
                    FROM statistics s
                    LEFT JOIN users u ON s.user_id = u.user_id
                    WHERE s.user_id = ?
                    """,
                    (user_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    
                    if row:
                        return {
                            'total_downloads': row['total_downloads'],
                            'total_size': row['total_size'],
                            'last_download_at': row['last_download_at'],
                            'member_since': row['created_at']
                        }
                    else:
                        # New user, return empty stats
                        return {
                            'total_downloads': 0,
                            'total_size': 0,
                            'last_download_at': None,
                            'member_since': None
                        }
        except Exception as e:
            logger.error(f"Failed to get stats for user {user_id}: {e}")
            return None
    
    async def get_global_stats(self) -> Optional[Dict[str, Any]]:
        """Get global bot statistics.
        
        Returns:
            Dictionary with global statistics or None
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                async with db.execute(
                    """
                    SELECT 
                        COUNT(DISTINCT user_id) as total_users,
                        SUM(total_downloads) as total_downloads,
                        SUM(total_size) as total_size
                    FROM statistics
                    """
                ) as cursor:
                    row = await cursor.fetchone()
                    
                    if row:
                        return {
                            'total_users': row['total_users'] or 0,
                            'total_downloads': row['total_downloads'] or 0,
                            'total_size': row['total_size'] or 0
                        }
                    else:
                        return {
                            'total_users': 0,
                            'total_downloads': 0,
                            'total_size': 0
                        }
        except Exception as e:
            logger.error(f"Failed to get global stats: {e}")
            return None
    
    async def get_recent_downloads(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent downloads for user.
        
        Args:
            user_id: Telegram user ID
            limit: Maximum number of records
            
        Returns:
            List of download records
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                
                async with db.execute(
                    """
                    SELECT video_url, success, file_size, created_at
                    FROM downloads
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (user_id, limit)
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get recent downloads for user {user_id}: {e}")
            return []
