"""Inline query handlers for supported short-video links."""

import logging
import time
from pathlib import Path
from typing import Dict

from aiogram import Bot, Router
from aiogram.types import (
    FSInputFile,
    InlineQuery,
    InlineQueryResultCachedPhoto,
    InlineQueryResultCachedVideo,
)

from ..config import Config
from ..database.db import Database
from ..services.downloader import MediaDownloader
from ..services.file_manager import FileManager
from ..services.url_parser import URLParser, Platform
from ..utils.formatters import format_file_size

logger = logging.getLogger(__name__)

inline_router = Router()

# Telegram publishes cached inline results itself after the user selects one.
# A chosen_inline_result handler must not re-download or privately resend media.

# Rate limiting storage
_user_requests: Dict[int, list] = {}


def _is_photo_post_error(error_msg: str) -> bool:
    normalized = (error_msg or "").lower()
    return "фото-пост" in normalized or "photo-post" in normalized


def _is_photo_file(file_path: str) -> bool:
    return Path(file_path).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}


def _get_cache_chat_id(user_id: int) -> int:
    return Config.CACHE_CHANNEL_ID or user_id


async def _build_inline_photo_results(
    bot: Bot,
    user_id: int,
    file_paths: list[str],
    title: str,
) -> list:
    """Upload an album and create matching cached inline results."""
    cache_chat_id = _get_cache_chat_id(user_id)
    results = []

    for index, file_path in enumerate(file_paths[:10], start=1):
        is_photo = _is_photo_file(file_path)
        if is_photo:
            sent_message = await bot.send_photo(
                chat_id=cache_chat_id,
                photo=FSInputFile(file_path),
            )
            file_id = sent_message.photo[-1].file_id
        else:
            sent_message = await bot.send_video(
                chat_id=cache_chat_id,
                video=FSInputFile(file_path),
                supports_streaming=True,
            )
            file_id = sent_message.video.file_id

        if cache_chat_id == user_id:
            try:
                await sent_message.delete()
            except Exception:
                pass

        result_type = (
            InlineQueryResultCachedPhoto
            if is_photo
            else InlineQueryResultCachedVideo
        )
        result_kwargs = {
            "id": f"{user_id}_media_{index}_{int(time.time())}",
            "title": f"{'📷' if is_photo else '🎬'} {index}/{len(file_paths)}",
            "description": title[:80] if title else f"Медиа {index}",
        }
        if is_photo:
            result_kwargs["photo_file_id"] = file_id
        else:
            result_kwargs["video_file_id"] = file_id
        results.append(
            result_type(
                **result_kwargs,
            )
        )

    return results


def _check_rate_limit(user_id: int) -> bool:
    """Check if user exceeded rate limit. Returns True if within limits."""
    now = time.time()

    if user_id not in _user_requests:
        _user_requests[user_id] = []

    _user_requests[user_id] = [
        t for t in _user_requests[user_id]
        if now - t < Config.RATE_LIMIT_PERIOD
    ]

    if len(_user_requests[user_id]) >= Config.RATE_LIMIT_REQUESTS:
        return False

    _user_requests[user_id].append(now)
    return True


def _platform_label(platform: Platform) -> str:
    if platform == Platform.TIKTOK:
        return "TikTok"
    if platform == Platform.YOUTUBE_SHORTS:
        return "YouTube"
    if platform == Platform.INSTAGRAM_REELS:
        return "Instagram"
    if platform == Platform.VK:
        return "VK"
    if platform == Platform.OTHER:
        return "медиа"
    return platform.value


