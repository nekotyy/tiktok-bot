import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bot.services.instagram_public import (
    InstagramPublicError,
    InstagramPublicExtractor,
)


class InstagramPublicExtractorTests(unittest.TestCase):
    def test_extracts_shortcode_from_public_post_and_reel(self):
        self.assertEqual(
            InstagramPublicExtractor._shortcode(
                "https://www.instagram.com/reel/AbC_123-xYz/?utm_source=test"
            ),
            "AbC_123-xYz",
        )
        self.assertEqual(
            InstagramPublicExtractor._shortcode(
                "https://instagram.com/p/Post-Code_1/"
            ),
            "Post-Code_1",
        )

    def test_rejects_profile_url(self):
        self.assertIsNone(
            InstagramPublicExtractor._shortcode(
                "https://www.instagram.com/public_user/"
            )
        )

    def test_parses_ordered_mixed_carousel_from_context_json(self):
        context = {
            "gql_data": {
                "shortcode_media": {
                    "__typename": "GraphSidecar",
                    "edge_sidecar_to_children": {
                        "edges": [
                            {
                                "node": {
                                    "id": "photo",
                                    "shortcode": "photo-code",
                                    "is_video": False,
                                    "display_url": "https://cdn.example/photo.jpg?a=1&b=2",
                                }
                            },
                            {
                                "node": {
                                    "id": "video",
                                    "shortcode": "video-code",
                                    "is_video": True,
                                    "display_url": "https://cdn.example/poster.jpg",
                                    "video_url": "https://cdn.example/video.mp4?a=1&b=2",
                                }
                            },
                        ]
                    },
                }
            }
        }
        context_json = json.dumps(context, separators=(",", ":"))
        html = f'<script>{{"contextJSON":{json.dumps(context_json)}}}</script>'

        media = InstagramPublicExtractor._media_from_html(html)
        items = InstagramPublicExtractor._media_items(media)

        self.assertEqual(
            [(item["kind"], item["url"]) for item in items],
            [
                ("photo", "https://cdn.example/photo.jpg?a=1&b=2"),
                ("video", "https://cdn.example/video.mp4?a=1&b=2"),
            ],
        )

    def test_unknown_embed_format_has_clear_error(self):
        with self.assertRaises(InstagramPublicError):
            InstagramPublicExtractor._media_from_html("<html></html>")

    def test_public_request_does_not_send_login_cookies(self):
        context = {
            "gql_data": {
                "shortcode_media": {
                    "is_video": False,
                    "display_url": "https://cdn.example/photo.jpg",
                    "owner": {"username": "public_user"},
                }
            }
        }
        context_json = json.dumps(context, separators=(",", ":"))
        html = f'<script>{{"contextJSON":{json.dumps(context_json)}}}</script>'
        response = SimpleNamespace(
            status_code=200,
            url="https://www.instagram.com/p/Public123/embed/captioned/",
            text=html,
        )

        with patch(
            "bot.services.instagram_public.requests.get",
            return_value=response,
        ) as request:
            result = InstagramPublicExtractor().extract(
                "https://www.instagram.com/p/Public123/"
            )

        self.assertEqual(result["items"][0]["kind"], "photo")
        request_options = request.call_args.kwargs
        self.assertNotIn("cookies", request_options)
        self.assertNotIn("cookie", request_options["headers"])
        self.assertEqual(request_options["impersonate"], "safari_ios")
