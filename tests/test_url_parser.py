import importlib
import sys
import unittest


def _load_url_parser_module():
    sys.modules.pop("bot.services.url_parser", None)
    return importlib.import_module("bot.services.url_parser")


class URLParserTests(unittest.TestCase):
    def setUp(self):
        module = _load_url_parser_module()
        self.Platform = module.Platform
        self.URLParser = module.URLParser

    def test_extracts_and_normalizes_instagram_reel(self):
        parsed = self.URLParser.extract_and_validate(
            "watch this https://www.instagram.com/reel/ABC123/?igsh=test"
        )

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.platform, self.Platform.INSTAGRAM_REELS)
        self.assertEqual(
            parsed.normalized_url,
            "https://www.instagram.com/reel/ABC123/",
        )

    def test_accepts_instagram_share_reel_links(self):
        parsed = self.URLParser.extract_and_validate(
            "https://www.instagram.com/share/reel/BA123456789/"
        )

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.platform, self.Platform.INSTAGRAM_REELS)

    def test_accepts_instagram_photo_posts(self):
        parsed = self.URLParser.extract_and_validate(
            "https://www.instagram.com/p/ABC123/"
        )

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.platform, self.Platform.INSTAGRAM_REELS)

    def test_accepts_instagram_reel_with_username_in_path(self):
        parsed = self.URLParser.extract_and_validate(
            "https://www.instagram.com/example.user/reel/ABC123/"
        )

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.platform, self.Platform.INSTAGRAM_REELS)

    def test_rejects_instagram_profile_links(self):
        parsed = self.URLParser.extract_and_validate(
            "https://www.instagram.com/example_user/"
        )

        self.assertIsNone(parsed)

    def test_accepts_vk_video(self):
        parsed = self.URLParser.extract_and_validate(
            "смотри https://vk.com/video-123456_789012?list=test"
        )

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.platform, self.Platform.VK)
        self.assertEqual(
            parsed.normalized_url,
            "https://vk.com/video-123456_789012?list=test",
        )

    def test_accepts_vk_video_embedded_in_section_url(self):
        parsed = self.URLParser.extract_and_validate(
            "https://vk.com/videos-77521"
            "?z=video-77521_162222515%2Fclub77521"
        )

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.platform, self.Platform.VK)

    def test_accepts_regular_youtube_video(self):
        parsed = self.URLParser.extract_and_validate(
            "https://www.youtube.com/watch?v=abcdefghijk&utm_source=test"
        )

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.platform, self.Platform.YOUTUBE_SHORTS)
        self.assertEqual(
            parsed.normalized_url,
            "https://www.youtube.com/watch?v=abcdefghijk",
        )

    def test_accepts_other_allowlisted_platform(self):
        parsed = self.URLParser.extract_and_validate(
            "https://x.com/example/status/1234567890?s=20"
        )

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.platform, self.Platform.OTHER)

    def test_rejects_arbitrary_hosts(self):
        parsed = self.URLParser.extract_and_validate(
            "https://example.com/video/123"
        )

        self.assertIsNone(parsed)

    def test_rejects_allowlisted_profile_pages(self):
        for url in (
            "https://x.com/example",
            "https://www.reddit.com/r/example/",
            "https://www.twitch.tv/example",
        ):
            with self.subTest(url=url):
                self.assertIsNone(
                    self.URLParser.extract_and_validate(url)
                )

    def test_skips_invalid_profile_before_valid_media_url(self):
        parsed = self.URLParser.extract_and_validate(
            "https://x.com/example "
            "https://x.com/example/status/1234567890"
        )

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.platform, self.Platform.OTHER)
