"""Anonymous extraction of public Instagram posts from embed pages."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from curl_cffi import requests


class InstagramPublicError(RuntimeError):
    """Raised when Instagram does not expose a post anonymously."""


class InstagramPublicExtractor:
    """Extract public posts and Reels without login data or exported cookies."""

    SHORTCODE_PATTERN = re.compile(
        r"/(?:reel|reels|p|tv)/([A-Za-z0-9_-]+)",
        re.IGNORECASE,
    )
    CONTEXT_JSON_PATTERN = re.compile(
        r'"contextJSON":"((?:\\.|[^"\\])*)"',
    )
    MOBILE_USER_AGENT = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
        "Mobile/15E148 Safari/604.1"
    )

    def __init__(self, proxy: Optional[str] = None, timeout: int = 30):
        self.proxy = proxy or None
        self.timeout = timeout

    def extract(self, post_url: str) -> Dict[str, Any]:
        """Return ordered photo/video URLs from a public post or Reel."""
        shortcode = self._shortcode(post_url)
        if not shortcode:
            raise InstagramPublicError(
                "ссылка не содержит публичный пост или Reel"
            )

        embed_url = (
            f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
        )
        request_options: Dict[str, Any] = {
            "headers": {
                "User-Agent": self.MOBILE_USER_AGENT,
                "Accept": (
                    "text/html,application/xhtml+xml,"
                    "application/xml;q=0.9,*/*;q=0.8"
                ),
                "Accept-Language": "en-US,en;q=0.5",
                "Referer": "https://www.instagram.com/",
            },
            "impersonate": "safari_ios",
            "timeout": self.timeout,
            "allow_redirects": True,
        }
        if self.proxy:
            request_options["proxy"] = self.proxy

        try:
            response = requests.get(embed_url, **request_options)
        except Exception as error:
            raise InstagramPublicError(
                f"не удалось открыть публичную embed-страницу: {error}"
            ) from error

        if response.status_code != 200:
            raise InstagramPublicError(
                f"публичная embed-страница вернула HTTP {response.status_code}"
            )
        if "accounts/login" in str(response.url).lower():
            raise InstagramPublicError(
                "Instagram перенаправил публичную embed-страницу на вход"
            )

        media = self._media_from_html(response.text)
        items = self._media_items(media)
        if not items:
            raise InstagramPublicError(
                "Instagram не вернул медиа для этой публичной публикации"
            )

        caption_edges = (
            media.get("edge_media_to_caption", {}).get("edges") or []
        )
        caption = ""
        if caption_edges:
            caption = str(caption_edges[0].get("node", {}).get("text") or "")
        owner = str(media.get("owner", {}).get("username") or "")
        title = caption or (f"Instagram — @{owner}" if owner else "Instagram")

        return {
            "items": items,
            "metadata": {
                "title": title,
                "description": caption,
                "uploader": owner,
                "shortcode": shortcode,
            },
        }

    def download_to_path(
        self,
        media_url: str,
        output_path: str,
        max_size_bytes: int,
    ) -> str:
        """Download an extracted CDN URL with Instagram-compatible headers."""
        request_options: Dict[str, Any] = {
            "headers": {
                "User-Agent": self.MOBILE_USER_AGENT,
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.5",
                "Referer": "https://www.instagram.com/",
            },
            "impersonate": "safari_ios",
            "timeout": self.timeout,
            "allow_redirects": True,
            "stream": True,
        }
        if self.proxy:
            request_options["proxy"] = self.proxy

        try:
            response = requests.get(media_url, **request_options)
        except Exception as error:
            raise InstagramPublicError(
                f"не удалось скачать медиа из Instagram CDN: {error}"
            ) from error

        if response.status_code not in {200, 206}:
            raise InstagramPublicError(
                f"Instagram CDN вернул HTTP {response.status_code}"
            )

        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > max_size_bytes:
            raise InstagramPublicError(
                "медиа из Instagram превышает допустимый размер"
            )

        destination = Path(output_path)
        written = 0
        try:
            with destination.open("wb") as output_file:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    written += len(chunk)
                    if written > max_size_bytes:
                        raise InstagramPublicError(
                            "медиа из Instagram превышает допустимый размер"
                        )
                    output_file.write(chunk)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        finally:
            response.close()

        if not written:
            destination.unlink(missing_ok=True)
            raise InstagramPublicError("Instagram CDN вернул пустой файл")
        return str(destination)

    @classmethod
    def _shortcode(cls, post_url: str) -> Optional[str]:
        path = urlparse(post_url).path
        match = cls.SHORTCODE_PATTERN.search(path)
        return match.group(1)[:64] if match else None

    @classmethod
    def _media_from_html(cls, html: str) -> Dict[str, Any]:
        match = cls.CONTEXT_JSON_PATTERN.search(html)
        if not match:
            raise InstagramPublicError(
                "в публичной embed-странице отсутствуют данные публикации"
            )

        try:
            # contextJSON is a JSON string nested inside another JSON document.
            context_json = json.loads(f'"{match.group(1)}"')
            context = json.loads(context_json)
            media = context["gql_data"]["shortcode_media"]
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise InstagramPublicError(
                "Instagram вернул неизвестный формат embed-страницы"
            ) from error

        if not isinstance(media, dict):
            raise InstagramPublicError(
                "Instagram не вернул описание публикации"
            )
        return media

    @classmethod
    def _media_items(cls, media: Dict[str, Any]) -> List[Dict[str, Any]]:
        sidecar = (
            media.get("edge_sidecar_to_children", {}).get("edges") or []
        )
        nodes = [
            edge.get("node") or {}
            for edge in sidecar
            if isinstance(edge, dict)
        ] or [media]

        items: List[Dict[str, Any]] = []
        seen = set()
        for node in nodes:
            is_video = bool(node.get("is_video"))
            media_url = (
                node.get("video_url") if is_video else node.get("display_url")
            )
            if not media_url or media_url in seen:
                continue
            if is_video and not node.get("video_url"):
                continue

            items.append(
                {
                    "kind": "video" if is_video else "photo",
                    "url": str(media_url),
                    "metadata": {
                        "id": node.get("id"),
                        "shortcode": node.get("shortcode"),
                        "thumbnail": node.get("display_url"),
                    },
                }
            )
            seen.add(media_url)
        return items
