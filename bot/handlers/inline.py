"""Inline query handlers for bot."""

import logging
from typing import Dict, Any
import time

from aiogram import Router, F
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineQueryResultVideo,
    InlineQueryResultCachedVideo,
    InlineQueryResultCachedPhoto,
    FSInputFile,
    InputMediaPhoto
)
from aiogram.types import Message
from aiogram import Bot

from ..services.url_parser import URLParser
from ..services.downloader import TikTokDownloader
from ..services.file_manager import FileManager
from ..database.db import Database
from ..config import Config
from ..utils.formatters import format_file_size

logger = logging.getLogger(__name__)

# Router for inline handlers
inline_router = Router()

# Rate limiting storage
user_requests: Dict[int, list] = {}


def is_photo_post_error(error_msg: str) -> bool:
    """Return True when inline request points to a TikTok photo post."""
    normalized = (error_msg or "").lower()
    return "фото-пост" in normalized or "photo-post" in normalized


async def send_media_to_private_chat(
    bot: Bot,
    user_id: int,
    download_result: Dict[str, Any],
    file_manager: FileManager,
):
    """Send downloaded media to user's private chat and clean up files."""
    if download_result.get("media_type") == "photo":
        file_paths = download_result.get("file_paths", [])

        try:
            if len(file_paths) == 1:
                await bot.send_photo(
                    chat_id=user_id,
                    photo=FSInputFile(file_paths[0])
                )
            else:
                for start in range(0, len(file_paths), 10):
                    chunk = file_paths[start:start + 10]
                    await bot.send_media_group(
                        chat_id=user_id,
                        media=[
                            InputMediaPhoto(media=FSInputFile(file_path))
                            for file_path in chunk
                        ]
                    )
        finally:
            await file_manager.delete_files(file_paths)
        return

    file_path = download_result["file_path"]
    try:
        await bot.send_video(
            chat_id=user_id,
            video=FSInputFile(file_path),
            supports_streaming=True
        )
    finally:
        await file_manager.delete_file(file_path)


def get_cache_chat_id(user_id: int) -> int:
    """Get cache destination for temporary uploads."""
    return Config.CACHE_CHANNEL_ID or user_id


async def build_inline_photo_results(
    bot: Bot,
    user_id: int,
    file_paths: list[str],
    title: str,
):
    """Upload photos to cache chat and create inline cached-photo results."""
    cache_chat_id = get_cache_chat_id(user_id)
    results = []

    for index, file_path in enumerate(file_paths[:10], start=1):
        sent_message = await bot.send_photo(
            chat_id=cache_chat_id,
            photo=FSInputFile(file_path)
        )
        photo_file_id = sent_message.photo[-1].file_id

        if cache_chat_id == user_id:
            try:
                await sent_message.delete()
            except Exception:
                pass

        results.append(
            InlineQueryResultCachedPhoto(
                id=f"{user_id}_photo_{index}_{int(time.time())}",
                photo_file_id=photo_file_id,
                title=f"📷 {index}/{len(file_paths)}",
                description=title[:80] if title else f"Фото {index}",
            )
        )

    return results


def check_rate_limit(user_id: int) -> bool:
    """Check if user exceeded rate limit.
    
    Args:
        user_id: Telegram user ID
        
    Returns:
        True if within limits
    """
    now = time.time()
    
    if user_id not in user_requests:
        user_requests[user_id] = []
    
    # Remove old requests (older than rate limit period)
    user_requests[user_id] = [
        t for t in user_requests[user_id]
        if now - t < Config.RATE_LIMIT_PERIOD
    ]
    
    # Check limit
    if len(user_requests[user_id]) >= Config.RATE_LIMIT_REQUESTS:
        return False
    
    user_requests[user_id].append(now)
    return True


