"""Media downloader for TikTok, YouTube Shorts, and Instagram Reels."""

import logging
import mimetypes
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
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
    """Downloads media from TikTok, YouTube Shorts, and Instagram Reels."""

    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
    VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}
    AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav"}
    TEMPORARY_DOWNLOAD_SUFFIXES = (".part", ".ytdl", ".temp", ".tmp")

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
            'retries': 3,
            'fragment_retries': 3,
            'extractor_retries': 3,
            'file_access_retries': 3,
            'http_headers': {
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/120.0.0.0 Safari/537.36'
                ),
            },
        }

    def _get_video_ydl_opts(self, media_id: str) -> Dict[str, Any]:
        opts = self._get_common_ydl_opts()
        opts.update({
            'format': (
                'bv*[vcodec!=none]+ba[acodec!=none]/'
                'b[vcodec!=none][acodec!=none]/'
                'best[vcodec!=none]'
            ),
            'merge_output_format': 'mp4',
            'outtmpl': str(self.downloads_path / f"{media_id}.%(ext)s"),
        })
        return opts

    def _get_audio_ydl_opts(self, media_id: str) -> Dict[str, Any]:
        opts = self._get_common_ydl_opts()
        opts.update({
            'format': 'ba[ext=m4a]/ba[ext=mp3]/ba[acodec!=none]/bestaudio/best',
            'outtmpl': str(self.downloads_path / f"{media_id}_audio.%(ext)s"),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
        return opts

    # ── Public async entry points ──────────────────────────────────

    async def download_media(self, platform: str, url: str) -> Dict[str, Any]:
        """Download media from the given platform.

        Args:
            platform: "tiktok", "youtube_shorts", or "instagram_reels"
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
            elif platform == "instagram_reels":
                return await loop.run_in_executor(
                    None, self._download_instagram_reel_sync, url, media_id
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
                result = self._download_video_sync(
                    ytdlp_url,
                    media_id,
                    title_fallback='TikTok Video',
                )
                if result.get('success'):
                    result['media_type'] = 'video'
                return result

            gallery_media = self._collect_tiktok_media_with_gallery_dl(resolved_url)
            photo_urls = gallery_media.get('photo_urls') or []
            if not photo_urls:
                photo_urls = self._collect_photo_urls(info)
            audio_source = gallery_media.get('audio_url') or self._collect_audio_url(info)
            if photo_urls:
                return self._download_photos_sync(
                    info,
                    photo_urls,
                    media_id,
                    audio_source=audio_source,
                )

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

    def _download_video_sync(
        self,
        url: str,
        media_id: str,
        title_fallback: str,
        error_formatter: Optional[Callable[[Exception], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        ydl_opts = self._get_video_ydl_opts(media_id)

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

                filesize = self._estimate_filesize(info)
                if filesize > self.max_file_size_bytes:
                    return self._file_too_large_error(filesize, label='Видео')

                ydl.download([url])

                file_path = self._find_downloaded_file(media_id, self.VIDEO_EXTENSIONS)
                if not file_path:
                    return {
                        'success': False,
                        'error': 'Файл не был создан после скачивания',
                    }

                actual_size = os.path.getsize(file_path)
                if actual_size > self.max_file_size_bytes:
                    os.remove(file_path)
                    return self._file_too_large_error(actual_size, label='Видео')

                return {
                    'success': True,
                    'media_type': 'video',
                    'file_path': file_path,
                    'file_size': actual_size,
                    'duration': info.get('duration'),
                    'title': info.get('title', title_fallback),
                    'thumbnail': info.get('thumbnail'),
                }

        except yt_dlp.utils.DownloadError as e:
            formatter = error_formatter or self._format_download_error
            return formatter(e)
        except Exception as e:
            logger.error(f"Unexpected video download error: {e}")
            return {'success': False, 'error': f'Неожиданная ошибка: {str(e)}'}

    # ── YouTube Shorts download pipeline ────────────────────────────

    def _download_youtube_shorts_sync(
        self, url: str, media_id: str
    ) -> Dict[str, Any]:
        try:
            result = self._download_video_sync(
                url,
                media_id,
                title_fallback='YouTube Short',
                error_formatter=self._format_youtube_error,
            )
            if result.get('success'):
                result['platform'] = 'youtube_shorts'
            return result
        except yt_dlp.utils.DownloadError as e:
            return self._format_youtube_error(e)
        except Exception as e:
            logger.error(f"Unexpected YouTube Shorts download error: {e}")
            self._cleanup_matching_files(media_id)
            return {'success': False, 'error': f'Неожиданная ошибка: {str(e)}'}

    # ── Instagram Reels download pipeline ───────────────────────────

    def _download_instagram_reel_sync(
        self, url: str, media_id: str
    ) -> Dict[str, Any]:
        try:
            result = self._download_video_sync(
                url,
                media_id,
                title_fallback='Instagram Reel',
                error_formatter=self._format_instagram_error,
            )
            if result.get('success'):
                result['platform'] = 'instagram_reels'
            return result
        except yt_dlp.utils.DownloadError as e:
            return self._format_instagram_error(e)
        except Exception as e:
            logger.error(f"Unexpected Instagram Reels download error: {e}")
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

    def _collect_tiktok_media_with_gallery_dl(self, url: str) -> Dict[str, Any]:
        if DataJob is None:
            return {}

        try:
            job = DataJob(url, file=None)
            job.run()
        except Exception as e:
            logger.warning(f"gallery-dl extraction failed for {url}: {e}")
            return {}

        photo_urls: List[str] = []
        seen = set()
        audio_url: Optional[str] = None
        audio_title: Optional[str] = None
        audio_duration: Optional[int] = None

        for index, media_url in enumerate(job.data_urls):
            if not media_url or media_url in seen:
                continue

            meta = job.data_meta[index] if index < len(job.data_meta) else {}
            media_type = str(meta.get('type') or '').lower()
            extension = str(meta.get('extension') or '').lower().lstrip('.')

            if media_type == 'audio' or extension in {'mp3', 'm4a', 'aac', 'ogg', 'opus', 'wav'}:
                if not audio_url:
                    audio_url = media_url
                    audio_title = meta.get('title')
                    audio_duration = meta.get('duration')
                seen.add(media_url)
                continue

            if extension not in {'jpg', 'jpeg', 'png', 'webp'}:
                continue

            photo_urls.append(media_url)
            seen.add(media_url)

        return {
            'photo_urls': photo_urls,
            'audio_url': audio_url,
            'audio_title': audio_title,
            'audio_duration': audio_duration,
        }

    def _collect_photo_urls_with_gallery_dl(self, url: str) -> List[str]:
        return self._collect_tiktok_media_with_gallery_dl(url).get('photo_urls', [])

    def _collect_audio_url(self, info: Dict[str, Any]) -> Optional[str]:
        formats = info.get('formats') or []
        for fmt in formats:
            audio_url = fmt.get('url')
            if not audio_url:
                continue
            if fmt.get('acodec') in (None, 'none'):
                continue
            if fmt.get('vcodec') not in (None, 'none'):
                continue
            return audio_url
        return None

    def _download_photos_sync(
        self,
        info: Dict[str, Any],
        photo_urls: List[str],
        media_id: str,
        audio_source: Optional[str] = None,
    ) -> Dict[str, Any]:
        file_paths: List[str] = []
        audio_path: Optional[str] = None
        total_size = 0

        try:
            for index, photo_url in enumerate(photo_urls, start=1):
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

            if audio_source:
                try:
                    audio_path = self._download_audio_source(audio_source, media_id)
                    if audio_path:
                        audio_size = os.path.getsize(audio_path)
                        total_size += audio_size
                        if total_size > self.max_file_size_bytes:
                            self._cleanup_paths(file_paths + [audio_path])
                            return self._file_too_large_error(total_size)
                except Exception as e:
                    logger.warning(f"TikTok photo audio download failed: {e}")
                    audio_path = None

            return {
                'success': True,
                'media_type': 'photo',
                'file_paths': file_paths,
                'audio_path': audio_path,
                'file_size': total_size,
                'duration': info.get('duration'),
                'title': info.get('title', 'TikTok Photo Post'),
                'audio_title': info.get('track') or info.get('title', 'TikTok Audio'),
                'photo_count': len(file_paths),
            }
        except Exception as e:
            logger.error(f"Photo download failed: {e}")
            self._cleanup_paths(file_paths + ([audio_path] if audio_path else []))
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

    def _download_audio_source(self, url: str, media_id: str) -> Optional[str]:
        if url.startswith('ytdl:'):
            return self._download_audio_with_yt_dlp(url.removeprefix('ytdl:'), media_id)
        return self._download_audio_file(url, media_id)

    def _download_audio_with_yt_dlp(self, url: str, media_id: str) -> Optional[str]:
        with yt_dlp.YoutubeDL(self._get_audio_ydl_opts(media_id)) as ydl:
            ydl.download([url])
        return self._find_downloaded_file(f"{media_id}_audio", self.AUDIO_EXTENSIONS)

    def _download_audio_file(self, url: str, media_id: str) -> Optional[str]:
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

            ext = self._guess_audio_extension(url, response.headers.get_content_type())
            file_path = self.downloads_path / f"{media_id}_audio{ext}"
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

    def _guess_audio_extension(self, url: str, content_type: Optional[str]) -> str:
        ext = Path(urlparse(url).path).suffix.lower()
        if ext in self.AUDIO_EXTENSIONS:
            return ext

        guessed = mimetypes.guess_extension(content_type or '')
        if guessed in self.AUDIO_EXTENSIONS:
            return guessed

        if content_type in {'audio/mp4', 'video/mp4'}:
            return '.m4a'

        return '.mp3'

    def _estimate_filesize(self, info: Dict[str, Any]) -> int:
        requested_formats = info.get('requested_formats') or []
        requested_size = 0
        for fmt in requested_formats:
            requested_size += fmt.get('filesize') or fmt.get('filesize_approx') or 0

        if requested_size:
            return requested_size

        return info.get('filesize') or info.get('filesize_approx') or 0

    def _find_downloaded_file(self, media_id: str, extensions: set[str]) -> Optional[str]:
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

    def _file_too_large_error(self, size_bytes: int, label: str = 'Файл') -> Dict[str, Any]:
        size_mb = size_bytes / (1024 * 1024)
        max_mb = self.max_file_size_bytes / (1024 * 1024)
        return {
            'success': False,
            'error': f'{label} слишком большой ({size_mb:.1f} МБ). Максимум: {max_mb:.0f} МБ',
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

    def _format_instagram_error(self, error: Exception) -> Dict[str, Any]:
        error_msg = str(error).lower()

        if 'login required' in error_msg or 'not logged in' in error_msg:
            return {
                'success': False,
                'error': 'Instagram требует авторизацию для этого Reel',
            }
        if 'unavailable' in error_msg or 'not available' in error_msg:
            return {'success': False, 'error': 'Reel недоступен или был удалён'}
        if 'private' in error_msg:
            return {'success': False, 'error': 'Reel из приватного аккаунта'}

        return {'success': False, 'error': f'Ошибка загрузки Instagram: {str(error)}'}


# Backwards compatibility alias
TikTokDownloader = MediaDownloader
