"""Command handlers for bot."""

import logging
from pathlib import Path

from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, InputMediaPhoto

from ..database.db import Database
from ..utils.formatters import (
    format_start_message,
    format_help_message,
    format_stats_message
)

logger = logging.getLogger(__name__)

# Router for command handlers
command_router = Router()


def get_main_keyboard() -> InlineKeyboardMarkup:
    """Get main menu keyboard.
    
    Returns:
        Inline keyboard with main menu buttons
    """
    buttons = [
        [
            InlineKeyboardButton(text="📖 Помощь", callback_data="help"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="stats")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_back_keyboard() -> InlineKeyboardMarkup:
    """Get back button keyboard.
    
    Returns:
        Inline keyboard with back button
    """
    buttons = [
        [InlineKeyboardButton(text="◀️ Назад", callback_data="start")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@command_router.message(CommandStart())
async def cmd_start(message: Message, db: Database):
    """Handle /start command.
    
    Args:
        message: Telegram message
        db: Database instance
    """
    user_id = message.from_user.id
    
    # Add user to database
    await db.add_user(
        user_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )
    
    # Send welcome message
    await message.answer(
        text=format_start_message(),
        reply_markup=get_main_keyboard()
    )
    
    logger.info(f"User {user_id} started the bot")


@command_router.message(Command("help"))
async def cmd_help(message: Message):
    """Handle /help command.
    
    Args:
        message: Telegram message
    """
    await message.answer(
        text=format_help_message(),
        reply_markup=get_back_keyboard()
    )


@command_router.message(Command("stats"))
async def cmd_stats(message: Message, db: Database):
    """Handle /stats command.
    
    Args:
        message: Telegram message
        db: Database instance
    """
    user_id = message.from_user.id
    
    # Get user statistics
    stats = await db.get_user_stats(user_id)
    
    if stats is None:
        await message.answer(
            text="❌ Не удалось получить статистику. Попробуйте позже.",
            reply_markup=get_back_keyboard()
        )
        return
    
    # Format and send statistics
    await message.answer(
        text=format_stats_message(stats),
        reply_markup=get_back_keyboard()
    )


# Callback query handlers for inline buttons

from aiogram.types import CallbackQuery


@command_router.callback_query(F.data == "start")
async def callback_start(callback: CallbackQuery, db: Database):
    """Handle start button callback.
    
    Args:
        callback: Callback query
        db: Database instance
    """
    user_id = callback.from_user.id
    
    # Add user to database
    await db.add_user(
        user_id=user_id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
        last_name=callback.from_user.last_name
    )
    
    # Edit message
    await callback.message.edit_text(
        text=format_start_message(),
        reply_markup=get_main_keyboard()
    )
    
    await callback.answer()


@command_router.callback_query(F.data == "help")
async def callback_help(callback: CallbackQuery):
    """Handle help button callback.
    
    Args:
        callback: Callback query
    """
    await callback.message.edit_text(
        text=format_help_message(),
        reply_markup=get_back_keyboard()
    )
    
    await callback.answer()


@command_router.callback_query(F.data == "stats")
async def callback_stats(callback: CallbackQuery, db: Database):
    """Handle stats button callback.
    
    Args:
        callback: Callback query
        db: Database instance
    """
    user_id = callback.from_user.id
    
    # Get user statistics
    stats = await db.get_user_stats(user_id)
    
    if stats is None:
        await callback.answer(
            text="❌ Не удалось получить статистику",
            show_alert=True
        )
        return
    
    # Edit message
    await callback.message.edit_text(
        text=format_stats_message(stats),
        reply_markup=get_back_keyboard()
    )
    
    await callback.answer()


@command_router.callback_query(F.data == "rate_limit")
async def callback_rate_limit(callback: CallbackQuery):
    """Handle rate limit callback.
    
    Args:
        callback: Callback query
    """
    await callback.answer(
        text="⚠️ Вы отправляете слишком много запросов. Подождите немного.",
        show_alert=True
    )


@command_router.callback_query(F.data == "invalid_url")
async def callback_invalid_url(callback: CallbackQuery):
    """Handle invalid URL callback.
    
    Args:
        callback: Callback query
    """
    await callback.answer(
        text="❌ Некорректная ссылка на TikTok. Проверьте формат ссылки.",
        show_alert=True
    )


@command_router.callback_query(F.data == "error")
async def callback_error(callback: CallbackQuery):
    """Handle error callback.
    
    Args:
        callback: Callback query
    """
    await callback.answer(
        text="❌ Произошла ошибка. Попробуйте позже.",
        show_alert=True
    )


# Handler for TikTok URLs in private messages
from ..services.url_parser import URLParser
from ..services.downloader import TikTokDownloader
from ..services.file_manager import FileManager
from ..utils.formatters import format_file_size


def _is_photo_file(file_path: str) -> bool:
    """Check if a file should be sent as a photo."""
    return Path(file_path).suffix.lower() in {".jpg", ".jpeg", ".png"}


async def _send_photo_reply(message: Message, file_paths: list[str]):
    """Send one or more downloaded photos as replies."""
    if len(file_paths) == 1:
        file_path = file_paths[0]
        photo_file = FSInputFile(file_path)
        if _is_photo_file(file_path):
            await message.reply_photo(photo=photo_file)
        else:
            await message.reply_document(document=photo_file)
        return

    if all(_is_photo_file(path) for path in file_paths):
        for start in range(0, len(file_paths), 10):
            chunk = file_paths[start:start + 10]
            media_group = [
                InputMediaPhoto(media=FSInputFile(file_path))
                for file_path in chunk
            ]
            await message.reply_media_group(media=media_group)
        return

    for file_path in file_paths:
        media_file = FSInputFile(file_path)
        if _is_photo_file(file_path):
            await message.reply_photo(photo=media_file)
        else:
            await message.reply_document(document=media_file)


@command_router.message(
    F.text.regexp(r'https?://(?:www\.|m\.|vm\.|vt\.)?tiktok\.com/[^\s]+')
    | F.caption.regexp(r'https?://(?:www\.|m\.|vm\.|vt\.)?tiktok\.com/[^\s]+')
)
async def handle_tiktok_url(
    message: Message,
    db: Database,
    downloader: TikTokDownloader,
    file_manager: FileManager
):
    """Handle TikTok URLs sent directly to bot.
    
    Args:
        message: Telegram message
        db: Database instance
        downloader: TikTok downloader service
        file_manager: File manager service
    """
    user_id = message.from_user.id
    text = message.text or message.caption or ""

    video_url = URLParser.extract_and_validate(text)
    if not video_url:
        await message.reply("Некорректная ссылка на TikTok")
        return

    await db.add_user(
        user_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )

    status_msg = await message.reply("Скачиваю медиа...")

    try:
        download_result = await downloader.download_media(video_url)

        if not download_result["success"]:
            error_msg = download_result.get("error", "Не удалось скачать медиа")
            await status_msg.edit_text(f"Ошибка: {error_msg}")
            await db.log_download(
                user_id=user_id,
                video_url=video_url,
                success=False,
                error_message=error_msg
            )
            return

        file_size = download_result["file_size"]
        duration = download_result.get("duration")

        if download_result.get("media_type") == "photo":
            file_paths = download_result.get("file_paths", [])
            await _send_photo_reply(message, file_paths)
            await file_manager.delete_files(file_paths)
        else:
            file_path = download_result["file_path"]
            video_file = FSInputFile(file_path)
            await message.reply_video(
                video=video_file,
                supports_streaming=True
            )
            await file_manager.delete_file(file_path)

        await status_msg.delete()

        await db.log_download(
            user_id=user_id,
            video_url=video_url,
            success=True,
            file_size=file_size,
            duration=duration
        )

        logger.info(f"Media sent to user {user_id} (direct message)")
        return
    except Exception as e:
        logger.error(f"Error handling TikTok URL: {e}")
        await status_msg.edit_text("Произошла ошибка при скачивании")
        return
    
    # Extract and validate URL
    video_url = URLParser.extract_and_validate(text)
    
    if not video_url:
        await message.answer("❌ Некорректная ссылка на TikTok")
        return
    
    # Add user to database
    await db.add_user(
        user_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )
    
    # Send "downloading" message
    status_msg = await message.answer("⏬ Скачиваю видео...")
    
    try:
        # Download video
        download_result = await downloader.download_video(video_url)
        
        if not download_result['success']:
            error_msg = download_result.get('error', 'Не удалось скачать видео')
            await status_msg.edit_text(f"❌ Ошибка: {error_msg}")
            
            # Log failed download
            await db.log_download(
                user_id=user_id,
                video_url=video_url,
                success=False,
                error_message=error_msg
            )
            return
        
        # Download successful
        file_path = download_result['file_path']
        file_size = download_result['file_size']
        duration = download_result.get('duration')
        
        # Send video
        video_file = FSInputFile(file_path)
        await message.answer_video(
            video=video_file,
            
            supports_streaming=True
        )
        
        # Delete status message
        await status_msg.delete()
        
        # Delete video file
        await file_manager.delete_file(file_path)
        
        # Log successful download
        await db.log_download(
            user_id=user_id,
            video_url=video_url,
            success=True,
            file_size=file_size,
            duration=duration
        )
        
        logger.info(f"Video sent to user {user_id} (direct message)")
        
    except Exception as e:
        logger.error(f"Error handling TikTok URL: {e}")
        await status_msg.edit_text("❌ Произошла ошибка при скачивании видео")
