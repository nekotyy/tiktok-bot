"""Command handlers and direct URL handler for TikTok and YouTube Shorts."""

import logging
from pathlib import Path
from typing import Optional

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    ChatMemberAdministrator,
    ChatMemberOwner,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)
from aiogram.filters import Command, CommandStart
from aiogram.utils.chat_action import ChatActionSender

from ..config import Config
from ..database.db import Database
from ..services.downloader import MediaDownloader
from ..services.file_manager import FileManager
from ..services.url_parser import URLParser, Platform
from ..utils.formatters import (
    format_start_message,
    format_help_message,
    format_stats_message,
    format_top_message,
)

logger = logging.getLogger(__name__)

command_router = Router()


def _get_requester_id(message: Message) -> int:
    """Return the user/channel identifier associated with the message."""
    if message.from_user:
        return message.from_user.id
    if message.sender_chat:
        return message.sender_chat.id
    return message.chat.id


def _get_requester_profile(
    message: Message,
) -> tuple[int, Optional[str], Optional[str], Optional[str]]:
    """Build a database-friendly profile for users, groups, and channels."""
    requester_id = _get_requester_id(message)

    if message.from_user:
        return (
            requester_id,
            message.from_user.username,
            message.from_user.first_name,
            message.from_user.last_name,
        )

    chat = message.sender_chat or message.chat
    return (
        requester_id,
        getattr(chat, "username", None),
        getattr(chat, "title", None),
        None,
    )


async def _ensure_chat_allowed(message: Message) -> bool:
    """Allow processing only in whitelisted chats/channels."""
    if Config.is_chat_allowed(message.chat.id):
        return True

    logger.info(
        "Ignoring message from non-whitelisted chat %s (%s)",
        message.chat.id,
        message.chat.type,
    )
    return False


def get_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📖 Помощь", callback_data="help"),
                InlineKeyboardButton(text="📊 Статистика", callback_data="stats"),
            ]
        ]
    )


def get_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="start")]
        ]
    )


async def _is_chat_admin(message: Message) -> bool:
    """Check if the user is an admin/owner of the chat. Always True in private."""
    if message.chat.type == "private":
        return True
    try:
        member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
        return isinstance(member, (ChatMemberAdministrator, ChatMemberOwner))
    except Exception:
        return False


def _is_pure_link_message(text: str) -> bool:
    """Return True if the message consists only of a URL and whitespace."""
    import re
    cleaned = re.sub(
        r'https?://(?:www\.|m\.|vm\.|vt\.)?tiktok\.com/[^\s]+'
        r'|https?://(?:www\.)?youtube\.com/shorts/[^\s]+'
        r'|https?://youtu\.be/[^\s]+',
        '',
        text,
    )
    return not cleaned.strip()


def get_settings_keyboard(settings: dict) -> InlineKeyboardMarkup:
    require = settings.get('require_pure_link', False)
    delete_src = settings.get('delete_source_messages', True)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=("✅ " if require else "❌ ") + "Только чистые ссылки",
                    callback_data="toggle_require_pure_link",
                )
            ],
            [
                InlineKeyboardButton(
                    text=("✅ " if delete_src else "❌ ") + "Удалять сообщения со ссылками",
                    callback_data="toggle_delete_source",
                )
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="start")],
        ]
    )


# ── Commands ────────────────────────────────────────────────────────

@command_router.message(CommandStart())
async def cmd_start(message: Message, db: Database):
    if not await _ensure_chat_allowed(message):
        return

    await db.add_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
    )
    await message.answer(
        text=format_start_message(),
        reply_markup=get_main_keyboard(),
    )
    logger.info(f"User {message.from_user.id} started the bot")


@command_router.message(Command("help"))
async def cmd_help(message: Message):
    if not await _ensure_chat_allowed(message):
        return

    await message.answer(
        text=format_help_message(),
        reply_markup=get_back_keyboard(),
    )


@command_router.message(Command("stats"))
@command_router.channel_post(Command("stats"))
async def cmd_stats(message: Message, db: Database):
    if not await _ensure_chat_allowed(message):
        return

    stats = await db.get_user_stats(_get_requester_id(message))
    if stats is None:
        await message.answer(
            text="❌ Не удалось получить статистику. Попробуйте позже.",
            reply_markup=get_back_keyboard(),
        )
        return
    await message.answer(
        text=format_stats_message(stats),
        reply_markup=get_back_keyboard(),
    )


