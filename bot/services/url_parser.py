"""URL parsing and validation for TikTok and YouTube Shorts links."""

import re
from enum import Enum
from typing import Optional
from urllib.parse import urlparse


class Platform(Enum):
    """Supported platforms."""
    TIKTOK = "tiktok"
    YOUTUBE_SHORTS = "youtube_shorts"


class ParsedURL:
    """Result of URL parsing."""

    def __init__(self, platform: Platform, original_url: str, normalized_url: str):
        self.platform = platform
        self.original_url = original_url
        self.normalized_url = normalized_url

    def __repr__(self) -> str:
        return f"ParsedURL(platform={self.platform.value}, url={self.normalized_url})"


class URLParser:
    """Parser for TikTok and YouTube Shorts URLs."""

    # TikTok URL patterns
    TIKTOK_PATTERN = r'https?://(?:www\.|m\.|vm\.|vt\.)?tiktok\.com/[^\s]+'

    # YouTube Shorts patterns
    YOUTUBE_SHORTS_PATTERN = r'https?://(?:www\.)?youtube\.com/shorts/[^\s]+'
    YOUTUBE_SHORT_URL_PATTERN = r'https?://youtu\.be/[^\s]+'

    # Supported TikTok domains
    TIKTOK_DOMAINS = [
        'tiktok.com',
        'www.tiktok.com',
        'm.tiktok.com',
        'vm.tiktok.com',
        'vt.tiktok.com',
    ]

    # Supported YouTube domains
    YOUTUBE_DOMAINS = [
        'youtube.com',
        'www.youtube.com',
        'youtu.be',
    ]

    @classmethod
    def detect_platform(cls, url: str) -> Optional[Platform]:
        """Detect which platform a URL belongs to.

        Args:
            url: URL to check

        Returns:
            Platform enum or None
        """
        if not url:
            return None

        url_lower = url.lower()

        if re.search(r'tiktok\.com', url_lower):
            return Platform.TIKTOK

        if '/shorts/' in url_lower or 'youtu.be' in url_lower:
            return Platform.YOUTUBE_SHORTS

        return None

    @classmethod
    def extract_url(cls, text: str) -> Optional[str]:
        """Extract the first TikTok or YouTube Shorts URL from text.

        Args:
            text: Text that may contain a URL

        Returns:
            URL if found, None otherwise
        """
        if not text:
            return None

        combined_pattern = (
            f'({cls.YOUTUBE_SHORTS_PATTERN}|'
            f'{cls.YOUTUBE_SHORT_URL_PATTERN}|'
            f'{cls.TIKTOK_PATTERN})'
        )

        match = re.search(combined_pattern, text, re.IGNORECASE)
        if match:
            url = match.group(0)
            url = url.rstrip('.,;:!?)]}>')
            return url

        return None

    @classmethod
    def is_valid_tiktok_url(cls, url: str) -> bool:
        """Check if URL is a valid TikTok URL."""
        if not url:
            return False

        try:
            parsed = urlparse(url)
            if parsed.scheme not in ('http', 'https'):
                return False

            domain = parsed.netloc.lower()
            if not any(domain == d or domain.endswith('.' + d) for d in cls.TIKTOK_DOMAINS):
                return False

            if not parsed.path or parsed.path == '/':
                return False

            return True
        except Exception:
            return False

    @classmethod
    def is_valid_youtube_shorts_url(cls, url: str) -> bool:
        """Check if URL is a valid YouTube Shorts URL.

        Only accepts /shorts/ URLs and short youtu.be links.
        Regular youtube.com/watch URLs are rejected.
        """
        if not url:
            return False

        try:
            parsed = urlparse(url)
            if parsed.scheme not in ('http', 'https'):
                return False

            domain = parsed.netloc.lower()

            if 'youtu.be' in domain:
                return bool(parsed.path.strip('/'))

            if '/shorts/' in parsed.path.lower():
                video_id = parsed.path.split('/shorts/')[-1].split('/')[0].split('?')[0]
                return len(video_id) >= 10

            return False
        except Exception:
            return False

    @classmethod
    def normalize_url(cls, url: str) -> str:
        """Normalize URL by stripping unnecessary query parameters."""
        if not url:
            return url

        try:
            parsed = urlparse(url)

            # Short links: keep only scheme + netloc + path
            if parsed.netloc in ('vm.tiktok.com', 'vt.tiktok.com', 'youtu.be'):
                return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

            # TikTok: keep full path, drop tracking params
            if 'tiktok.com' in parsed.netloc.lower():
                return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

            # YouTube Shorts: keep only the video ID
            if '/shorts/' in parsed.path.lower():
                parts = parsed.path.split('/shorts/')
                if len(parts) >= 2:
                    video_id = parts[1].split('/')[0].split('?')[0]
                    return f"https://www.youtube.com/shorts/{video_id}"

            return url
        except Exception:
            return url

    @classmethod
    def extract_and_validate(cls, text: str) -> Optional[ParsedURL]:
        """Extract URL from text, detect platform, validate and normalize.

        Args:
            text: Text that may contain a URL

        Returns:
            ParsedURL object or None
        """
        url = cls.extract_url(text)
        if not url:
            return None

        platform = cls.detect_platform(url)
        if not platform:
            return None

        if platform == Platform.TIKTOK:
            if not cls.is_valid_tiktok_url(url):
                return None
        elif platform == Platform.YOUTUBE_SHORTS:
            if not cls.is_valid_youtube_shorts_url(url):
                return None

        normalized = cls.normalize_url(url)
        return ParsedURL(platform=platform, original_url=url, normalized_url=normalized)
