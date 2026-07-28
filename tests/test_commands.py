import importlib
import os
import sys
import types
import unittest
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


os.environ.setdefault("BOT_TOKEN", "test-token")


class _FilterExpression:
    def __or__(self, other):
        return self


class _FilterField:
    def regexp(self, pattern):
        return _FilterExpression()

    def __eq__(self, other):
        return _FilterExpression()


class _FProxy:
    text = _FilterField()
    caption = _FilterField()
    data = _FilterField()


class _Router:
    def message(self, *args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def channel_post(self, *args, **kwargs):
        return self.message(*args, **kwargs)

    def callback_query(self, *args, **kwargs):
        return self.message(*args, **kwargs)


class _AsyncNoopContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _ChatActionSender:
    @staticmethod
    def typing(**kwargs):
        return _AsyncNoopContext()

    @staticmethod
    def upload_photo(**kwargs):
        return _AsyncNoopContext()

    @staticmethod
    def upload_video(**kwargs):
        return _AsyncNoopContext()

    @staticmethod
    def upload_document(**kwargs):
        return _AsyncNoopContext()


class _FSInputFile:
    def __init__(self, path):
        self.path = path


class _InlineKeyboardButton:
    def __init__(self, text, callback_data):
        self.text = text
        self.callback_data = callback_data


class _InlineKeyboardMarkup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


class _InputMediaPhoto:
    def __init__(self, media):
        self.media = media


class _InputMediaVideo:
    def __init__(self, media, supports_streaming=False):
        self.media = media
        self.supports_streaming = supports_streaming


class _Command:
    def __init__(self, *args, **kwargs):
        pass


class _CommandStart(_Command):
    pass


def _install_stub_modules():
    dotenv_module = types.ModuleType("dotenv")
    dotenv_module.load_dotenv = lambda *args, **kwargs: None
    sys.modules["dotenv"] = dotenv_module

    aiogram_module = types.ModuleType("aiogram")
    aiogram_module.Router = _Router
    aiogram_module.F = _FProxy()
    sys.modules["aiogram"] = aiogram_module

    aiogram_types_module = types.ModuleType("aiogram.types")
    aiogram_types_module.CallbackQuery = object
    aiogram_types_module.ChatMemberAdministrator = object
    aiogram_types_module.ChatMemberOwner = object
    aiogram_types_module.FSInputFile = _FSInputFile
    aiogram_types_module.InlineKeyboardButton = _InlineKeyboardButton
    aiogram_types_module.InlineKeyboardMarkup = _InlineKeyboardMarkup
    aiogram_types_module.InputMediaPhoto = _InputMediaPhoto
    aiogram_types_module.InputMediaVideo = _InputMediaVideo
    aiogram_types_module.Message = object
    sys.modules["aiogram.types"] = aiogram_types_module

    aiogram_filters_module = types.ModuleType("aiogram.filters")
    aiogram_filters_module.Command = _Command
    aiogram_filters_module.CommandStart = _CommandStart
    sys.modules["aiogram.filters"] = aiogram_filters_module

    aiogram_utils_module = types.ModuleType("aiogram.utils")
    sys.modules["aiogram.utils"] = aiogram_utils_module

    aiogram_chat_action_module = types.ModuleType("aiogram.utils.chat_action")
    aiogram_chat_action_module.ChatActionSender = _ChatActionSender
    sys.modules["aiogram.utils.chat_action"] = aiogram_chat_action_module

    database_module = types.ModuleType("bot.database.db")

    class Database:
        pass

    database_module.Database = Database
    sys.modules["bot.database.db"] = database_module

    downloader_module = types.ModuleType("bot.services.downloader")

    class MediaDownloader:
        pass

    downloader_module.MediaDownloader = MediaDownloader
    sys.modules["bot.services.downloader"] = downloader_module

    file_manager_module = types.ModuleType("bot.services.file_manager")

    class FileManager:
        pass

    file_manager_module.FileManager = FileManager
    sys.modules["bot.services.file_manager"] = file_manager_module

    url_parser_module = types.ModuleType("bot.services.url_parser")

    from enum import Enum

    class Platform(Enum):
        TIKTOK = "tiktok"
        YOUTUBE_SHORTS = "youtube_shorts"
        INSTAGRAM_REELS = "instagram_reels"
        VK = "vk"
        OTHER = "other"

    class URLParser:
        @staticmethod
        def extract_and_validate(text):
            return None

    url_parser_module.Platform = Platform
    url_parser_module.URLParser = URLParser
    sys.modules["bot.services.url_parser"] = url_parser_module

    formatters_module = types.ModuleType("bot.utils.formatters")
    formatters_module.format_start_message = lambda: "start"
    formatters_module.format_help_message = lambda: "help"
    formatters_module.format_stats_message = lambda stats: f"stats:{stats}"
    formatters_module.format_top_message = lambda top: f"top:{top}"
    sys.modules["bot.utils.formatters"] = formatters_module


_install_stub_modules()

commands = importlib.import_module("bot.handlers.commands")
config_module = importlib.import_module("bot.config")
Config = config_module.Config


@dataclass
class DummyUser:
    id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None


@dataclass
class DummyChat:
    id: int
    type: str = "private"
    title: str | None = None
    username: str | None = None


class DummyMessage:
    def __init__(
        self,
        *,
        chat,
        text=None,
        caption=None,
        from_user=None,
        sender_chat=None,
    ):
        self.chat = chat
        self.text = text
        self.caption = caption
        self.from_user = from_user
        self.sender_chat = sender_chat
        self.bot = object()
        self.message_thread_id = None
        self.message_id = 1
        self.deleted = False
        self.reply_calls = []
        self.answer_calls = []
        self.reply_video_calls = []
        self.reply_photo_calls = []
        self.reply_audio_calls = []
        self.reply_document_calls = []
        self.reply_media_group_calls = []

    async def answer(self, text=None, reply_markup=None):
        self.answer_calls.append(
            {"text": text, "reply_markup": reply_markup}
        )

    async def reply(self, text):
        self.reply_calls.append(text)

    async def reply_video(self, video, supports_streaming=False):
        self.reply_video_calls.append(
            {
                "video": video,
                "supports_streaming": supports_streaming,
            }
        )

    async def reply_photo(self, photo):
        self.reply_photo_calls.append({"photo": photo})

    async def reply_audio(self, audio, title=None):
        self.reply_audio_calls.append({"audio": audio, "title": title})

    async def reply_document(self, document):
        self.reply_document_calls.append({"document": document})

    async def reply_media_group(self, media):
        self.reply_media_group_calls.append({"media": media})

    async def delete(self):
        self.deleted = True


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.original_allowed_chat_ids = Config.ALLOWED_CHAT_IDS
        self.original_auto_allow_member_chats = Config.AUTO_ALLOW_MEMBER_CHATS
        Config.AUTO_ALLOW_MEMBER_CHATS = False

    def tearDown(self):
        Config.ALLOWED_CHAT_IDS = self.original_allowed_chat_ids
        Config.AUTO_ALLOW_MEMBER_CHATS = self.original_auto_allow_member_chats

    def test_parse_id_list_supports_multiple_separators(self):
        parsed = Config._parse_id_list("123, -100200300\n-100400500; 999")
        self.assertEqual(parsed, {123, -100200300, -100400500, 999})

    def test_get_int_env_falls_back_on_placeholder(self):
        original = os.environ.get("TEST_INT_ENV")
        os.environ["TEST_INT_ENV"] = "your_telegram_id"
        try:
            self.assertEqual(config_module._get_int_env("TEST_INT_ENV", 7), 7)
        finally:
            if original is None:
                os.environ.pop("TEST_INT_ENV", None)
            else:
                os.environ["TEST_INT_ENV"] = original

    def test_is_chat_allowed_respects_whitelist(self):
        Config.ALLOWED_CHAT_IDS = {-1001, 42}
        self.assertTrue(Config.is_chat_allowed(-1001))
        self.assertTrue(Config.is_chat_allowed(42))
        self.assertFalse(Config.is_chat_allowed(7))

        Config.ALLOWED_CHAT_IDS = set()
        self.assertTrue(Config.is_chat_allowed(7))


class CommandHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original_allowed_chat_ids = Config.ALLOWED_CHAT_IDS
        self.original_auto_allow_member_chats = Config.AUTO_ALLOW_MEMBER_CHATS
        self.original_extract_and_validate = commands.URLParser.extract_and_validate
        Config.ALLOWED_CHAT_IDS = {-1001234567890}
        Config.AUTO_ALLOW_MEMBER_CHATS = False
        commands.URLParser.extract_and_validate = MagicMock(
            return_value=SimpleNamespace(
                platform=commands.Platform.TIKTOK,
                normalized_url="https://www.tiktok.com/@author/video/1234567890",
            )
        )

        self.db = AsyncMock()
        self.db.get_chat_settings.return_value = {
            "delete_source_messages": True,
            "require_pure_link": False,
        }
        self.downloader = AsyncMock()
        self.file_manager = AsyncMock()

    async def asyncTearDown(self):
        Config.ALLOWED_CHAT_IDS = self.original_allowed_chat_ids
        Config.AUTO_ALLOW_MEMBER_CHATS = self.original_auto_allow_member_chats
        commands.URLParser.extract_and_validate = self.original_extract_and_validate

    async def test_channel_post_is_processed_and_sent_back_to_channel(self):
        message = DummyMessage(
            chat=DummyChat(
                id=-1001234567890,
                type="channel",
                title="My Channel",
                username="my_channel",
            ),
            text="https://www.tiktok.com/@author/video/1234567890",
            sender_chat=DummyChat(
                id=-1001234567890,
                type="channel",
                title="My Channel",
                username="my_channel",
            ),
        )
        self.downloader.download_media.return_value = {
            "success": True,
            "media_type": "video",
            "file_path": "downloads/video.mp4",
            "file_size": 123456,
            "duration": 17,
        }

        await commands.handle_media_url(
            message,
            self.db,
            self.downloader,
            self.file_manager,
        )

        self.db.add_user.assert_awaited_once_with(
            user_id=-1001234567890,
            username="my_channel",
            first_name="My Channel",
            last_name=None,
        )
        self.downloader.download_media.assert_awaited_once_with(
            platform="tiktok",
            url="https://www.tiktok.com/@author/video/1234567890",
        )
        self.assertEqual(len(message.reply_video_calls), 1)
        self.assertEqual(
            message.reply_video_calls[0]["video"].path,
            "downloads/video.mp4",
        )
        self.assertTrue(message.reply_video_calls[0]["supports_streaming"])
        self.assertTrue(message.deleted)
        self.file_manager.delete_file.assert_awaited_once_with("downloads/video.mp4")
        self.db.log_download.assert_awaited_once_with(
            user_id=-1001234567890,
            video_url="https://www.tiktok.com/@author/video/1234567890",
            success=True,
            file_size=123456,
            duration=17,
        )

    async def test_instagram_reel_is_processed(self):
        commands.URLParser.extract_and_validate = MagicMock(
            return_value=SimpleNamespace(
                platform=commands.Platform.INSTAGRAM_REELS,
                normalized_url="https://www.instagram.com/reel/ABC123/",
            )
        )
        message = DummyMessage(
            chat=DummyChat(id=-1001234567890, type="private"),
            text="https://www.instagram.com/reel/ABC123/?igsh=test",
            from_user=DummyUser(id=42, username="viewer", first_name="Viewer"),
        )
        self.downloader.download_media.return_value = {
            "success": True,
            "media_type": "video",
            "file_path": "downloads/reel.mp4",
            "file_size": 98765,
            "duration": 11,
        }

        await commands.handle_media_url(
            message,
            self.db,
            self.downloader,
            self.file_manager,
        )

        self.downloader.download_media.assert_awaited_once_with(
            platform="instagram_reels",
            url="https://www.instagram.com/reel/ABC123/",
        )
        self.assertEqual(len(message.reply_video_calls), 1)
        self.file_manager.delete_file.assert_awaited_once_with("downloads/reel.mp4")

    async def test_tiktok_photo_post_is_sent_without_audio(self):
        message = DummyMessage(
            chat=DummyChat(id=-1001234567890, type="private"),
            text="https://www.tiktok.com/@author/photo/1234567890",
            from_user=DummyUser(id=42, username="viewer", first_name="Viewer"),
        )
        self.downloader.download_media.return_value = {
            "success": True,
            "media_type": "photo",
            "file_paths": ["downloads/photo1.jpg"],
            "file_size": 123456,
            "duration": 17,
        }

        await commands.handle_media_url(
            message,
            self.db,
            self.downloader,
            self.file_manager,
        )

        self.assertEqual(len(message.reply_photo_calls), 1)
        self.assertEqual(len(message.reply_audio_calls), 0)
        self.file_manager.delete_files.assert_awaited_once_with(
            ["downloads/photo1.jpg"]
        )

    async def test_non_whitelisted_chat_is_ignored(self):
        message = DummyMessage(
            chat=DummyChat(id=-1009999999999, type="channel"),
            text="https://www.tiktok.com/@author/video/1234567890",
            sender_chat=DummyChat(id=-1009999999999, type="channel"),
        )

        await commands.handle_media_url(
            message,
            self.db,
            self.downloader,
            self.file_manager,
        )

        self.db.add_user.assert_not_awaited()
        self.db.log_download.assert_not_awaited()
        self.downloader.download_media.assert_not_awaited()
        self.file_manager.delete_file.assert_not_awaited()
        self.assertFalse(message.deleted)
        self.assertEqual(message.reply_calls, [])
        self.assertEqual(message.reply_video_calls, [])

    async def test_channel_stats_uses_sender_chat_id(self):
        message = DummyMessage(
            chat=DummyChat(id=-1001234567890, type="channel", title="My Channel"),
            text="/stats",
            sender_chat=DummyChat(id=-1001234567890, type="channel", title="My Channel"),
        )
        self.db.get_user_stats.return_value = {"total_downloads": 5}

        await commands.cmd_stats(message, self.db)

        self.db.get_user_stats.assert_awaited_once_with(-1001234567890)
        self.assertEqual(message.answer_calls[0]["text"], "stats:{'total_downloads': 5}")

    async def test_send_photo_reply_splits_into_albums_of_ten(self):
        message = DummyMessage(chat=DummyChat(id=-1001234567890, type="channel"))
        file_paths = [f"downloads/{index}.jpg" for index in range(1, 24)]

        await commands._send_photo_reply(message, file_paths)

        self.assertEqual(len(message.reply_media_group_calls), 3)
        self.assertEqual(len(message.reply_media_group_calls[0]["media"]), 10)
        self.assertEqual(len(message.reply_media_group_calls[1]["media"]), 10)
        self.assertEqual(len(message.reply_media_group_calls[2]["media"]), 3)

    async def test_send_mixed_instagram_album_as_photo_and_video_group(self):
        message = DummyMessage(chat=DummyChat(id=-1001234567890))

        await commands._send_photo_reply(
            message,
            ["downloads/photo.jpg", "downloads/video.mp4"],
        )

        media = message.reply_media_group_calls[0]["media"]
        self.assertIsInstance(media[0], _InputMediaPhoto)
        self.assertIsInstance(media[1], _InputMediaVideo)
        self.assertTrue(media[1].supports_streaming)

    async def test_top_command_returns_leaderboard(self):
        message = DummyMessage(
            chat=DummyChat(id=-1001234567890, type="channel", title="My Channel"),
            text="/top",
            sender_chat=DummyChat(id=-1001234567890, type="channel", title="My Channel"),
        )
        self.db.get_top_users.return_value = [{"user_id": 1, "total_downloads": 7}]

        await commands.cmd_top(message, self.db)

        self.db.get_top_users.assert_awaited_once_with(limit=10)
        self.assertEqual(message.answer_calls[0]["text"], "top:[{'user_id': 1, 'total_downloads': 7}]")

    def test_message_contains_supported_url_with_text_prefix(self):
        commands.URLParser.extract_and_validate = MagicMock(
            return_value=SimpleNamespace(
                platform=commands.Platform.TIKTOK,
                normalized_url="https://vt.tiktok.com/ZS9k6HCQT/",
            )
        )
        message = DummyMessage(
            chat=DummyChat(id=-1001234567890),
            text="Twitch:mafanyaking https://vt.tiktok.com/ZS9k6HCQT/",
        )

        self.assertTrue(commands._message_contains_supported_url(message))
        commands.URLParser.extract_and_validate.assert_called_once_with(
            "Twitch:mafanyaking https://vt.tiktok.com/ZS9k6HCQT/"
        )

    def test_pure_link_message_accepts_instagram_reel(self):
        self.assertTrue(
            commands._is_pure_link_message(
                " https://www.instagram.com/reel/ABC123/?igsh=test "
            )
        )