@inline_router.inline_query()
async def handle_inline_query(
    inline_query: InlineQuery,
    downloader: MediaDownloader,
    file_manager: FileManager,
    db: Database,
    bot: Bot,
):
    """Handle inline query: @bot <url>."""
    query_text = inline_query.query.strip()
    user_id = inline_query.from_user.id

    if not _check_rate_limit(user_id):
        await inline_query.answer(
            results=[],
            cache_time=1,
            is_personal=True,
            switch_pm_text="⚠️ Слишком много запросов",
            switch_pm_parameter="rate_limit",
        )
        return

    if not query_text:
        await inline_query.answer(
            results=[],
            cache_time=1,
            is_personal=True,
            switch_pm_text="📝 Вставьте ссылку на видео или публикацию",
            switch_pm_parameter="start",
        )
        return

    parsed = URLParser.extract_and_validate(query_text)
    if not parsed:
        await inline_query.answer(
            results=[],
            cache_time=1,
            is_personal=True,
            switch_pm_text="❌ Эта ссылка не поддерживается",
            switch_pm_parameter="invalid_url",
        )
        return

    await db.add_user(
        user_id=user_id,
        username=inline_query.from_user.username,
        first_name=inline_query.from_user.first_name,
        last_name=inline_query.from_user.last_name,
    )

    label = _platform_label(parsed.platform)
    logger.info(f"User {user_id} requested {label}: {parsed.normalized_url}")

    try:
        download_result = await downloader.download_media(
            platform=parsed.platform.value,
            url=parsed.normalized_url,
        )

        if not download_result["success"]:
            error_msg = download_result.get("error", "Не удалось скачать медиа")
            await inline_query.answer(
                results=[],
                cache_time=1,
                is_personal=True,
                switch_pm_text=f"❌ Ошибка: {error_msg[:30]}...",
                switch_pm_parameter="error",
            )
            await db.log_download(
                user_id=user_id,
                video_url=parsed.normalized_url,
                success=False,
                error_message=error_msg,
            )
            logger.warning(f"Download failed for user {user_id}: {error_msg}")
            return

        file_size = download_result["file_size"]
        duration = download_result.get("duration")
        title = download_result.get("title", f"{label} Video")

        # ── Photo post (TikTok only) ──
        if download_result.get("media_type") in {"photo", "album"}:
            file_paths = download_result.get("file_paths", [])
            try:
                results = await _build_inline_photo_results(
                    bot=bot,
                    user_id=user_id,
                    file_paths=file_paths,
                    title=title,
                )
                await inline_query.answer(
                    results=results,
                    cache_time=300,
                    is_personal=True,
                )
                await file_manager.delete_files(file_paths)
                await db.log_download(
                    user_id=user_id,
                    video_url=parsed.normalized_url,
                    success=True,
                    file_size=file_size,
                    duration=duration,
                )
                logger.info(f"Inline photo results sent for user {user_id}")
            except Exception as e:
                logger.error(f"Failed to upload photos for inline: {e}")
                await file_manager.delete_files(file_paths)
                raise
            return

        # ── Video ──
        file_path = download_result["file_path"]
        logger.info(
            f"Download successful: {file_path} ({format_file_size(file_size)})"
        )

        try:
            cache_chat_id = (
                Config.CACHE_CHANNEL_ID if Config.CACHE_CHANNEL_ID else user_id
            )

            sent_message = await bot.send_video(
                chat_id=cache_chat_id,
                video=FSInputFile(file_path),
                supports_streaming=True,
            )
            file_id = sent_message.video.file_id

            if cache_chat_id == user_id:
                try:
                    await sent_message.delete()
                except Exception:
                    pass

            result = InlineQueryResultCachedVideo(
                id=f"{user_id}_{int(time.time())}",
                video_file_id=file_id,
                title=f"🎬 {title[:50]}",
                description=(
                    f"📦 {format_file_size(file_size)}"
                    + (f" • ⏱ {duration}с" if duration else "")
                ),
            )

            await inline_query.answer(
                results=[result],
                cache_time=300,
                is_personal=True,
            )

            await file_manager.delete_file(file_path)
            await db.log_download(
                user_id=user_id,
                video_url=parsed.normalized_url,
                success=True,
                file_size=file_size,
                duration=duration,
            )
            logger.info(f"Inline cached video sent for user {user_id}")

        except Exception as e:
            logger.error(f"Failed to upload video for inline: {e}")
            await file_manager.delete_file(file_path)
            await db.log_download(
                user_id=user_id,
                video_url=parsed.normalized_url,
                success=False,
                error_message=str(e),
            )
            raise

    except Exception as e:
        logger.error(f"Error processing inline query: {e}")
        try:
            await inline_query.answer(
                results=[],
                cache_time=1,
                is_personal=True,
                switch_pm_text="❌ Произошла ошибка",
                switch_pm_parameter="error",
            )
        except Exception:
            pass
