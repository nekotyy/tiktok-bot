import importlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch


def _load_downloader_module():
    sys.modules.pop("bot.services.downloader", None)
    return importlib.import_module("bot.services.downloader")


class DownloaderHelperTests(unittest.TestCase):
    def setUp(self):
        self.module = _load_downloader_module()
        self.downloader = self.module.MediaDownloader(
            downloads_path="downloads",
            max_file_size_bytes=10 * 1024 * 1024,
        )

    def test_find_downloaded_file_uses_actual_extension(self):
        class FakePath:
            def __init__(self, name, suffix, mtime, is_file=True):
                self.name = name
                self.suffix = suffix
                self._mtime = mtime
                self._is_file = is_file

            def is_file(self):
                return self._is_file

            def stat(self):
                return SimpleNamespace(st_mtime=self._mtime)

            def __str__(self):
                return f"downloads/{self.name}"

        class FakeDownloadsPath:
            def glob(self, pattern):
                return [
                    FakePath("media123.mp4.part", ".part", 3),
                    FakePath("media123.webm", ".webm", 1),
                    FakePath("media123.mp4", ".mp4", 2),
                    FakePath("media123.txt", ".txt", 4),
                ]

        self.downloader.downloads_path = FakeDownloadsPath()

        found = self.downloader._find_downloaded_file(
            "media123",
            self.downloader.VIDEO_EXTENSIONS,
        )

        self.assertEqual(found, "downloads/media123.mp4")

    def test_estimate_filesize_sums_requested_video_and_audio(self):
        size = self.downloader._estimate_filesize(
            {
                "requested_formats": [
                    {"filesize": 1024},
                    {"filesize_approx": 2048},
                ],
                "filesize": 999999,
            }
        )

        self.assertEqual(size, 3072)

    def test_collect_audio_url_prefers_audio_only_formats(self):
        audio_url = self.downloader._collect_audio_url(
            {
                "formats": [
                    {"url": "https://example.com/video.mp4", "vcodec": "h264", "acodec": "aac"},
                    {"url": "https://example.com/audio.m4a", "vcodec": "none", "acodec": "aac"},
                ]
            }
        )

        self.assertEqual(audio_url, "https://example.com/audio.m4a")

    def test_guess_audio_extension_treats_mp4_audio_as_m4a(self):
        self.assertEqual(
            self.downloader._guess_audio_extension(
                "https://example.com/play",
                "video/mp4",
            ),
            ".m4a",
        )

    def test_gallery_dl_media_collection_includes_photos_and_audio(self):
        class FakeDataJob:
            def __init__(self, url, file=None):
                self.data_urls = [
                    "https://example.com/photo1.jpg",
                    "https://example.com/audio.mp3",
                    "https://example.com/photo2.webp",
                ]
                self.data_meta = [
                    {"type": "image", "extension": "jpg"},
                    {"type": "audio", "extension": "mp3", "title": "Sound", "duration": 12},
                    {"type": "image", "extension": "webp"},
                ]

            def run(self):
                return None

        with patch.object(self.module, "DataJob", FakeDataJob):
            media = self.downloader._collect_tiktok_media_with_gallery_dl(
                "https://www.tiktok.com/@user/photo/123"
            )

        self.assertEqual(
            media["photo_urls"],
            ["https://example.com/photo1.jpg", "https://example.com/photo2.webp"],
        )
        self.assertEqual(media["audio_url"], "https://example.com/audio.mp3")
        self.assertEqual(media["audio_title"], "Sound")
        self.assertEqual(media["audio_duration"], 12)
