"""Extract, validate, and normalize supported social-media URLs."""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


class Platform(Enum):
    """Downloader pipelines exposed to handlers."""

    TIKTOK = "tiktok"
    YOUTUBE_SHORTS = "youtube_shorts"
    INSTAGRAM_REELS = "instagram_reels"
    VK = "vk"
    OTHER = "other"


class ParsedURL:
    """Result of URL parsing."""

    def __init__(self, platform: Platform, original_url: str, normalized_url: str):
        self.platform = platform
        self.original_url = original_url
        self.normalized_url = normalized_url

    def __repr__(self) -> str:
        return f"ParsedURL(platform={self.platform.value}, url={self.normalized_url})"


class URLParser:
    """Parser for individual posts and videos on supported public platforms."""

    URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

    TIKTOK_DOMAINS = {
        "tiktok.com",
        "www.tiktok.com",
        "m.tiktok.com",
        "vm.tiktok.com",
        "vt.tiktok.com",
    }
    YOUTUBE_DOMAINS = {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
    }
    INSTAGRAM_DOMAINS = {
        "instagram.com",
        "www.instagram.com",
    }
    VK_DOMAINS = {
        "vk.com",
        "m.vk.com",
        "vk.ru",
        "m.vk.ru",
        "vkvideo.ru",
        "www.vkvideo.ru",
    }

    # These hosts have established yt-dlp and/or gallery-dl extractors. Keeping
    # an allow-list prevents the bot from becoming an arbitrary URL fetcher.
    OTHER_DOMAINS = {
        "x.com",
        "twitter.com",
        "mobile.twitter.com",
        "facebook.com",
        "www.facebook.com",
        "m.facebook.com",
        "fb.watch",
        "threads.net",
        "www.threads.net",
        "reddit.com",
        "www.reddit.com",
        "old.reddit.com",
        "redd.it",
        "pinterest.com",
        "www.pinterest.com",
        "pin.it",
        "rutube.ru",
        "www.rutube.ru",
        "ok.ru",
        "m.ok.ru",
        "twitch.tv",
        "www.twitch.tv",
        "clips.twitch.tv",
        "vimeo.com",
        "www.vimeo.com",
        "dailymotion.com",
        "www.dailymotion.com",
        "dai.ly",
        "likee.video",
        "l.likee.video",
        "coub.com",
        "streamable.com",
        "snapchat.com",
        "www.snapchat.com",
        "tumblr.com",
        "www.tumblr.com",
    }

    TRACKING_QUERY_KEYS = {
        "fbclid",
        "gclid",
        "igsh",
        "igshid",
        "si",
        "share_id",
        "utm_campaign",
        "utm_content",
        "utm_medium",
        "utm_source",
        "utm_term",
    }

    @staticmethod
    def _hostname(url: str) -> str:
        try:
            return (urlparse(url).hostname or "").lower().rstrip(".")
        except ValueError:
            return ""

    @staticmethod
    def _host_matches(hostname: str, domains: set[str]) -> bool:
        return any(
            hostname == domain or hostname.endswith(f".{domain}")
            for domain in domains
        )

    @classmethod
    def detect_platform(cls, url: str) -> Optional[Platform]:
        """Return the pipeline associated with a supported hostname."""
        hostname = cls._hostname(url)
        if cls._host_matches(hostname, cls.TIKTOK_DOMAINS):
            return Platform.TIKTOK
        if cls._host_matches(hostname, cls.YOUTUBE_DOMAINS):
            return Platform.YOUTUBE_SHORTS
        if cls._host_matches(hostname, cls.INSTAGRAM_DOMAINS):
            return Platform.INSTAGRAM_REELS
        if cls._host_matches(hostname, cls.VK_DOMAINS):
            return Platform.VK
        if cls._host_matches(hostname, cls.OTHER_DOMAINS):
            return Platform.OTHER
        return None

    @classmethod
    def extract_url(cls, text: str) -> Optional[str]:
        """Extract the first URL whose hostname is explicitly supported."""
        if not text:
            return None
        for match in cls.URL_PATTERN.finditer(text):
            url = match.group(0).rstrip(".,;:!?)]}>»”’")
            if cls.detect_platform(url):
                return url
        return None

    @classmethod
    def _valid_http_url(cls, url: str, domains: set[str]) -> bool:
        try:
            parsed = urlparse(url)
            port = parsed.port
        except ValueError:
            return False
        return (
            parsed.scheme.lower() in {"http", "https"}
            and parsed.username is None
            and parsed.password is None
            and port in {None, 80, 443}
            and cls._host_matches((parsed.hostname or "").lower(), domains)
            and bool(parsed.path and parsed.path != "/")
        )

    @classmethod
    def is_valid_tiktok_url(cls, url: str) -> bool:
        """Accept individual TikTok posts and official short links."""
        if not cls._valid_http_url(url, cls.TIKTOK_DOMAINS):
            return False
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        path = parsed.path.strip("/")
        if hostname in {"vm.tiktok.com", "vt.tiktok.com"}:
            return bool(path)
        return bool(
            re.search(r"(?:^|/)(?:video|photo)/\d+", path, re.IGNORECASE)
            or re.match(r"(?:t|v|embed)/", path, re.IGNORECASE)
        )

    @classmethod
    def is_valid_youtube_url(cls, url: str) -> bool:
        """Accept a single YouTube video, Short, clip, or live URL."""
        if not cls._valid_http_url(url, cls.YOUTUBE_DOMAINS):
            return False
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        path = parsed.path.strip("/")
        if hostname == "youtu.be":
            return bool(path.split("/")[0])
        if path == "watch":
            return bool(parse_qs(parsed.query).get("v", [""])[0])
        return bool(
            re.match(r"(?:shorts|live|embed|clip)/[^/]+", path, re.IGNORECASE)
        )

    @classmethod
    def is_valid_youtube_shorts_url(cls, url: str) -> bool:
        """Backwards-compatible name; regular single-video links are supported."""
        return cls.is_valid_youtube_url(url)

    @classmethod
    def is_valid_instagram_url(cls, url: str) -> bool:
        """Accept Reels, video/photo posts, shares, and individual stories."""
        if not cls._valid_http_url(url, cls.INSTAGRAM_DOMAINS):
            return False
        path = urlparse(url).path.lower().strip("/")
        return bool(
            re.match(
                r"(?:[^/]+/)?(?:p|reel|reels|tv)/[^/]+",
                path,
            )
            or re.match(r"share/(?:p|reel)/[^/]+", path)
            or re.match(r"stories/[^/]+/[^/]+", path)
        )

    @classmethod
    def is_valid_instagram_reels_url(cls, url: str) -> bool:
        """Backwards-compatible name for all individual Instagram media."""
        return cls.is_valid_instagram_url(url)

    @classmethod
    def is_valid_vk_url(cls, url: str) -> bool:
        """Accept VK media and wall post URLs, but not profiles or feeds."""
        if not cls._valid_http_url(url, cls.VK_DOMAINS):
            return False
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        query = parse_qs(parsed.query)
        if path == "video_ext.php":
            return bool(parsed.query)
        if re.match(r"videos-?\d+$", path, re.IGNORECASE):
            embedded = query.get("z", [""])[0]
            return bool(
                re.match(r"(?:video|clip)-?\d+_\d+", embedded)
            )
        return bool(
            re.match(
                r"(?:video|clip|wall)-?\d+_\d+",
                path,
                re.IGNORECASE,
            )
            or re.match(
                r"@[^/]+/(?:clip|video)-?\d+_\d+",
                path,
                re.IGNORECASE,
            )
        )

    @classmethod
    def is_valid_other_url(cls, url: str) -> bool:
        """Validate an individual-looking URL on the generic allow-list."""
        if not cls._valid_http_url(url, cls.OTHER_DOMAINS):
            return False

        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        path = parsed.path.strip("/")
        query = parse_qs(parsed.query)

        if hostname.endswith(("x.com", "twitter.com")):
            return bool(re.match(r"[^/]+/status/\d+", path))
        if hostname == "fb.watch":
            return bool(path)
        if hostname.endswith("facebook.com"):
            return bool(
                re.match(r"reel/[^/]+", path)
                or re.match(r"share/(?:r|v)/[^/]+", path)
                or re.match(r"[^/]+/(?:videos|posts)/[^/]+", path)
                or (path == "watch" and query.get("v"))
            )
        if hostname.endswith("threads.net"):
            return bool(re.match(r"@[^/]+/post/[^/]+", path))
        if hostname in {"redd.it"}:
            return bool(path)
        if hostname.endswith("reddit.com"):
            return bool(re.match(r"r/[^/]+/comments/[^/]+", path))
        if hostname == "pin.it":
            return bool(path)
        if hostname.endswith("pinterest.com"):
            return bool(re.match(r"pin/\d+", path))
        if hostname.endswith("rutube.ru"):
            return bool(re.match(r"(?:video|shorts)/[^/]+", path))
        if hostname.endswith("ok.ru"):
            return bool(re.match(r"(?:video|videoembed)/\d+", path))
        if hostname == "clips.twitch.tv":
            return bool(path)
        if hostname.endswith("twitch.tv"):
            return bool(
                re.match(r"videos/\d+", path)
                or re.match(r"[^/]+/clip/[^/]+", path)
            )
        if hostname.endswith("vimeo.com"):
            return bool(
                re.match(r"\d+(?:$|/)", path)
                or re.match(r"(?:channels|showcase)/[^/]+/(?:video/)?\d+", path)
            )
        if hostname == "dai.ly":
            return bool(path)
        if hostname.endswith("dailymotion.com"):
            return bool(re.match(r"video/[^/]+", path))
        if hostname.endswith("likee.video"):
            return bool(path)
        if hostname.endswith("coub.com"):
            return bool(re.match(r"view/[^/]+", path))
        if hostname.endswith("streamable.com"):
            return bool(path)
        if hostname.endswith("snapchat.com"):
            return bool(re.match(r"spotlight/[^/]+", path))
        if hostname.endswith("tumblr.com"):
            return bool(re.search(r"(?:^|/)\d{5,}(?:/|$)", path))
        return False

    @classmethod
    def normalize_url(cls, url: str) -> str:
        """Remove common tracking parameters while preserving media identifiers."""
        if not url:
            return url
        try:
            parsed = urlparse(url)
        except ValueError:
            return url

        hostname = (parsed.hostname or "").lower()
        scheme = "https"
        path = parsed.path
        query = parse_qs(parsed.query, keep_blank_values=True)

        if cls._host_matches(hostname, cls.INSTAGRAM_DOMAINS):
            if path and not path.endswith("/"):
                path = f"{path}/"
            return urlunparse((scheme, "www.instagram.com", path, "", "", ""))

        if hostname == "youtu.be":
            return urlunparse((scheme, hostname, path, "", "", ""))

        if cls._host_matches(hostname, cls.YOUTUBE_DOMAINS):
            if path.lower() == "/watch":
                video_id = query.get("v", [""])[0]
                return f"https://www.youtube.com/watch?v={video_id}"
            if path.lower().startswith("/shorts/"):
                video_id = path.split("/")[2]
                return f"https://www.youtube.com/shorts/{video_id}"

        filtered_query = {
            key: values
            for key, values in query.items()
            if key.lower() not in cls.TRACKING_QUERY_KEYS
            and not key.lower().startswith("utm_")
        }
        normalized_query = urlencode(filtered_query, doseq=True)
        return urlunparse(
            (
                scheme,
                parsed.netloc.lower(),
                path,
                "",
                normalized_query,
                "",
            )
        )

    @classmethod
    def extract_and_validate(cls, text: str) -> Optional[ParsedURL]:
        """Extract, validate, and normalize one supported URL from text."""
        validators = {
            Platform.TIKTOK: cls.is_valid_tiktok_url,
            Platform.YOUTUBE_SHORTS: cls.is_valid_youtube_url,
            Platform.INSTAGRAM_REELS: cls.is_valid_instagram_url,
            Platform.VK: cls.is_valid_vk_url,
            Platform.OTHER: cls.is_valid_other_url,
        }
        if not text:
            return None
        for match in cls.URL_PATTERN.finditer(text):
            url = match.group(0).rstrip(".,;:!?)]}>»”’")
            platform = cls.detect_platform(url)
            if platform and validators[platform](url):
                return ParsedURL(
                    platform=platform,
                    original_url=url,
                    normalized_url=cls.normalize_url(url),
                )
        return None
