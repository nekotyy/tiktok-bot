"""Download videos, photos, and social-media albums."""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget

from bot.services.instagram_public import (
    InstagramPublicError,
    InstagramPublicExtractor,
)

try:
    from gallery_dl import config as gallery_config
    from gallery_dl.job import DataJob
except ImportError:
    gallery_config = None
    DataJob = None

logger = logging.getLogger(__name__)


class _YTDLPLogger:
    """Route yt-dlp output through the bot logger instead of stderr."""

    @staticmethod
    def debug(message: str) -> None:
        logger.debug("yt-dlp: %s", message)

    @staticmethod
    def warning(message: str) -> None:
        logger.warning("yt-dlp: %s", message)

    @staticmethod
    def error(message: str) -> None:
        logger.debug("yt-dlp error: %s", message)


class MediaDownloader:
    """Download media with yt-dlp and use gallery-dl for social photo posts."""

    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
    VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}
    AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".webm"}
    TEMPORARY_DOWNLOAD_SUFFIXES = (".part", ".ytdl", ".temp", ".tmp")

    # Prefer Telegram-compatible streams, but retain generic fallbacks. The last
    # two selectors are only used for sources that genuinely have no audio.
    VIDEO_FORMAT = (
        "bv*[ext=mp4][vcodec^=avc]+ba[ext=m4a]/"
        "bv*[ext=mp4]+ba[acodec!=none]/"
        "bv*+ba[acodec!=none]/"
        "b[ext=mp4][vcodec^=avc][acodec!=none]/"
        "b[ext=mp4][vcodec^=h264][acodec!=none]/"
        "b[ext=mp4][vcodec!=none][acodec!=none]/"
        "b[vcodec!=none][acodec!=none]/"
        "bv*[ext=mp4][vcodec!=none][acodec=none]/"
        "bv*[vcodec!=none][acodec=none]"
    )

    def __init__(
        self,
        downloads_path: str,
        max_file_size_bytes: int,
        proxy: Optional[str] = None,
        impersonate: Optional[str] = None,
    ):
        self.downloads_path = Path(downloads_path)
        self.max_file_size_bytes = max_file_size_bytes
        self.proxy = proxy or None
        self.impersonate = impersonate or None
        self.instagram = InstagramPublicExtractor(proxy=self.proxy)
        self._ensure_directory()
        self._configure_gallery_dl()

    def _ensure_directory(self) -> None:
        self.downloads_path.mkdir(parents=True, exist_ok=True)

    def _configure_gallery_dl(self) -> None:
        if gallery_config is None:
            return

        # Background music is deliberately disabled: photo posts must contain
        # photos only. "merged" gives direct Instagram videos with their audio.
        gallery_config.set(("extractor", "instagram"), "audio", False)
        gallery_config.set(("extractor", "instagram"), "videos", "merged")
        if self.proxy:
            gallery_config.set(("extractor",), "proxy", self.proxy)

    def _get_common_ydl_opts(self) -> Dict[str, Any]:
        opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "no_color": True,
            "noprogress": True,
            "logger": _YTDLPLogger(),
            "ignoreconfig": True,
            "extract_flat": False,
            "noplaylist": True,
            "playlist_items": "1",
            "socket_timeout": 30,
            "retries": 3,
            "fragment_retries": 3,
            "extractor_retries": 3,
            "file_access_retries": 3,
            # Deno is yt-dlp's default; Node is present in the Docker image and
            # serves as a fallback for YouTube's JavaScript challenges.
            "js_runtimes": {"deno": {}, "node": {}},
        }
        if self.proxy:
            opts["proxy"] = self.proxy
        if self.impersonate:
            opts["impersonate"] = ImpersonateTarget.from_str(self.impersonate)
        return opts

    def _get_video_ydl_opts(self, media_id: str) -> Dict[str, Any]:
        opts = self._get_common_ydl_opts()
        opts.update(
            {
                "format": self.VIDEO_FORMAT,
                "merge_output_format": "mp4",
                "outtmpl": str(self.downloads_path / f"{media_id}.%(ext)s"),
                "overwrites": True,
            }
        )
        return opts

    def _get_repair_audio_ydl_opts(
        self,
        output_prefix: str,
        format_selector: str,
    ) -> Dict[str, Any]:
        opts = self._get_common_ydl_opts()
        opts.update(
            {
                "format": format_selector,
                "outtmpl": str(
                    self.downloads_path / f"{output_prefix}.%(ext)s"
                ),
                "overwrites": True,
            }
        )
        return opts

    # ── Public async entry points ──────────────────────────────────

    async def download_media(self, platform: str, url: str) -> Dict[str, Any]:
        """Download a normalized supported URL without blocking the event loop."""
        media_id = str(uuid4())

        workers = {
            "tiktok": self._download_tiktok_sync,
            "youtube_shorts": self._download_youtube_sync,
            "instagram_reels": self._download_instagram_sync,
            "vk": self._download_vk_sync,
            "other": self._download_generic_sync,
        }
        worker = workers.get(platform)
        if worker is None:
            return {"success": False, "error": "Неподдерживаемая платформа"}

        try:
            return await asyncio.to_thread(worker, url, media_id)
        except Exception as error:
            logger.exception("Media download failed for %s", url)
            self._cleanup_matching_files(media_id)
            return {"success": False, "error": str(error)}

    async def get_video_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Get video info without downloading."""

        def _extract() -> Optional[Dict[str, Any]]:
            with yt_dlp.YoutubeDL(self._get_common_ydl_opts()) as ydl:
                return ydl.extract_info(url, download=False)

        try:
            info = await asyncio.to_thread(_extract)
            primary = self._primary_info(info)
            if not primary:
                return None
            return {
                "title": primary.get("title"),
                "duration": primary.get("duration"),
                "thumbnail": primary.get("thumbnail"),
                "uploader": primary.get("uploader"),
                "view_count": primary.get("view_count"),
            }
        except Exception as error:
            logger.error("Failed to get video info for %s: %s", url, error)
            return None

    # ── Platform pipelines ─────────────────────────────────────────

    def _download_tiktok_sync(self, url: str, media_id: str) -> Dict[str, Any]:
        resolved_url = self._resolve_tiktok_url(url)
        ytdlp_url = self._convert_photo_url_to_video_url(resolved_url)
        extraction_error: Optional[Exception] = None
        info: Dict[str, Any] = {}

        try:
            info = self._extract_info(ytdlp_url) or {}
            if self._has_video_formats(info):
                return self._download_video_sync(
                    ytdlp_url,
                    media_id,
                    title_fallback="TikTok Video",
                )
        except yt_dlp.utils.DownloadError as error:
            extraction_error = error

        gallery_media = self._collect_gallery_media(resolved_url)
        photo_urls = [
            item["url"] for item in gallery_media["items"]
            if item["kind"] == "photo"
        ]
        if not photo_urls and info:
            photo_urls = self._collect_photo_urls(info)
        if photo_urls:
            return self._download_photos_sync(
                info or gallery_media.get("metadata") or {},
                photo_urls,
                media_id,
                title_fallback="TikTok Photo Post",
            )

        if extraction_error:
            return self._format_download_error(extraction_error)
        return {
            "success": False,
            "error": "Не удалось найти видео или фото в этой публикации TikTok",
        }

    def _download_youtube_sync(self, url: str, media_id: str) -> Dict[str, Any]:
        result = self._download_video_sync(
            url,
            media_id,
            title_fallback="YouTube Video",
            error_formatter=self._format_youtube_error,
        )
        if result.get("success"):
            result["platform"] = "youtube_shorts"
        return result

    # Backwards-compatible method name used by earlier integrations.
    _download_youtube_shorts_sync = _download_youtube_sync

    def _download_instagram_sync(self, url: str, media_id: str) -> Dict[str, Any]:
        # Instagram's public embed endpoint exposes posts and Reels without an
        # account. Use it first so public media never depends on browser cookies.
        public_error: Optional[Exception] = None
        try:
            public_media = self.instagram.extract(url)
            result = self._download_gallery_album_sync(
                public_media,
                media_id,
                title_fallback="Instagram Post",
                instagram_public=True,
            )
            if result.get("success"):
                result["platform"] = "instagram_reels"
                return result
        except InstagramPublicError as error:
            public_error = error
            logger.warning(
                "Anonymous Instagram embed extraction failed for %s: %s",
                url,
                error,
            )

        path = urlparse(url).path.lower()
        video_first = bool(
            re.match(
                r"/(?:(?:[^/]+/)?(?:reel|reels|tv)|share/reel)/",
                path,
            )
        )
        result: Optional[Dict[str, Any]] = None

        if video_first:
            result = self._download_video_sync(
                url,
                media_id,
                title_fallback="Instagram Video",
                error_formatter=self._format_instagram_error,
            )
            if result.get("success"):
                result["platform"] = "instagram_reels"
                return result

        gallery_media = self._collect_gallery_media(url)
        if any(item["kind"] == "photo" for item in gallery_media["items"]):
            result = self._download_gallery_album_sync(
                gallery_media,
                media_id,
                title_fallback="Instagram Post",
            )
            if result.get("success"):
                result["platform"] = "instagram_reels"
                return result

        if result is None:
            result = self._download_video_sync(
                url,
                media_id,
                title_fallback="Instagram Video",
                error_formatter=self._format_instagram_error,
            )
            if result.get("success"):
                result["platform"] = "instagram_reels"
                return result

        # Some Instagram and Threads video posts are exposed by gallery-dl even
        # when yt-dlp's anonymous endpoint is temporarily blocked.
        if gallery_media["items"]:
            fallback = self._download_gallery_album_sync(
                gallery_media,
                media_id,
                title_fallback="Instagram Post",
            )
            if fallback.get("success"):
                fallback["platform"] = "instagram_reels"
                return fallback
        if result and result.get("success"):
            return result
        if public_error:
            return self._format_instagram_error(public_error)
        return result or {
            "success": False,
            "error": "Не удалось скачать публичную публикацию Instagram",
        }

    _download_instagram_reel_sync = _download_instagram_sync

    def _download_vk_sync(self, url: str, media_id: str) -> Dict[str, Any]:
        # VK video pages can look like photo pages to gallery-dl, so yt-dlp gets
        # the first attempt. gallery-dl remains a fallback for wall photo posts.
        result = self._download_video_sync(
            url,
            media_id,
            title_fallback="VK Video",
            error_formatter=self._format_vk_error,
        )
        if result.get("success"):
            result["platform"] = "vk"
            return result

        gallery_media = self._collect_gallery_media(url)
        if gallery_media["items"]:
            fallback = self._download_gallery_album_sync(
                gallery_media,
                media_id,
                title_fallback="VK Post",
            )
            if fallback.get("success"):
                fallback["platform"] = "vk"
                return fallback
        return result

    def _download_generic_sync(self, url: str, media_id: str) -> Dict[str, Any]:
        # Prefer galleries when there are real images; this handles X/Twitter,
        # Facebook, Reddit, Pinterest, Threads, and similar photo posts.
        gallery_media = self._collect_gallery_media(url)
        if any(item["kind"] == "photo" for item in gallery_media["items"]):
            result = self._download_gallery_album_sync(
                gallery_media,
                media_id,
                title_fallback="Social Media Post",
            )
            if result.get("success"):
                result["platform"] = "other"
                return result

        result = self._download_video_sync(
            url,
            media_id,
            title_fallback="Video",
        )
        if result.get("success"):
            result["platform"] = "other"
            return result

        if gallery_media["items"]:
            fallback = self._download_gallery_album_sync(
                gallery_media,
                media_id,
                title_fallback="Social Media Post",
            )
            if fallback.get("success"):
                fallback["platform"] = "other"
                return fallback
        return result

    # ── Video downloading and validation ───────────────────────────

    def _download_video_sync(
        self,
        url: str,
        media_id: str,
        title_fallback: str,
        error_formatter: Optional[Callable[[Exception], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        try:
            with yt_dlp.YoutubeDL(self._get_video_ydl_opts(media_id)) as ydl:
                info = ydl.extract_info(url, download=False)
                primary = self._primary_info(info)
                if not primary or not self._has_video_formats(info or {}):
                    return {
                        "success": False,
                        "error": "Эта ссылка не содержит поддерживаемого видео",
                    }

                estimated_size = self._estimate_filesize(primary)
                if estimated_size > self.max_file_size_bytes:
                    return self._file_too_large_error(
                        estimated_size,
                        label="Видео",
                    )

                ydl.download([url])

            file_path = self._find_downloaded_file(media_id, self.VIDEO_EXTENSIONS)
            if not file_path:
                return {
                    "success": False,
                    "error": "Файл не был создан после скачивания",
                }

            file_path = self._ensure_audio_and_telegram_compatibility(
                url=url,
                file_path=file_path,
                info=primary,
                media_id=media_id,
            )
            actual_size = os.path.getsize(file_path)
            if actual_size > self.max_file_size_bytes:
                self._cleanup_matching_files(media_id)
                return self._file_too_large_error(actual_size, label="Видео")

            self._cleanup_matching_files(media_id, keep={file_path})
            return {
                "success": True,
                "media_type": "video",
                "file_path": file_path,
                "file_size": actual_size,
                "duration": primary.get("duration"),
                "title": primary.get("title") or title_fallback,
                "thumbnail": primary.get("thumbnail"),
            }
        except yt_dlp.utils.DownloadError as error:
            self._cleanup_matching_files(media_id)
            formatter = error_formatter or self._format_download_error
            return formatter(error)
        except Exception as error:
            logger.exception("Unexpected video download error for %s", url)
            self._cleanup_matching_files(media_id)
            return {
                "success": False,
                "error": f"Ошибка обработки видео: {error}",
            }

    def _ensure_audio_and_telegram_compatibility(
        self,
        url: str,
        file_path: str,
        info: Dict[str, Any],
        media_id: str,
    ) -> str:
        probe = self._probe_media(file_path)
        if not self._stream(probe, "video"):
            raise RuntimeError("в скачанном файле отсутствует видеопоток")

        if not self._stream(probe, "audio") and self._has_audio_formats(info):
            logger.warning(
                "Downloaded file has no audio although the source advertises it; "
                "repairing %s",
                url,
            )
            file_path = self._repair_missing_audio(
                url=url,
                video_path=file_path,
                media_id=media_id,
            )
            probe = self._probe_media(file_path)
            if not self._stream(probe, "audio"):
                raise RuntimeError("не удалось добавить звуковую дорожку")

        return self._convert_for_telegram(file_path, probe, media_id)

    def _repair_missing_audio(
        self,
        url: str,
        video_path: str,
        media_id: str,
    ) -> str:
        audio_prefix = f"{media_id}_repair_audio"
        try:
            audio_path = self._download_valid_audio_candidate(
                url=url,
                audio_prefix=audio_prefix,
            )
            audio_probe = self._probe_media(audio_path)
            if not self._stream(audio_probe, "audio"):
                raise RuntimeError(
                    "скачанный файл для ремонта не содержит аудиопотока"
                )

            repaired_path = str(self.downloads_path / f"{media_id}_repaired.mp4")
            self._run_ffmpeg(
                [
                    "-i",
                    video_path,
                    "-i",
                    audio_path,
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    "-movflags",
                    "+faststart",
                    repaired_path,
                ]
            )
            if not Path(repaired_path).is_file():
                raise RuntimeError("ffmpeg не создал исправленное видео")

            self._cleanup_paths([video_path, audio_path])
            return repaired_path
        finally:
            for candidate in self.downloads_path.glob(f"{audio_prefix}*"):
                try:
                    if candidate.is_file():
                        candidate.unlink()
                except OSError:
                    pass

    def _download_valid_audio_candidate(
        self,
        url: str,
        audio_prefix: str,
    ) -> str:
        # Some extractors advertise an audio codec on a URL that actually
        # contains video only. Try a real audio-only format first, then a
        # progressive video+audio format, validating every file with ffprobe.
        selectors = (
            "ba[ext=m4a][acodec!=none]/ba[acodec!=none][vcodec=none]",
            (
                "b[ext=mp4][vcodec^=avc][acodec!=none]/"
                "b[ext=mp4][vcodec^=h264][acodec!=none]"
            ),
            "b[format_id=download][acodec!=none]",
            "b[acodec!=none][vcodec!=none]",
        )
        errors: List[str] = []

        for attempt, selector in enumerate(selectors, start=1):
            output_prefix = f"{audio_prefix}_{attempt}"
            try:
                with yt_dlp.YoutubeDL(
                    self._get_repair_audio_ydl_opts(
                        output_prefix,
                        selector,
                    )
                ) as ydl:
                    ydl.download([url])

                audio_path = self._find_downloaded_file(
                    output_prefix,
                    self.AUDIO_EXTENSIONS | self.VIDEO_EXTENSIONS,
                )
                if not audio_path:
                    errors.append(f"попытка {attempt}: файл не создан")
                    continue

                probe = self._probe_media(audio_path)
                if self._stream(probe, "audio"):
                    return audio_path

                errors.append(f"попытка {attempt}: аудиопоток отсутствует")
                self._cleanup_paths([audio_path])
            except Exception as error:
                errors.append(f"попытка {attempt}: {error}")
                self._cleanup_matching_files(output_prefix)

        details = "; ".join(errors)
        raise RuntimeError(
            "не удалось получить настоящую аудиодорожку"
            + (f" ({details})" if details else "")
        )

    def _convert_for_telegram(
        self,
        file_path: str,
        probe: Dict[str, Any],
        media_id: str,
    ) -> str:
        video_stream = self._stream(probe, "video") or {}
        audio_stream = self._stream(probe, "audio")
        video_codec = video_stream.get("codec_name")
        pixel_format = video_stream.get("pix_fmt")
        audio_codec = audio_stream.get("codec_name") if audio_stream else None

        compatible_video = (
            video_codec == "h264"
            and pixel_format in (None, "yuv420p", "yuvj420p")
        )
        compatible_audio = audio_stream is None or audio_codec == "aac"
        already_mp4 = Path(file_path).suffix.lower() == ".mp4"
        if compatible_video and compatible_audio and already_mp4:
            return file_path

        output_path = str(self.downloads_path / f"{media_id}_telegram.mp4")
        command = ["-i", file_path, "-map", "0:v:0"]
        if audio_stream:
            command.extend(["-map", "0:a:0"])

        if compatible_video:
            command.extend(["-c:v", "copy"])
        else:
            command.extend(
                [
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "23",
                    "-pix_fmt",
                    "yuv420p",
                ]
            )

        if audio_stream:
            if compatible_audio:
                command.extend(["-c:a", "copy"])
            else:
                command.extend(["-c:a", "aac", "-b:a", "192k"])
        else:
            command.append("-an")

        command.extend(["-movflags", "+faststart", output_path])
        self._run_ffmpeg(command)
        if not Path(output_path).is_file():
            raise RuntimeError("ffmpeg не создал совместимый MP4")

        converted_probe = self._probe_media(output_path)
        if not self._stream(converted_probe, "video"):
            raise RuntimeError("после конвертации отсутствует видеопоток")
        if audio_stream and not self._stream(converted_probe, "audio"):
            raise RuntimeError("после конвертации пропала звуковая дорожка")

        self._cleanup_paths([file_path])
        return output_path

    def _probe_media(self, file_path: str) -> Dict[str, Any]:
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            raise RuntimeError(
                "ffprobe не установлен; он нужен для проверки звуковой дорожки"
            )

        process = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type,codec_name,pix_fmt:format=format_name,duration",
                "-of",
                "json",
                file_path,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        if process.returncode != 0:
            detail = process.stderr.strip()[-800:]
            raise RuntimeError(f"ffprobe не смог проверить медиа: {detail}")
        try:
            return json.loads(process.stdout or "{}")
        except json.JSONDecodeError as error:
            raise RuntimeError("ffprobe вернул некорректный результат") from error

    @staticmethod
    def _stream(probe: Dict[str, Any], stream_type: str) -> Optional[Dict[str, Any]]:
        return next(
            (
                stream
                for stream in probe.get("streams") or []
                if stream.get("codec_type") == stream_type
            ),
            None,
        )

    @staticmethod
    def _run_ffmpeg(arguments: List[str]) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError(
                "ffmpeg не установлен; он нужен для объединения видео и звука"
            )

        process = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            check=False,
        )
        if process.returncode != 0:
            detail = process.stderr.strip()[-1200:]
            raise RuntimeError(f"ffmpeg завершился с ошибкой: {detail}")

    # ── gallery-dl and album helpers ───────────────────────────────

    def _collect_gallery_media(self, url: str) -> Dict[str, Any]:
        result: Dict[str, Any] = {"items": [], "metadata": {}}
        if DataJob is None:
            return result

        try:
            job = DataJob(url, file=None)
            job.run()
            if getattr(job, "exception", None):
                logger.warning(
                    "gallery-dl extraction failed for %s: %s",
                    url,
                    job.exception,
                )
        except Exception as error:
            logger.warning("gallery-dl extraction failed for %s: %s", url, error)
            return result

        seen = set()
        for index, media_url in enumerate(job.data_urls):
            if not media_url or media_url in seen:
                continue
            metadata = job.data_meta[index] if index < len(job.data_meta) else {}
            kind = self._gallery_media_kind(media_url, metadata)
            # Audio is intentionally ignored for every photo/album platform.
            if kind not in {"photo", "video"}:
                continue
            result["items"].append(
                {"kind": kind, "url": media_url, "metadata": metadata}
            )
            seen.add(media_url)
            if not result["metadata"]:
                result["metadata"] = metadata
        return result

    def _gallery_media_kind(
        self,
        media_url: str,
        metadata: Dict[str, Any],
    ) -> Optional[str]:
        media_type = str(metadata.get("type") or "").lower()
        extension = str(metadata.get("extension") or "").lower()
        if extension and not extension.startswith("."):
            extension = f".{extension}"
        if not extension:
            clean_url = media_url.removeprefix("ytdl:")
            extension = Path(urlparse(clean_url).path).suffix.lower()

        if media_type == "audio":
            return None
        if media_type in {"video", "animated"}:
            return "video"
        if media_type in {"image", "photo"}:
            return "photo"
        if extension in self.VIDEO_EXTENSIONS:
            return "video"
        if extension in self.AUDIO_EXTENSIONS:
            return None
        if extension in self.IMAGE_EXTENSIONS:
            return "photo"
        return None

    def _download_gallery_album_sync(
        self,
        gallery_media: Dict[str, Any],
        media_id: str,
        title_fallback: str,
        instagram_public: bool = False,
    ) -> Dict[str, Any]:
        file_paths: List[str] = []
        total_size = 0
        metadata = gallery_media.get("metadata") or {}

        try:
            for index, item in enumerate(gallery_media.get("items") or [], start=1):
                item_id = f"{media_id}_{index:03d}"
                if item["kind"] == "photo":
                    if instagram_public:
                        file_path = self.instagram.download_to_path(
                            item["url"],
                            str(self.downloads_path / f"{item_id}.jpg"),
                            self.max_file_size_bytes,
                        )
                    else:
                        file_path = self._download_photo_file(
                            item["url"],
                            item_id,
                            1,
                        )
                else:
                    if instagram_public:
                        raw_path = self.instagram.download_to_path(
                            item["url"],
                            str(self.downloads_path / f"{item_id}.mp4"),
                            self.max_file_size_bytes,
                        )
                        probe = self._probe_media(raw_path)
                        if not self._stream(probe, "video"):
                            raise RuntimeError(
                                "Instagram CDN вернул файл без видеопотока"
                            )
                        file_path = self._convert_for_telegram(
                            raw_path,
                            probe,
                            item_id,
                        )
                    else:
                        video_result = self._download_video_sync(
                            item["url"].removeprefix("ytdl:"),
                            f"{item_id}_video",
                            title_fallback=title_fallback,
                        )
                        file_path = (
                            video_result.get("file_path")
                            if video_result.get("success")
                            else None
                        )
                        if not file_path:
                            logger.warning(
                                "Skipping gallery video that could not be "
                                "downloaded: %s",
                                video_result.get("error"),
                            )

                if not file_path:
                    continue
                file_size = os.path.getsize(file_path)
                if file_size > self.max_file_size_bytes:
                    self._cleanup_paths(file_paths + [file_path])
                    return self._file_too_large_error(file_size)
                total_size += file_size
                file_paths.append(file_path)

            if not file_paths:
                return {
                    "success": False,
                    "error": "Не удалось скачать файлы из публикации",
                }

            media_type = (
                "photo"
                if all(self._is_image_path(path) for path in file_paths)
                else "album"
            )
            return {
                "success": True,
                "media_type": media_type,
                "file_paths": file_paths,
                "file_size": total_size,
                "duration": metadata.get("duration"),
                "title": metadata.get("title") or metadata.get("description")
                or title_fallback,
                "photo_count": sum(
                    1 for path in file_paths if self._is_image_path(path)
                ),
            }
        except Exception as error:
            logger.exception("Gallery download failed")
            self._cleanup_paths(file_paths)
            self._cleanup_matching_files(media_id)
            return {
                "success": False,
                "error": f"Не удалось скачать публикацию: {error}",
            }

    def _download_photos_sync(
        self,
        info: Dict[str, Any],
        photo_urls: List[str],
        media_id: str,
        title_fallback: str = "Photo Post",
    ) -> Dict[str, Any]:
        file_paths: List[str] = []
        total_size = 0
        try:
            for index, photo_url in enumerate(photo_urls, start=1):
                file_path = self._download_photo_file(photo_url, media_id, index)
                if not file_path:
                    continue
                file_size = os.path.getsize(file_path)
                if file_size > self.max_file_size_bytes:
                    self._cleanup_paths(file_paths + [file_path])
                    return self._file_too_large_error(file_size)
                total_size += file_size
                file_paths.append(file_path)

            if not file_paths:
                return {
                    "success": False,
                    "error": "Не удалось скачать изображения из публикации",
                }
            return {
                "success": True,
                "media_type": "photo",
                "file_paths": file_paths,
                "file_size": total_size,
                "duration": info.get("duration"),
                "title": info.get("title") or title_fallback,
                "photo_count": len(file_paths),
            }
        except Exception as error:
            logger.exception("Photo download failed")
            self._cleanup_paths(file_paths)
            self._cleanup_matching_files(media_id)
            return {
                "success": False,
                "error": f"Не удалось скачать фото: {error}",
            }

    def _download_photo_file(
        self,
        url: str,
        media_id: str,
        index: int,
    ) -> Optional[str]:
        request = Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/136.0.0.0 Safari/537.36"
                ),
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            },
        )
        with urlopen(request, timeout=30) as response:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > self.max_file_size_bytes:
                raise RuntimeError("изображение превышает допустимый размер")

            extension = self._guess_extension(
                url,
                response.headers.get_content_type(),
            )
            file_path = self.downloads_path / f"{media_id}_{index}{extension}"
            written = 0
            with open(file_path, "wb") as output_file:
                while chunk := response.read(1024 * 1024):
                    written += len(chunk)
                    if written > self.max_file_size_bytes:
                        output_file.close()
                        file_path.unlink(missing_ok=True)
                        raise RuntimeError("изображение превышает допустимый размер")
                    output_file.write(chunk)
            return str(file_path) if written else None

    # Backwards-compatible helper now intentionally returns no audio.
    def _collect_tiktok_media_with_gallery_dl(self, url: str) -> Dict[str, Any]:
        media = self._collect_gallery_media(url)
        return {
            "photo_urls": [
                item["url"] for item in media["items"]
                if item["kind"] == "photo"
            ],
            "audio_url": None,
            "audio_title": None,
            "audio_duration": None,
        }

    def _collect_photo_urls_with_gallery_dl(self, url: str) -> List[str]:
        return self._collect_tiktok_media_with_gallery_dl(url)["photo_urls"]

    # ── Extraction and file helpers ────────────────────────────────

    def _extract_info(self, url: str) -> Optional[Dict[str, Any]]:
        with yt_dlp.YoutubeDL(self._get_common_ydl_opts()) as ydl:
            return ydl.extract_info(url, download=False)

    @classmethod
    def _primary_info(
        cls,
        info: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not info:
            return None
        entries = info.get("entries")
        if entries:
            for entry in entries:
                primary = cls._primary_info(entry)
                if primary:
                    return primary
        return info

    @classmethod
    def _iter_info(cls, info: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
        yield info
        for entry in info.get("entries") or []:
            if entry:
                yield from cls._iter_info(entry)

    def _has_video_formats(self, info: Dict[str, Any]) -> bool:
        for entry in self._iter_info(info):
            if entry.get("vcodec") not in (None, "none"):
                return True
            for media_format in entry.get("formats") or []:
                if media_format.get("vcodec") not in (None, "none"):
                    return True
            extension = str(entry.get("ext") or "").lower()
            if extension in {
                item.lstrip(".") for item in self.VIDEO_EXTENSIONS
            }:
                return True
        return False

    def _has_audio_formats(self, info: Dict[str, Any]) -> bool:
        for entry in self._iter_info(info):
            if entry.get("acodec") not in (None, "none"):
                return True
            for media_format in (
                (entry.get("requested_formats") or [])
                + (entry.get("formats") or [])
            ):
                if media_format.get("acodec") not in (None, "none"):
                    return True
        return False

    def _collect_photo_urls(self, info: Dict[str, Any]) -> List[str]:
        urls: List[str] = []
        seen = set()
        for entry in self._iter_info(info):
            thumbnail = entry.get("thumbnail")
            if thumbnail and thumbnail not in seen:
                urls.append(thumbnail)
                seen.add(thumbnail)
            thumbnails = sorted(
                entry.get("thumbnails") or [],
                key=lambda item: item.get("preference", 0),
                reverse=True,
            )
            for item in thumbnails:
                image_url = item.get("url")
                if image_url and image_url not in seen:
                    urls.append(image_url)
                    seen.add(image_url)
        return urls

    def _estimate_filesize(self, info: Dict[str, Any]) -> int:
        requested_formats = info.get("requested_formats") or []
        requested_size = sum(
            media_format.get("filesize")
            or media_format.get("filesize_approx")
            or 0
            for media_format in requested_formats
        )
        if requested_size:
            return requested_size
        return info.get("filesize") or info.get("filesize_approx") or 0

    def _find_downloaded_file(
        self,
        media_id: str,
        extensions: set[str],
    ) -> Optional[str]:
        candidates = []
        for file_path in self.downloads_path.glob(f"{media_id}*"):
            if not file_path.is_file():
                continue
            if file_path.name.endswith(self.TEMPORARY_DOWNLOAD_SUFFIXES):
                continue
            if file_path.suffix.lower() not in extensions:
                continue
            candidates.append(file_path)
        if not candidates:
            return None
        return str(max(candidates, key=lambda path: path.stat().st_mtime))

    def _guess_extension(self, url: str, content_type: Optional[str]) -> str:
        extension = Path(urlparse(url).path).suffix.lower()
        if extension in self.IMAGE_EXTENSIONS:
            return extension
        guessed = mimetypes.guess_extension(content_type or "")
        if guessed in self.IMAGE_EXTENSIONS:
            return guessed
        return ".jpg"

    def _guess_audio_extension(
        self,
        url: str,
        content_type: Optional[str],
    ) -> str:
        """Retained for compatibility with callers from older releases."""
        extension = Path(urlparse(url).path).suffix.lower()
        if extension in self.AUDIO_EXTENSIONS:
            return extension
        guessed = mimetypes.guess_extension(content_type or "")
        if guessed in self.AUDIO_EXTENSIONS:
            return guessed
        if content_type in {"audio/mp4", "video/mp4"}:
            return ".m4a"
        return ".mp3"

    def _resolve_tiktok_url(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            hostname = (parsed.netloc or "").lower()
            is_short = (
                hostname in {"vm.tiktok.com", "vt.tiktok.com"}
                or (
                    hostname == "www.tiktok.com"
                    and parsed.path.startswith("/t/")
                )
            )
            if not is_short:
                return url
            request = Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/136.0.0.0 Safari/537.36"
                    ),
                },
            )
            with urlopen(request, timeout=15) as response:
                return response.geturl() or url
        except Exception as error:
            logger.warning("Failed to resolve short TikTok URL %s: %s", url, error)
            return url

    @staticmethod
    def _convert_photo_url_to_video_url(url: str) -> str:
        return re.sub(r"/photo/(\d+)", r"/video/\1", url)

    def _cleanup_matching_files(
        self,
        media_id: str,
        keep: Optional[set[str]] = None,
    ) -> None:
        keep_resolved = {
            str(Path(path).resolve()) for path in (keep or set())
        }
        for file_path in self.downloads_path.glob(f"{media_id}*"):
            try:
                if (
                    file_path.is_file()
                    and str(file_path.resolve()) not in keep_resolved
                ):
                    file_path.unlink()
            except OSError:
                pass

    @staticmethod
    def _cleanup_paths(file_paths: List[str]) -> None:
        for file_path in file_paths:
            try:
                Path(file_path).unlink(missing_ok=True)
            except OSError:
                pass

    def _is_image_path(self, file_path: str) -> bool:
        return Path(file_path).suffix.lower() in self.IMAGE_EXTENSIONS

    # ── Error formatters ───────────────────────────────────────────

    def _file_too_large_error(
        self,
        size_bytes: int,
        label: str = "Файл",
    ) -> Dict[str, Any]:
        size_mb = size_bytes / (1024 * 1024)
        max_mb = self.max_file_size_bytes / (1024 * 1024)
        return {
            "success": False,
            "error": (
                f"{label} слишком большой ({size_mb:.1f} МБ). "
                f"Максимум: {max_mb:.0f} МБ"
            ),
        }

    def _format_download_error(self, error: Exception) -> Dict[str, Any]:
        error_msg = str(error).lower()
        if "unsupported url" in error_msg:
            return {
                "success": False,
                "error": "Загрузчик пока не поддерживает эту ссылку",
            }
        if "unavailable" in error_msg or "not available" in error_msg:
            return {
                "success": False,
                "error": "Публикация недоступна или была удалена",
            }
        if "private" in error_msg:
            return {
                "success": False,
                "error": "Публикация приватная или аккаунт закрыт",
            }
        if "login required" in error_msg or "not logged in" in error_msg:
            return {
                "success": False,
                "error": (
                    "Эта публикация не доступна анонимно или является приватной."
                ),
            }
        if any(
            marker in error_msg
            for marker in (
                "sign in to confirm",
                "not a bot",
                "--cookies",
                "use cookies",
            )
        ):
            return {
                "success": False,
                "error": (
                    "Площадка отклонила запрос с IP сервера. "
                    "Попробуйте позже или настройте YTDLP_PROXY."
                ),
            }
        if "blocked from accessing this post" in error_msg:
            return {
                "success": False,
                "error": "Площадка временно ограничила доступ с текущего IP",
            }
        return {"success": False, "error": f"Ошибка загрузки: {error}"}

    def _format_youtube_error(self, error: Exception) -> Dict[str, Any]:
        error_msg = str(error).lower()
        if "private" in error_msg:
            return {"success": False, "error": "Видео приватное"}
        if "members-only" in error_msg or "member" in error_msg:
            return {
                "success": False,
                "error": "Видео доступно только участникам канала",
            }
        return self._format_download_error(error)

    def _format_instagram_error(self, error: Exception) -> Dict[str, Any]:
        error_msg = str(error).lower()
        if any(
            marker in error_msg
            for marker in (
                "login required",
                "not logged in",
                "login page",
                "empty media response",
                "authentication",
                "перенаправил публичную embed-страницу на вход",
            )
        ):
            return {
                "success": False,
                "error": (
                    "Instagram не отдал эту публикацию через публичный доступ. "
                    "Возможно, она приватная, удалена или ограничена по возрасту."
                ),
            }
        if "private" in error_msg:
            return {
                "success": False,
                "error": "Публикация из приватного аккаунта",
            }
        return self._format_download_error(error)

    def _format_vk_error(self, error: Exception) -> Dict[str, Any]:
        error_msg = str(error).lower()
        if "login" in error_msg or "cookies" in error_msg:
            return {
                "success": False,
                "error": (
                    "Эта публикация VK не доступна анонимно или является приватной."
                ),
            }
        return self._format_download_error(error)


# Backwards compatibility alias
TikTokDownloader = MediaDownloader
