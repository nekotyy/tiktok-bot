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

    def test_rejects_non_reel_instagram_links(self):
        parsed = self.URLParser.extract_and_validate(
            "https://www.instagram.com/p/ABC123/"
        )

        self.assertIsNone(parsed)
