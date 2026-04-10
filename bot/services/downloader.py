"""Media downloader for TikTok and YouTube Shorts."""

import logging
import mimetypes
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

import asyncio
import yt_dlp

try:
    from gallery_dl.job import DataJob
except ImportError:
    DataJob = None

from ..config import Config

logger = logging.getLogger(__name__)


class MediaDownloader:
    """Downloads media from TikTok and YouTube Shorts."""

    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
    VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}

    def __init__(self, downloads_path: str, max_file_size_bytes: int):
        self.downloads_path = Path(downloads_path)
        self.max_file_size_bytes = max_file_size_bytes
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        self.downloads_path.mkdir(parents=True, exist_ok=True)

    def _get_common_ydl_opts(self) -> Dict[str, Any]:
        return {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'nocheckcertificate': True,
            'no_color': True,
            'socket_timeout': 30,
            'http_headers': {
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/120.0.0.0 Safari/537.36'
                ),
            },
        }

    def _get_video_ydl_opts(self, output_path: str) -> Dict[str, Any]:
        opts = self._get_common_ydl_opts()
        opts.update({
            'format': 'best[ext=mp4]/best',
            'outtmpl': output_path,
        })
        return opts

    # ── Public async entry points ──────────────────────────────────

    async def download_media(self, platform: str, url: str) -> Dict[str, Any]:
        """Download media from the given platform.

        Args:
            platform: "tiktok" or "youtube_shorts"
            url: Normalized URL

        Returns:
            Result dict with success, media_type, file_path(s), etc.
        """
        media_id = str(uuid4())

        try:
            loop = asyncio.get_event_loop()
            if platform == "tiktok":
                return await loop.run_in_executor(
                    None, self._download_tiktok_sync, url, media_id
                )
            elif platform == "youtube_shorts":
                return await loop.run_in_executor(
                    None, self._download_youtube_shorts_sync, url, media_id
                )
            else:
                return {'success': False, 'error': 'Неподдерживаемая платформа'}
        except Exception as e:
            logger.error(f"Media download failed for {url}: {e}")
            self._cleanup_matching_files(media_id)
            return {'success': False, 'error': str(e)}

    async def get_video_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Get video info without downloading."""
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
            }

            def _extract():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=False)

            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, _extract)

            if info:
                return {
                    'title': info.get('title'),
                    'duration': info.get('duration'),
                    'thumbnail': info.get('thumbnail'),
                    'uploader': info.get('uploader'),
                    'view_count': info.get('view_count'),
                }
            return None
        except Exception as e:
            logger.error(f"Failed to get video info for {url}: {e}")
            return None

    # ── TikTok download pipeline ────────────────────────────────────

    def _download_tiktok_sync(self, url: str, media_id: str) -> Dict[str, Any]:
        try:
            resolved_url = self._resolve_tiktok_url(url)
            ytdlp_url = self._convert_photo_url_to_video_url(resolved_url)
            info = self._extract_info(ytdlp_url)

            if not info:
                return {
                    'success': False,
                    'error': 'Не удалось получить информацию о публикации',
                }

            if self._has_video_formats(info):
                output_path = str(self.downloads_path / f"{media_id}.mp4")
                result = self._download_video_sync(ytdlp_url, output_path)
                if result.get('success'):
                    result['media_type'] = 'video'
                return result

            photo_urls = self._collect_photo_urls_with_gallery_dl(resolved_url)
            if not photo_urls:
                photo_urls = self._collect_photo_urls(info)
            if photo_urls:
                return self._download_photos_sync(info, photo_urls, media_id)

            return {
                'success': False,
                'error': 'Не удалось найти видео или фото в этой публикации TikTok',
            }
        except yt_dlp.utils.DownloadError as e:
            return self._format_download_error(e)
        except Exception as e:
            logger.error(f"Unexpected TikTok download error: {e}")
            self._cleanup_matching_files(media_id)
            return {'success': False, 'error': f'Неожиданная ошибка: {str(e)}'}

    def _download_video_sync(self, url: str, output_path: str) -> Dict[str, Any]:
        ydl_opts = self._get_video_ydl_opts(output_path)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                if not info:
                    return {
                        'success': False,
                        'error': 'Не удалось получить информацию о видео',
                    }

                if not self._has_video_formats(info):
                    return {
                        'success': False,
                        'error': 'Эта ссылка содержит не видео, а фото-пост. Отправьте её боту напрямую.',
                    }

                filesize = info.get('filesize') or info.get('filesize_approx', 0)
                if filesize > self.max_file_size_bytes:
                    size_mb = filesize / (1024 * 1024)
                    max_mb = self.max_file_size_bytes / (1024 * 1024)
                    return {
                        'success': False,
                        'error': f'Видео слишком большое ({size_mb:.1f} МБ). Максимум: {max_mb:.0f} МБ',
                    }

                ydl.download([url])

                if not os.path.exists(output_path):
                    return {
                        'success': False,
                        'error': 'Файл не был создан после скачивания',
                    }

                actual_size = os.path.getsize(output_path)
                if actual_size > self.max_file_size_bytes:
                    os.remove(output_path)
                    size_mb = actual_size / (1024 * 1024)
                    max_mb = self.max_file_size_bytes / (1024 * 1024)
                    return {
                        'success': False,
                        'error': f'Видео слишком большое ({size_mb:.1f} МБ). Максимум: {max_mb:.0f} МБ',
                    }

                return {
                    'success': True,
                    'media_type': 'video',
                    'file_path': output_path,
                    'file_size': actual_size,
                    'duration': info.get('duration'),
                    'title': info.get('title', 'TikTok Video'),
                    'thumbnail': info.get('thumbnail'),
                }

        except yt_dlp.utils.DownloadError as e:
            return self._format_download_error(e)
        except Exception as e:
            logger.error(f"Unexpected video download error: {e}")
            return {'success': False, 'error': f'Неожиданная ошибка: {str(e)}'}

    # ── YouTube Shorts download pipeline ────────────────────────────

    def _download_youtube_shorts_sync(
        self, url: str, media_id: str
    ) -> Dict[str, Any]:
        output_path = str(self.downloads_path / f"{media_id}.mp4")

        try:
            with yt_dlp.YoutubeDL(self._get_video_ydl_opts(output_path)) as ydl:
                info = ydl.extract_info(url, download=False)

                if not info:
                    return {
                        'success': False,
                        'error': 'Не удалось получить информацию о видео',
                    }

                # URL validation already done in url_parser — trust the /shorts/ path.
                # No duration check: YouTube allows >60s videos on /shorts/ URLs.

                # File size check
                filesize = info.get('filesize') or info.get('filesize_approx', 0)
                if filesize > self.max_file_size_bytes:
                    size_mb = filesize / (1024 * 1024)
                    max_mb = self.max_file_size_bytes / (1024 * 1024)
                    return {
                        'success': False,
                        'error': f'Видео слишком большое ({size_mb:.1f} МБ). Максимум: {max_mb:.0f} МБ',
                    }

                # Download
                ydl.download([url])

                if not os.path.exists(output_path):
                    return {
                        'success': False,
                        'error': 'Файл не был создан после скачивания',
                    }

                actual_size = os.path.getsize(output_path)
                if actual_size > self.max_file_size_bytes:
                    os.remove(output_path)
                    size_mb = actual_size / (1024 * 1024)
                    max_mb = self.max_file_size_bytes / (1024 * 1024)
                    return {
                        'success': False,
                        'error': f'Видео слишком большое ({size_mb:.1f} МБ). Максимум: {max_mb:.0f} МБ',
                    }

                return {
                    'success': True,
                    'media_type': 'video',
                    'file_path': output_path,
                    'file_size': actual_size,
                    'duration': info.get('duration'),
                    'title': info.get('title', 'YouTube Short'),
                    'thumbnail': info.get('thumbnail'),
                    'platform': 'youtube_shorts',
                }

        except yt_dlp.utils.DownloadError as e:
            return self._format_youtube_error(e)
        except Exception as e:
            logger.error(f"Unexpected YouTube Shorts download error: {e}")
            self._cleanup_matching_files(media_id)
            return {'success': False, 'error': f'Неожиданная ошибка: {str(e)}'}

    # ── TikTok helpers ──────────────────────────────────────────────

    def _extract_info(self, url: str) -> Optional[Dict[str, Any]]:
        with yt_dlp.YoutubeDL(self._get_common_ydl_opts()) as ydl:
            return ydl.extract_info(url, download=False)

    def _resolve_tiktok_url(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            hostname = (parsed.netloc or '').lower()

            # Short URLs that need redirect resolution
            is_short = (
                hostname in {'vm.tiktok.com', 'vt.tiktok.com'}
                or (hostname == 'www.tiktok.com' and parsed.path.startswith('/t/'))
            )
            if not is_short:
                return url

            request = Request(
                url,
                headers={
                    'User-Agent': (
                        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                        'AppleWebKit/537.36 (KHTML, like Gecko) '
                        'Chrome/120.0.0.0 Safari/537.36'
                    ),
                },
            )
            with urlopen(request, timeout=15) as response:
                return response.geturl() or url
        except Exception as e:
            logger.warning(f"Failed to resolve short TikTok URL {url}: {e}")
            return url

    def _convert_photo_url_to_video_url(self, url: str) -> str:
        return re.sub(r'/photo/(\d+)', r'/video/\1', url)

    def _has_video_formats(self, info: Dict[str, Any]) -> bool:
        formats = info.get('formats') or []
        for fmt in formats:
            if fmt.get('vcodec') not in (None, 'none'):
                return True

        ext = (info.get('ext') or '').lower()
        return ext in {item.lstrip('.') for item in self.VIDEO_EXTENSIONS}

    def _collect_photo_urls(self, info: Dict[str, Any]) -> List[str]:
        urls: List[str] = []
        seen = set()

        thumbnail = info.get('thumbnail')
        if thumbnail and thumbnail not in seen:
            urls.append(thumbnail)
            seen.add(thumbnail)

        thumbnails = sorted(
            info.get('thumbnails') or [],
            key=lambda item: item.get('preference', 0),
            reverse=True,
        )

        for item in thumbnails:
            image_url = item.get('url')
            if not image_url or image_url in seen:
                continue
            urls.append(image_url)
            seen.add(image_url)

        return urls

    def _collect_photo_urls_with_gallery_dl(self, url: str) -> List[str]:
        if DataJob is None:
            return []

        try:
            job = DataJob(url, file=None)
            job.run()
        except Exception as e:
            logger.warning(f"gallery-dl extraction failed for {url}: {e}")
            return []

        urls: List[str] = []
        seen = set()

        for index, media_url in enumerate(job.data_urls):
            if not media_url or media_url in seen:
                continue

            meta = job.data_meta[index] if index < len(job.data_meta) else {}
            extension = str(meta.get('extension') or '').lower().lstrip('.')
            if extension not in {'jpg', 'jpeg', 'png', 'webp'}:
                continue

            urls.append(media_url)
            seen.add(media_url)

        return urls

    def _download_photos_sync(
        self,
        info: Dict[str, Any],
        photo_urls: List[str],
        media_id: str,
    ) -> Dict[str, Any]:
        file_paths: List[str] = []
        total_size = 0

        try:
            for index, photo_url in enumerate(photo_urls[:10], start=1):
                file_path = self._download_photo_file(photo_url, media_id, index)
                if not file_path:
                    continue

                file_size = os.path.getsize(file_path)
                total_size += file_size

                if total_size > self.max_file_size_bytes:
                    self._cleanup_paths(file_paths + [file_path])
                    return self._file_too_large_error(total_size)

                file_paths.append(file_path)

            if not file_paths:
                return {
                    'success': False,
                    'error': 'Не удалось скачать изображения из этой публикации',
                }

            return {
                'success': True,
                'media_type': 'photo',
                'file_paths': file_paths,
                'file_size': total_size,
                'duration': None,
                'title': info.get('title', 'TikTok Photo Post'),
                'photo_count': len(file_paths),
            }
        except Exception as e:
            logger.error(f"Photo download failed: {e}")
            self._cleanup_paths(file_paths)
            self._cleanup_matching_files(media_id)
            return {'success': False, 'error': f'Не удалось скачать фото: {str(e)}'}

    def _download_photo_file(
        self, url: str, media_id: str, index: int
    ) -> Optional[str]:
        request = Request(
            url,
            headers={
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/120.0.0.0 Safari/537.36'
                ),
            },
        )

        with urlopen(request, timeout=30) as response:
            content = response.read()
            if not content:
                return None

            ext = self._guess_extension(url, response.headers.get_content_type())
            file_path = self.downloads_path / f"{media_id}_{index}{ext}"
            with open(file_path, 'wb') as output_file:
                output_file.write(content)
            return str(file_path)

    def _guess_extension(self, url: str, content_type: Optional[str]) -> str:
        ext = Path(urlparse(url).path).suffix.lower()
        if ext in self.IMAGE_EXTENSIONS:
            return ext

        guessed = mimetypes.guess_extension(content_type or '')
        if guessed in self.IMAGE_EXTENSIONS:
            return guessed

        return '.jpg'

    # ── Cleanup helpers ─────────────────────────────────────────────

    def _cleanup_matching_files(self, media_id: str) -> None:
        for file_path in self.downloads_path.glob(f"{media_id}*"):
            try:
                if file_path.is_file():
                    file_path.unlink()
            except Exception:
                pass

    def _cleanup_paths(self, file_paths: List[str]) -> None:
        for file_path in file_paths:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                pass

    # ── Error formatters ────────────────────────────────────────────

    def _file_too_large_error(self, size_bytes: int) -> Dict[str, Any]:
        size_mb = size_bytes / (1024 * 1024)
        max_mb = self.max_file_size_bytes / (1024 * 1024)
        return {
            'success': False,
            'error': f'Файл слишком большой ({size_mb:.1f} МБ). Максимум: {max_mb:.0f} МБ',
        }

    def _format_download_error(self, error: Exception) -> Dict[str, Any]:
        error_msg = str(error).lower()

        if 'unavailable' in error_msg:
            return {'success': False, 'error': 'Публикация недоступна или была удалена'}
        if 'private' in error_msg:
            return {'success': False, 'error': 'Публикация приватная или аккаунт закрыт'}
        if 'blocked from accessing this post' in error_msg:
            return {
                'success': False,
                'error': 'TikTok временно ограничил доступ к этой публикации с текущего IP',
            }

        return {'success': False, 'error': f'Ошибка загрузки: {str(error)}'}

    def _format_youtube_error(self, error: Exception) -> Dict[str, Any]:
        error_msg = str(error).lower()

        if 'unavailable' in error_msg or 'not available' in error_msg:
            return {'success': False, 'error': 'Видео недоступно или было удалено'}
        if 'private' in error_msg:
            return {'success': False, 'error': 'Видео приватное'}
        if 'members-only' in error_msg or 'member' in error_msg:
            return {'success': False, 'error': 'Это видео доступно только участникам канала'}

        return {'success': False, 'error': f'Ошибка загрузки: {str(error)}'}


# Backwards compatibility alias
TikTokDownloader = MediaDownloader
