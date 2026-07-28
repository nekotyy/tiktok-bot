import importlib
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def _load_downloader_module():
    sys.modules.pop("bot.services.downloader", None)
    return importlib.import_module("bot.services.downloader")


class DownloaderHelperTests(unittest.TestCase):
    def setUp(self):
        self.module = _load_downloader_module()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.downloader = self.module.MediaDownloader(
            downloads_path=self.temp_dir.name,
            max_file_size_bytes=10 * 1024 * 1024,
        )

    def test_video_selector_never_uses_unqualified_video_fallback(self):
        media_format = self.downloader._get_video_ydl_opts("media123")["format"]

        self.assertIn("+ba", media_format)
        self.assertIn("[acodec!=none]", media_format)
        self.assertNotIn("best[vcodec!=none]", media_format)

    def test_impersonation_string_is_converted_for_current_ytdlp_api(self):
        downloader = self.module.MediaDownloader(
            downloads_path=self.temp_dir.name,
            max_file_size_bytes=10 * 1024 * 1024,
            impersonate="chrome",
        )

        target = downloader._get_common_ydl_opts()["impersonate"]

        self.assertEqual(str(target), "chrome")

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

    def test_missing_audio_is_repaired_when_source_has_audio(self):
        video_only_probe = {
            "streams": [{"codec_type": "video", "codec_name": "h264"}]
        }
        repaired_probe = {
            "streams": [
                {"codec_type": "video", "codec_name": "h264"},
                {"codec_type": "audio", "codec_name": "aac"},
            ]
        }
        source_info = {
            "formats": [
                {"vcodec": "h264", "acodec": "none"},
                {"vcodec": "none", "acodec": "aac"},
            ]
        }

        with (
            patch.object(
                self.downloader,
                "_probe_media",
                side_effect=[video_only_probe, repaired_probe],
            ),
            patch.object(
                self.downloader,
                "_repair_missing_audio",
                return_value="repaired.mp4",
            ) as repair,
            patch.object(
                self.downloader,
                "_convert_for_telegram",
                return_value="final.mp4",
            ) as convert_video,
        ):
            result = self.downloader._ensure_audio_and_telegram_compatibility(
                url="https://example.com/video",
                file_path="silent.mp4",
                info=source_info,
                media_id="media123",
            )

        self.assertEqual(result, "final.mp4")
        repair.assert_called_once_with(
            url="https://example.com/video",
            video_path="silent.mp4",
            media_id="media123",
        )
        convert_video.assert_called_once_with(
            "repaired.mp4",
            repaired_probe,
            "media123",
        )

    def test_intentionally_silent_source_does_not_download_fake_audio(self):
        video_only_probe = {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "pix_fmt": "yuv420p",
                }
            ]
        }
        source_info = {
            "formats": [{"vcodec": "h264", "acodec": "none"}]
        }

        with (
            patch.object(
                self.downloader,
                "_probe_media",
                return_value=video_only_probe,
            ),
            patch.object(self.downloader, "_repair_missing_audio") as repair,
            patch.object(
                self.downloader,
                "_convert_for_telegram",
                return_value="silent.mp4",
            ),
        ):
            result = self.downloader._ensure_audio_and_telegram_compatibility(
                url="https://example.com/video",
                file_path="silent.mp4",
                info=source_info,
                media_id="media123",
            )

        self.assertEqual(result, "silent.mp4")
        repair.assert_not_called()

    def test_gallery_dl_ignores_photo_post_audio(self):
        class FakeDataJob:
            def __init__(self, url, file=None):
                self.data_urls = [
                    "https://example.com/photo1.jpg",
                    "https://example.com/audio.mp3",
                    "https://example.com/photo2.webp",
                ]
                self.data_meta = [
                    {"type": "image", "extension": "jpg"},
                    {"type": "audio", "extension": "mp3", "title": "Sound"},
                    {"type": "image", "extension": "webp"},
                ]
                self.exception = None

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
        self.assertIsNone(media["audio_url"])
        self.assertIsNone(media["audio_title"])

    def test_guess_audio_extension_treats_mp4_audio_as_m4a(self):
        self.assertEqual(
            self.downloader._guess_audio_extension(
                "https://example.com/play",
                "video/mp4",
            ),
            ".m4a",
        )

    def test_antibot_error_recommends_network_fallback(self):
        result = self.downloader._format_youtube_error(
            Exception("Sign in to confirm you’re not a bot. Use --cookies")
        )

        self.assertFalse(result["success"])
        self.assertIn("YTDLP_PROXY", result["error"])
        self.assertNotIn("--cookies", result["error"])

    def test_instagram_uses_public_extractor_before_generic_fallbacks(self):
        public_media = {
            "items": [
                {
                    "kind": "photo",
                    "url": "https://cdn.example/photo.jpg",
                    "metadata": {},
                }
            ],
            "metadata": {"title": "Public post"},
        }
        public_result = {
            "success": True,
            "media_type": "photo",
            "file_paths": ["photo.jpg"],
            "file_size": 123,
        }

        with (
            patch.object(
                self.downloader.instagram,
                "extract",
                return_value=public_media,
            ) as extract,
            patch.object(
                self.downloader,
                "_download_gallery_album_sync",
                return_value=public_result,
            ) as download_album,
            patch.object(self.downloader, "_download_video_sync") as video,
            patch.object(self.downloader, "_collect_gallery_media") as gallery,
        ):
            result = self.downloader._download_instagram_sync(
                "https://www.instagram.com/p/Public123/",
                "media123",
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["platform"], "instagram_reels")
        extract.assert_called_once()
        download_album.assert_called_once_with(
            public_media,
            "media123",
            title_fallback="Instagram Post",
            instagram_public=True,
        )
        video.assert_not_called()
        gallery.assert_not_called()

    @unittest.skipUnless(
        shutil.which("ffmpeg") and shutil.which("ffprobe"),
        "ffmpeg and ffprobe are required",
    )
    def test_telegram_conversion_preserves_audio_stream(self):
        source = str(Path(self.temp_dir.name) / "source.mkv")
        self.downloader._run_ffmpeg(
            [
                "-f",
                "lavfi",
                "-i",
                "color=size=64x64:rate=10:color=black",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=1000:sample_rate=44100",
                "-t",
                "0.3",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                source,
            ]
        )
        source_probe = self.downloader._probe_media(source)

        converted = self.downloader._convert_for_telegram(
            source,
            source_probe,
            "media123",
        )
        converted_probe = self.downloader._probe_media(converted)

        self.assertEqual(Path(converted).suffix, ".mp4")
        self.assertIsNotNone(self.downloader._stream(converted_probe, "video"))
        self.assertIsNotNone(self.downloader._stream(converted_probe, "audio"))
