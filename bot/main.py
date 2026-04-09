"""Main entry point for TikTok Downloader Bot."""

import asyncio
import logging
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from bot.config import Config
from bot.database.db import Database
from bot.services.downloader import TikTokDownloader
from bot.services.file_manager import FileManager
from bot.handlers.commands import command_router
from bot.handlers.inline import inline_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)


async def main():
    """Main function to run the bot."""
    logger.info("Starting TikTok Downloader Bot...")
    
    try:
        # Validate configuration
        Config.validate()
        logger.info("Configuration validated successfully")
        
        # Initialize bot and dispatcher
        bot = Bot(
            token=Config.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        dp = Dispatcher()
        
        # Initialize database
        db = Database(Config.DATABASE_PATH)
        await db.init_db()
        logger.info("Database initialized")
        
        # Initialize services
        downloader = TikTokDownloader(
            downloads_path=Config.DOWNLOADS_PATH,
            max_file_size_bytes=Config.MAX_FILE_SIZE_BYTES
        )
        logger.info("Downloader service initialized")
        
        file_manager = FileManager(
            downloads_path=Config.DOWNLOADS_PATH,
            cleanup_interval_minutes=Config.FILE_CLEANUP_INTERVAL
        )
        logger.info("File manager initialized")

        deleted_on_startup = await file_manager.cleanup_all_files()
        if deleted_on_startup:
            logger.info(f"Startup cleanup removed {deleted_on_startup} temp files")
        
        # Register routers
        dp.include_router(command_router)
        dp.include_router(inline_router)
        logger.info("Routers registered")
        
        # Start cleanup task
        cleanup_task = asyncio.create_task(
            file_manager.cleanup_task(interval_minutes=15)
        )
        logger.info("Cleanup task started")
        
        # Set bot info
        bot_info = await bot.get_me()
        logger.info(f"Bot started: @{bot_info.username} (ID: {bot_info.id})")
        logger.info(f"Bot name: {bot_info.first_name}")
        
        # Inject dependencies into handlers
        dp.workflow_data.update({
            'db': db,
            'downloader': downloader,
            'file_manager': file_manager,
            'bot': bot
        })
        
        # Start polling
        try:
            await dp.start_polling(
                bot,
                allowed_updates=dp.resolve_used_update_types(),
                db=db,
                downloader=downloader,
                file_manager=file_manager
            )
        finally:
            # Cleanup
            logger.info("Stopping bot...")
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
            
            await bot.session.close()
            logger.info("Bot stopped")
            
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (Ctrl+C)")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)