@inline_router.inline_query()
async def handle_inline_query(
    inline_query: InlineQuery,
    downloader: TikTokDownloader,
    file_manager: FileManager,
    db: Database,
    bot: Bot
):
    """Handle inline query from user.
    
    User writes: @botusername https://tiktok.com/...
    """
    query_text = inline_query.query.strip()
    user_id = inline_query.from_user.id
    
    # Check rate limit
    if not check_rate_limit(user_id):
        await inline_query.answer(
            results=[],
            cache_time=1,
            is_personal=True,
            switch_pm_text="⚠️ Слишком много запросов",
            switch_pm_parameter="rate_limit"
        )
        return
    
    # If query is empty, show instruction
    if not query_text:
        await inline_query.answer(
            results=[],
            cache_time=1,
            is_personal=True,
            switch_pm_text="📝 Вставьте ссылку на TikTok видео",
            switch_pm_parameter="start"
        )
        return
    
    # Extract and validate TikTok URL
    video_url = URLParser.extract_and_validate(query_text)
    
    if not video_url:
        await inline_query.answer(
            results=[],
            cache_time=1,
            is_personal=True,
            switch_pm_text="❌ Некорректная ссылка TikTok",
            switch_pm_parameter="invalid_url"
        )
        return
    
    # Log user
    await db.add_user(
        user_id=user_id,
        username=inline_query.from_user.username,
        first_name=inline_query.from_user.first_name,
        last_name=inline_query.from_user.last_name
    )
    
    try:
        # Download video first
        logger.info(f"User {user_id} requested download: {video_url}")
        
        # Download media
        download_result = await downloader.download_media(video_url)
        
        if not download_result['success']:
            # Send error message
            error_msg = download_result.get('error', 'Не удалось скачать видео')
            
            # Show error in inline results
            await inline_query.answer(
                results=[],
                cache_time=1,
                is_personal=True,
                switch_pm_text=f"❌ Ошибка: {error_msg[:30]}...",
                switch_pm_parameter="error"
            )
            
            # Log failed download
            await db.log_download(
                user_id=user_id,
                video_url=video_url,
                success=False,
                error_message=error_msg
            )
            
            logger.warning(f"Download failed for user {user_id}: {error_msg}")
            return
        
        file_size = download_result['file_size']
        duration = download_result.get('duration')
        title = download_result.get('title', 'TikTok Video')

        if download_result.get('media_type') == 'photo':
            file_paths = download_result.get('file_paths', [])
            logger.info(f"Photo post downloaded for inline: {len(file_paths)} files")

            try:
                results = await build_inline_photo_results(
                    bot=bot,
                    user_id=user_id,
                    file_paths=file_paths,
                    title=title,
                )

                await inline_query.answer(
                    results=results,
                    cache_time=300,
                    is_personal=True
                )

                await file_manager.delete_files(file_paths)

                await db.log_download(
                    user_id=user_id,
                    video_url=video_url,
                    success=True,
                    file_size=file_size,
                    duration=duration
                )

                logger.info(f"Inline photo results sent for user {user_id}")
                return
            except Exception as e:
                logger.error(f"Failed to upload photos for inline result: {e}")
                await file_manager.delete_files(file_paths)
                raise

        file_path = download_result['file_path']
        logger.info(f"Download successful: {file_path} ({format_file_size(file_size)})")
        
        # Upload video to Telegram to get file_id
        try:
            from aiogram.types import FSInputFile, BufferedInputFile
            
            # Try to use cache channel if configured
            cache_chat_id = None
            if Config.CACHE_CHANNEL_ID:
                cache_chat_id = Config.CACHE_CHANNEL_ID
                logger.info(f"Using cache channel: {cache_chat_id}")
            else:
                # Fallback to user's chat (requires user to have started the bot)
                cache_chat_id = user_id
                logger.info(f"Using user's chat for caching: {cache_chat_id}")
            
            # Send video to cache location to get file_id
            video_file = FSInputFile(file_path)
            sent_message = await bot.send_video(
                chat_id=cache_chat_id,
                video=video_file,
                
                supports_streaming=True
            )
            
            # Get file_id from the sent video
            file_id = sent_message.video.file_id
            
            # Delete the cache message if it was sent to user
            if cache_chat_id == user_id:
                try:
                    await sent_message.delete()
                except Exception:
                    pass
            
            logger.info(f"Got file_id: {file_id}")
            
            # Now create inline result with cached video
            result_id = f"{user_id}_{int(time.time())}"
            
            result = InlineQueryResultCachedVideo(
                id=result_id,
                video_file_id=file_id,
                title=f"🎬 {title[:50]}" if title else "🎬 TikTok видео",
                description=f"📦 {format_file_size(file_size)}" + (f" • ⏱ {duration}с" if duration else ""),
                
            )
            
            await inline_query.answer(
                results=[result],
                cache_time=300,  # Cache for 5 minutes
                is_personal=True
            )
            
            # Delete file after uploading
            await file_manager.delete_file(file_path)
            
            # Log successful download
            await db.log_download(
                user_id=user_id,
                video_url=video_url,
                success=True,
                file_size=file_size,
                duration=duration
            )
            
            logger.info(f"Inline result sent with cached video for user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to upload video for inline result: {e}")
            
            # Fallback: send article with instruction to use bot in private
            result_id = f"{user_id}_{int(time.time())}"
            
            result = InlineQueryResultArticle(
                id=result_id,
                title="🎬 Скачать TikTok видео",
                description="Нажмите, чтобы получить видео в личку",
                input_message_content=InputTextMessageContent(
                    message_text=f"⏬ Видео скачано!\n\n💬 Видео отправлено вам в личку с ботом @luxsittbot\n\n🔗 {video_url}"
                )
            )
            
            await inline_query.answer(
                results=[result],
                cache_time=1,
                is_personal=True
            )
            
            # Send video to user's private chat as fallback
            try:
                video_file = FSInputFile(file_path)
                await bot.send_video(
                    chat_id=user_id,
                    video=video_file,
                    
                    supports_streaming=True
                )
                logger.info(f"Video sent to user {user_id} in private chat (fallback)")
            except Exception as e2:
                logger.error(f"Failed to send video to private chat: {e2}")
            
            # Delete file
            await file_manager.delete_file(file_path)
            
            # Log download
            await db.log_download(
                user_id=user_id,
                video_url=video_url,
                success=True,
                file_size=file_size,
                duration=duration
            )
        
    except Exception as e:
        logger.error(f"Error processing inline query: {e}")
        await inline_query.answer(
            results=[],
            cache_time=1,
            is_personal=True,
            switch_pm_text="❌ Произошла ошибка",
            switch_pm_parameter="error"
        )


