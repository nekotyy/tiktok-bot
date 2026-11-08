"""Regression tests for inline media delivery."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from bot.config import Config
from bot.handlers import inline


class InlineHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original_cache_channel_id = Config.CACHE_CHANNEL_ID
        self.original_extract_and_validate = inline.URLParser.extract_and_validate
        Config.CACHE_CHANNEL_ID = -1001234567890
        inline._user_requests.clear()
        inline.URLParser.extract_and_validate = MagicMock(
            return_value=SimpleNamespace(
                platform=inline.Platform.TIKTOK,
                normalized_url="https://www.tiktok.com/@author/video/1234567890",
            )
        )

        self.inline_query = SimpleNamespace(
            query="https://www.tiktok.com/@author/video/1234567890",
            from_user=SimpleNamespace(
                id=42,
                username="viewer",
                first_name="Viewer",
                last_name=None,
            ),
            answer=AsyncMock(),
        )
        self.downloader = AsyncMock()
        self.downloader.download_media.return_value = {
            "success": True,
            "media_type": "video",
            "file_path": "downloads/video.mp4",
            "file_size": 123456,
            "duration": 17,
            "title": "Test video",
        }
        self.file_manager = AsyncMock()
        self.db = AsyncMock()
        self.bot = AsyncMock()

    async def asyncTearDown(self):
        Config.CACHE_CHANNEL_ID = self.original_cache_channel_id
        inline.URLParser.extract_and_validate = self.original_extract_and_validate
        inline._user_requests.clear()

    async def test_successful_video_is_returned_as_cached_inline_result(self):
        self.bot.send_video.return_value = SimpleNamespace(
            video=SimpleNamespace(file_id="cached-video-id"),
            delete=AsyncMock(),
        )

        await inline.handle_inline_query(
            self.inline_query,
            self.downloader,
            self.file_manager,
            self.db,
            self.bot,
        )

        self.bot.send_video.assert_awaited_once()
        self.assertEqual(
            self.bot.send_video.await_args.kwargs["chat_id"],
            Config.CACHE_CHANNEL_ID,
        )
        answer = self.inline_query.answer.await_args.kwargs
        self.assertEqual(len(answer["results"]), 1)
        self.assertEqual(answer["results"][0].video_file_id, "cached-video-id")
        self.db.log_download.assert_awaited_once_with(
            user_id=42,
            video_url="https://www.tiktok.com/@author/video/1234567890",
            success=True,
            file_size=123456,
            duration=17,
        )
        self.file_manager.delete_file.assert_awaited_once_with(
            "downloads/video.mp4"
        )

    async def test_failed_inline_upload_is_not_retried_in_private_chat(self):
        self.bot.send_video.side_effect = RuntimeError("Telegram upload failed")

        await inline.handle_inline_query(
            self.inline_query,
            self.downloader,
            self.file_manager,
            self.db,
            self.bot,
        )

        self.bot.send_video.assert_awaited_once()
        self.assertEqual(
            self.bot.send_video.await_args.kwargs["chat_id"],
            Config.CACHE_CHANNEL_ID,
        )
        answer = self.inline_query.answer.await_args.kwargs
        self.assertEqual(answer["results"], [])
        self.assertEqual(answer["switch_pm_parameter"], "error")
        self.file_manager.delete_file.assert_awaited_once_with(
            "downloads/video.mp4"
        )
        self.db.log_download.assert_awaited_once_with(
            user_id=42,
            video_url="https://www.tiktok.com/@author/video/1234567890",
            success=False,
            error_message="Telegram upload failed",
        )

    def test_chosen_inline_results_have_no_private_delivery_handler(self):
        observer = inline.inline_router.observers.get("chosen_inline_result")
        self.assertTrue(observer is None or not observer.handlers)