@command_router.message(Command("top"))
@command_router.channel_post(Command("top"))
async def cmd_top(message: Message, db: Database):
    if not await _ensure_chat_allowed(message):
        return

    top_entries = await db.get_top_users(limit=10)
    await message.answer(
        text=format_top_message(top_entries),
        reply_markup=get_back_keyboard(),
    )


@command_router.message(Command("settings"))
@command_router.channel_post(Command("settings"))
async def cmd_settings(message: Message, db: Database):
    if not await _ensure_chat_allowed(message):
        return

    if not await _is_chat_admin(message):
        await message.answer("⚠️ Настройки доступны только администраторам чата.")
        return

    settings = await db.get_chat_settings(message.chat.id)
    text = (
        "⚙️ <b>Настройки чата</b>\n\n"
        "<b>Только чистые ссылки</b> — бот отвечает только если сообщение "
        "состоит только из ссылки (без лишнего текста).\n\n"
        "<b>Удалять сообщения со ссылками</b> — бот удаляет исходное сообщение "
        "пользователя после отправки видео."
    )
    await message.answer(text=text, reply_markup=get_settings_keyboard(settings))


# ── Callback queries ────────────────────────────────────────────────

@command_router.callback_query(F.data == "start")
async def callback_start(callback: CallbackQuery, db: Database):
    await db.add_user(
        user_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
        last_name=callback.from_user.last_name,
    )
    await callback.message.edit_text(
        text=format_start_message(),
        reply_markup=get_main_keyboard(),
    )
    await callback.answer()


@command_router.callback_query(F.data == "help")
async def callback_help(callback: CallbackQuery):
    await callback.message.edit_text(
        text=format_help_message(),
        reply_markup=get_back_keyboard(),
    )
    await callback.answer()


@command_router.callback_query(F.data == "stats")
async def callback_stats(callback: CallbackQuery, db: Database):
    stats = await db.get_user_stats(callback.from_user.id)
    if stats is None:
        await callback.answer(
            text="❌ Не удалось получить статистику",
            show_alert=True,
        )
        return
    await callback.message.edit_text(
        text=format_stats_message(stats),
        reply_markup=get_back_keyboard(),
    )
    await callback.answer()


@command_router.callback_query(F.data == "rate_limit")
async def callback_rate_limit(callback: CallbackQuery):
    await callback.answer(
        text="⚠️ Вы отправляете слишком много запросов. Подождите немного.",
        show_alert=True,
    )


@command_router.callback_query(F.data == "invalid_url")
async def callback_invalid_url(callback: CallbackQuery):
    await callback.answer(
        text="❌ Некорректная ссылка. Поддерживаются TikTok и YouTube Shorts.",
        show_alert=True,
    )


@command_router.callback_query(F.data == "error")
async def callback_error(callback: CallbackQuery):
    await callback.answer(
        text="❌ Произошла ошибка. Попробуйте позже.",
        show_alert=True,
    )


@command_router.callback_query(F.data == "toggle_require_pure_link")
async def callback_toggle_require_pure_link(callback: CallbackQuery, db: Database):
    chat_id = callback.message.chat.id
    settings = await db.get_chat_settings(chat_id)
    new_value = not settings.get('require_pure_link', False)
    await db.set_chat_setting(chat_id, require_pure_link=new_value)
    settings['require_pure_link'] = new_value
    await callback.message.edit_reply_markup(reply_markup=get_settings_keyboard(settings))
    await callback.answer()


@command_router.callback_query(F.data == "toggle_delete_source")
async def callback_toggle_delete_source(callback: CallbackQuery, db: Database):
    chat_id = callback.message.chat.id
    settings = await db.get_chat_settings(chat_id)
    new_value = not settings.get('delete_source_messages', True)
    await db.set_chat_setting(chat_id, delete_source_messages=new_value)
    settings['delete_source_messages'] = new_value
    await callback.message.edit_reply_markup(reply_markup=get_settings_keyboard(settings))
    await callback.answer()


# ── Direct URL handler (TikTok + YouTube Shorts) ────────────────────

def _is_photo_file(file_path: str) -> bool:
    return Path(file_path).suffix.lower() in {".jpg", ".jpeg", ".png"}


def _message_contains_supported_url(message: Message) -> bool:
    text = message.text or message.caption or ""
    return URLParser.extract_and_validate(text) is not None