# Note: Sending video in inline mode requires a different approach
# We need to send video as a response to the chosen inline result
# This requires using ChosenInlineResult handler

from aiogram.types import ChosenInlineResult


@inline_router.chosen_inline_result()
async def handle_chosen_inline_result(
    chosen_result: ChosenInlineResult,
    downloader: TikTokDownloader,
    file_manager: FileManager,
    db: Database,
    bot: Bot
):
    """Handle when user selects an inline result.
    
    Note: This handler is called when user clicks on the inline result,
    but we cannot send files here directly. The message is already sent.
    We need a different approach for inline mode.
    """
    user_id = chosen_result.from_user.id
    query = chosen_result.query
    
    logger.info(f"User {user_id} chose inline result: {query}")
    
    # Extract URL from query
    video_url = URLParser.extract_and_validate(query)
    
    if not video_url:
        return
    
    try:
        # Download media
        download_result = await downloader.download_media(video_url)
        
        if not download_result['success']:
            error_msg = download_result.get('error', 'Не удалось скачать видео')
            
            # Try to send error to user (in private chat)
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=f"❌ Ошибка при скачивании:\n{error_msg}\n\n🔗 {video_url}"
                )
            except Exception:
                pass
            
            await db.log_download(
                user_id=user_id,
                video_url=video_url,
                success=False,
                error_message=error_msg
            )
            return
        
        # Download successful, send media to user in private chat
        file_size = download_result['file_size']
        duration = download_result.get('duration')
        
        try:
            await send_media_to_private_chat(
                bot=bot,
                user_id=user_id,
                download_result=download_result,
                file_manager=file_manager,
            )
            
            logger.info(f"Media sent to user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to send video to user {user_id}: {e}")
            
            # Try to send error message
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=f"❌ Не удалось отправить видео. Возможно, оно слишком большое.\n\n🔗 {video_url}"
                )
            except Exception:
                pass
        
        
        # Log successful download
        await db.log_download(
            user_id=user_id,
            video_url=video_url,
            success=True,
            file_size=file_size,
            duration=duration
        )
        
    except Exception as e:
        logger.error(f"Error in chosen inline result handler: {e}")
