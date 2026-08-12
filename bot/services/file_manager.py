"""File management and cleanup utilities."""

import os
import logging
import asyncio
from pathlib import Path
from typing import List
import time

logger = logging.getLogger(__name__)


class FileManager:
    """Manager for temporary video files."""
    
    def __init__(self, downloads_path: str, cleanup_interval_minutes: int):
        """Initialize file manager.
        
        Args:
            downloads_path: Path to downloads directory
            cleanup_interval_minutes: Files older than this will be deleted
        """
        self.downloads_path = Path(downloads_path)
        self.cleanup_interval_minutes = cleanup_interval_minutes
        self._ensure_directory()
    
    def _ensure_directory(self):
        """Ensure downloads directory exists."""
        self.downloads_path.mkdir(parents=True, exist_ok=True)
    
    async def delete_file(self, file_path: str) -> bool:
        """Delete a file.
        
        Args:
            file_path: Path to file to delete
            
        Returns:
            True if deleted successfully
        """
        try:
            if os.path.exists(file_path):
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, os.remove, file_path)
                logger.info(f"Deleted file: {file_path}")
                return True
            else:
                logger.warning(f"File not found for deletion: {file_path}")
                return False
        except Exception as e:
            logger.error(f"Failed to delete file {file_path}: {e}")
            return False

    async def delete_files(self, file_paths: List[str]) -> int:
        """Delete multiple files and return deleted count."""
        deleted_count = 0
        for file_path in file_paths:
            if await self.delete_file(file_path):
                deleted_count += 1
        return deleted_count
    
    async def cleanup_old_files(self) -> int:
        """Clean up old files from downloads directory.
        
        Returns:
            Number of files deleted
        """
        try:
            current_time = time.time()
            max_age_seconds = self.cleanup_interval_minutes * 60
            deleted_count = 0
            
            loop = asyncio.get_running_loop()
            
            # Get all files in downloads directory
            files = await loop.run_in_executor(
                None,
                lambda: list(self.downloads_path.glob('*'))
            )
            
            for file_path in files:
                if file_path.is_file():
                    try:
                        if file_path.name.startswith('.'):
                            continue

                        # Get file modification time
                        file_mtime = file_path.stat().st_mtime
                        age_seconds = current_time - file_mtime
                        
                        # Delete if older than threshold
                        if age_seconds > max_age_seconds:
                            await loop.run_in_executor(None, os.remove, str(file_path))
                            deleted_count += 1
                            logger.info(f"Cleaned up old file: {file_path.name}")
                    except Exception as e:
                        logger.error(f"Failed to process file {file_path}: {e}")
            
            if deleted_count > 0:
                logger.info(f"Cleanup completed: deleted {deleted_count} files")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"Cleanup task failed: {e}")
            return 0

    async def cleanup_all_files(self) -> int:
        """Delete all temporary downloaded files immediately."""
        try:
            loop = asyncio.get_running_loop()
            deleted_count = 0
            files = await loop.run_in_executor(
                None,
                lambda: list(self.downloads_path.glob('*'))
            )

            for file_path in files:
                if file_path.is_file() and not file_path.name.startswith('.'):
                    try:
                        await loop.run_in_executor(None, os.remove, str(file_path))
                        deleted_count += 1
                        logger.info(f"Deleted startup temp file: {file_path.name}")
                    except Exception as e:
                        logger.error(f"Failed to delete startup file {file_path}: {e}")

            return deleted_count
        except Exception as e:
            logger.error(f"Startup cleanup failed: {e}")
            return 0
    
    async def get_directory_size(self) -> int:
        """Get total size of downloads directory.
        
        Returns:
            Total size in bytes
        """
        try:
            loop = asyncio.get_running_loop()
            
            def _calculate_size():
                total_size = 0
                for file_path in self.downloads_path.glob('*'):
                    if file_path.is_file():
                        total_size += file_path.stat().st_size
                return total_size
            
            size = await loop.run_in_executor(None, _calculate_size)
            return size
            
        except Exception as e:
            logger.error(f"Failed to calculate directory size: {e}")
            return 0
    
    async def get_file_count(self) -> int:
        """Get number of files in downloads directory.
        
        Returns:
            Number of files
        """
        try:
            loop = asyncio.get_running_loop()
            
            def _count_files():
                return len([f for f in self.downloads_path.glob('*') if f.is_file()])
            
            count = await loop.run_in_executor(None, _count_files)
            return count
            
        except Exception as e:
            logger.error(f"Failed to count files: {e}")
            return 0
    
    async def cleanup_task(self, interval_minutes: int = 15):
        """Background task for periodic cleanup.
        
        Args:
            interval_minutes: Run cleanup every N minutes
        """
        logger.info(f"Starting cleanup task (runs every {interval_minutes} minutes)")
        
        while True:
            try:
                await asyncio.sleep(interval_minutes * 60)
                deleted = await self.cleanup_old_files()
                
                if deleted > 0:
                    size = await self.get_directory_size()
                    count = await self.get_file_count()
                    logger.info(
                        f"Cleanup stats: {deleted} deleted, "
                        f"{count} files remaining, "
                        f"total size: {size / (1024*1024):.1f} MB"
                    )
            except asyncio.CancelledError:
                logger.info("Cleanup task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
                # Continue running even if there's an error
                await asyncio.sleep(60)  # Wait 1 minute before retrying