async def _send_photo_reply(message: Message, file_paths: list[str]):
    if len(file_paths) == 1:
        file_path = file_paths[0]
        media_file = FSInputFile(file_path)
        if _is_photo_file(file_path):
            await message.reply_photo(photo=media_file)
        else:
            await message.reply_document(document=media_file)
        return

    if all(_is_photo_file(path) for path in file_paths):
        for start in range(0, len(file_paths), 10):
            chunk = file_paths[start:start + 10]
            media_group = [
                InputMediaPhoto(media=FSInputFile(fp))
                for fp in chunk
            ]
            await message.reply_media_group(media=media_group)
        return

    for file_path in file_paths:
        media_file = FSInputFile(file_path)
        if _is_photo_file(file_path):
            await message.reply_photo(photo=media_file)
        else:
            await message.reply_document(document=media_file)


async def _delete_source_message(message: Message):
    try:
        await message.delete()
        logger.info(
            "Deleted source message %s in chat %s",
            message.message_id,
            message.chat.id,
        )
    except Exception as e:
        logger.info(
            "Could not delete source message %s in chat %s: %s",
            message.message_id,
            message.chat.id,
            e,
        )


# Match both TikTok and YouTube Shorts URLs
URL_PATTERN = (
    r'https?://(?:www\.|m\.|vm\.|vt\.)?tiktok\.com/[^\s]+'
    r'|'
    r'https?://(?:www\.)?youtube\.com/shorts/[^\s]+'
    r'|'
    r'https?://youtu\.be/[^\s]+'
)


@command_router.message(_message_contains_supported_url)
@command_router.channel_post(_message_contains_supported_url)
async def handle_media_url(
    message: Message,
    db: Database,
    downloader: MediaDownloader,
    file_manager: FileManager,
):
    """Handle TikTok and YouTube Shorts URLs sent directly to the bot."""
    if not await _ensure_chat_allowed(message):
        return

    user_id, username, first_name, last_name = _get_requester_profile(message)
    text = message.text or message.caption or ""

    parsed = URLParser.extract_and_validate(text)
    if not parsed:
        await message.reply(
            "❌ Некорректная ссылка. Поддерживаются TikTok и YouTube Shorts."
        )
        return

    chat_settings = await db.get_chat_settings(message.chat.id)

    if chat_settings.get('require_pure_link') and not _is_pure_link_message(text):
        logger.info(
            "Skipping non-pure link message in chat %s (require_pure_link is on)",
            message.chat.id,
        )
        return

    await db.add_user(
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
    )

    platform_label = "TikTok" if parsed.platform == Platform.TIKTOK else "YouTube Short"
    logger.info(
        "Requester %s in chat %s requested %s: %s",
        user_id,
        message.chat.id,
        platform_label,
        parsed.normalized_url,
    )

    try:
        async with ChatActionSender.typing(
            bot=message.bot,
            chat_id=message.chat.id,
            message_thread_id=message.message_thread_id,
        ):
            download_result = await downloader.download_media(
                platform=parsed.platform.value,
                url=parsed.normalized_url,
            )

        if not download_result["success"]:
            error_msg = download_result.get("error", "Не удалось скачать медиа")
            await message.reply(f"❌ Ошибка: {error_msg}")
            await db.log_download(
                user_id=user_id,
                video_url=parsed.normalized_url,
                success=False,
                error_message=error_msg,
            )
            return

        file_size = download_result["file_size"]
        duration = download_result.get("duration")

        if download_result.get("media_type") == "photo":
            file_paths = download_result.get("file_paths", [])
            async with ChatActionSender.upload_photo(
                bot=message.bot,
                chat_id=message.chat.id,
                message_thread_id=message.message_thread_id,
            ):
                await _send_photo_reply(message, file_paths)
            await file_manager.delete_files(file_paths)
        else:
            file_path = download_result["file_path"]
            video_file = FSInputFile(file_path)
            async with ChatActionSender.upload_video(
                bot=message.bot,
                chat_id=message.chat.id,
                message_thread_id=message.message_thread_id,
            ):
                await message.reply_video(
                    video=video_file,
                    supports_streaming=True,
                )
            await file_manager.delete_file(file_path)

        await db.log_download(
            user_id=user_id,
            video_url=parsed.normalized_url,
            success=True,
            file_size=file_size,
            duration=duration,
        )

        if chat_settings.get('delete_source_messages'):
            await _delete_source_message(message)
        logger.info(
            "%s sent back to chat %s for requester %s",
            platform_label,
            message.chat.id,
            user_id,
        )

    except Exception as e:
        logger.error(f"Error handling media URL: {e}")
        await message.reply("❌ Произошла ошибка при скачивании")
