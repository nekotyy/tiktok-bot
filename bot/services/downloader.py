"""TikTok video downloader using yt-dlp."""

import os
import logging
import mimetypes
import re
from pathlib import Path
from typing import Dict, Any, Optional, List
import asyncio
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

import yt_dlp
try:
    from gallery_dl.job import DataJob
except ImportError:  # pragma: no cover - optional dependency fallback
    DataJob = None

logger = logging.getLogger(__name__)


class TikTokDownloader:
    """TikTok video downloader."""

    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
    VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}
    
    def __init__(self, downloads_path: str, max_file_size_bytes: int):
        """Initialize downloader.
        
        Args:
            downloads_path: Path to downloads directory
            max_file_size_bytes: Maximum allowed file size
        """
        self.downloads_path = Path(downloads_path)
        self.max_file_size_bytes = max_file_size_bytes
        self._ensure_directory()
    
    def _ensure_directory(self):
        """Ensure downloads directory exists."""
        self.downloads_path.mkdir(parents=True, exist_ok=True)
    
    def _get_common_ydl_opts(self) -> Dict[str, Any]:
        """Get shared yt-dlp options."""
        return {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            },
            # Download options
            'nocheckcertificate': True,
            'no_color': True,
            # Timeout settings
            'socket_timeout': 30,
        }

    def _get_ydl_opts(self, output_path: str) -> Dict[str, Any]:
        """Get yt-dlp options for video download."""
        opts = self._get_common_ydl_opts()
        opts.update({
            'format': 'best[ext=mp4]/best',  # Prefer MP4 format
            'outtmpl': output_path,
        })
        return opts
    
    async def download_video(self, url: str) -> Dict[str, Any]:
        """Download TikTok video.
        
        Args:
            url: TikTok video URL
            
        Returns:
            Dictionary with download result:
            {
                'success': bool,
                'file_path': str (if success),
                'file_size': int (if success),
                'duration': int (if success),
                'title': str (if success),
                'error': str (if not success)
            }
        """
        url = self._prepare_url(url)

        # Generate unique filename
        video_id = str(uuid4())
        output_path = str(self.downloads_path / f"{video_id}.mp4")
        
        try:
            # Download video in executor to not block event loop
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._download_sync,
                url,
                output_path
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Download failed for {url}: {e}")
            # Clean up partial file if exists
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except Exception:
                    pass
            
            return {
                'success': False,
                'error': str(e)
            }

    async def download_media(self, url: str) -> Dict[str, Any]:
        """Download TikTok media for direct chats and groups."""
        url = self._resolve_tiktok_url(url)
        media_id = str(uuid4())

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._download_media_sync,
                url,
                media_id
            )
            return result
        except Exception as e:
            logger.error(f"Media download failed for {url}: {e}")
            self._cleanup_matching_files(media_id)
            return {
                'success': False,
                'error': str(e)
            }
    
    def _download_sync(self, url: str, output_path: str) -> Dict[str, Any]:
        """Synchronous download implementation.
        
        Args:
            url: TikTok video URL
            output_path: Output file path
            
        Returns:
            Download result dictionary
        """
        ydl_opts = self._get_ydl_opts(output_path)
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info without downloading first
                info = ydl.extract_info(url, download=False)
                
                if not info:
                    return {
                        'success': False,
                        'error': 'Не удалось получить информацию о видео'
                    }
                
                if not self._has_video_formats(info):
                    return {
                        'success': False,
                        'error': 'Эта ссылка содержит не видео, а фото-пост. Отправьте её боту напрямую.'
                    }

                # Check file size (approximate)
                filesize = info.get('filesize') or info.get('filesize_approx', 0)
                if filesize > self.max_file_size_bytes:
                    size_mb = filesize / (1024 * 1024)
                    max_mb = self.max_file_size_bytes / (1024 * 1024)
                    return {
                        'success': False,
                        'error': f'Видео слишком большое ({size_mb:.1f} МБ). Максимум: {max_mb:.0f} МБ'
                    }
                
                # Download video
                ydl.download([url])
                
                # Check if file exists and get actual size
                if not os.path.exists(output_path):
                    return {
                        'success': False,
                        'error': 'Файл не был создан после скачивания'
                    }
                
                actual_size = os.path.getsize(output_path)
                
                # Check actual file size
                if actual_size > self.max_file_size_bytes:
                    os.remove(output_path)
                    size_mb = actual_size / (1024 * 1024)
                    max_mb = self.max_file_size_bytes / (1024 * 1024)
                    return {
                        'success': False,
                        'error': f'Видео слишком большое ({size_mb:.1f} МБ). Максимум: {max_mb:.0f} МБ'
                    }
                
                # Return success result
                return {
                    'success': True,
                    'media_type': 'video',
                    'file_path': output_path,
                    'file_size': actual_size,
                    'duration': info.get('duration'),
                    'title': info.get('title', 'TikTok Video'),
                    'thumbnail': info.get('thumbnail')
                }
                
        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e)
            if 'unavailable' in error_msg.lower():
                return {
                    'success': False,
                    'error': 'Видео недоступно или было удалено'
                }
            elif 'private' in error_msg.lower():
                return {
                    'success': False,
                    'error': 'Видео приватное или аккаунт закрыт'
                }
            else:
                return {
                    'success': False,
                    'error': f'Ошибка загрузки: {error_msg}'
                }
        except Exception as e:
            logger.error(f"Unexpected error during download: {e}")
            return {
                'success': False,
                'error': f'Неожиданная ошибка: {str(e)}'
            }
    
    def _download_media_sync(self, url: str, media_id: str) -> Dict[str, Any]:
        """Download either video or image media."""
        try:
            ytdlp_url = self._convert_photo_url_to_video_url(url)
            info = self._extract_info(ytdlp_url)

            if not info:
                return {
                    'success': False,
                    'error': 'Не удалось получить информацию о публикации'
                }

            if self._has_video_formats(info):
                output_path = str(self.downloads_path / f"{media_id}.mp4")
                result = self._download_sync(ytdlp_url, output_path)
                if result.get('success'):
                    result['media_type'] = 'video'
                return result

            photo_urls = self._collect_photo_urls_with_gallery_dl(url)
            if not photo_urls:
                photo_urls = self._collect_photo_urls(info)
            if photo_urls:
                return self._download_photos_sync(info, photo_urls, media_id)

            return {
                'success': False,
                'error': 'Не удалось найти видео или фото в этой публикации TikTok'
            }
        except yt_dlp.utils.DownloadError as e:
            return self._format_download_error(e)
        except Exception as e:
            logger.error(f"Unexpected media download error: {e}")
            self._cleanup_matching_files(media_id)
            return {
                'success': False,
                'error': f'Неожиданная ошибка: {str(e)}'
            }

    def _extract_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Extract media info without downloading."""
        with yt_dlp.YoutubeDL(self._get_common_ydl_opts()) as ydl:
            return ydl.extract_info(url, download=False)

    def _prepare_url(self, url: str) -> str:
        """Resolve short TikTok URLs and normalize photo posts to video URLs."""
        resolved_url = self._resolve_tiktok_url(url)
        return self._convert_photo_url_to_video_url(resolved_url)

    def _resolve_tiktok_url(self, url: str) -> str:
        """Resolve short vm/vt TikTok URLs to their final destination."""
        try:
            parsed = urlparse(url)
            hostname = (parsed.netloc or '').lower()
            if hostname not in {'vm.tiktok.com', 'vt.tiktok.com'}:
                return url

            request = Request(
                url,
                headers={
                    'User-Agent': (
                        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                        'AppleWebKit/537.36 (KHTML, like Gecko) '
                        'Chrome/120.0.0.0 Safari/537.36'
                    )
                }
            )
            with urlopen(request, timeout=15) as response:
                return response.geturl() or url
        except Exception as e:
            logger.warning(f"Failed to resolve short TikTok URL {url}: {e}")
            return url

    def _convert_photo_url_to_video_url(self, url: str) -> str:
        """Convert TikTok photo URLs to equivalent video URLs."""
        return re.sub(r'/photo/(\d+)', r'/video/\1', url)

    def _has_video_formats(self, info: Dict[str, Any]) -> bool:
        """Check if media contains a video stream."""
        formats = info.get('formats') or []
        for fmt in formats:
            if fmt.get('vcodec') not in (None, 'none'):
                return True

        ext = (info.get('ext') or '').lower()
        return ext in {item.lstrip('.') for item in self.VIDEO_EXTENSIONS}

    def _collect_photo_urls(self, info: Dict[str, Any]) -> List[str]:
        """Collect unique image URLs from metadata."""
        urls: List[str] = []
        seen = set()

        thumbnail = info.get('thumbnail')
        if thumbnail and thumbnail not in seen:
            urls.append(thumbnail)
            seen.add(thumbnail)

        thumbnails = sorted(
            info.get('thumbnails') or [],
            key=lambda item: item.get('preference', 0),
            reverse=True
        )

        for item in thumbnails:
            image_url = item.get('url')
            if not image_url or image_url in seen:
                continue
            urls.append(image_url)
            seen.add(image_url)

        return urls

    def _collect_photo_urls_with_gallery_dl(self, url: str) -> List[str]:
        """Collect photo post image URLs using gallery-dl."""
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
        media_id: str
    ) -> Dict[str, Any]:
        """Download photo post images from metadata URLs."""
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
                    'error': 'Не удалось скачать изображения из этой публикации'
                }

            return {
                'success': True,
                'media_type': 'photo',
                'file_paths': file_paths,
                'file_size': total_size,
                'duration': None,
                'title': info.get('title', 'TikTok Photo Post'),
                'photo_count': len(file_paths)
            }
        except Exception as e:
            logger.error(f"Photo download failed: {e}")
            self._cleanup_paths(file_paths)
            self._cleanup_matching_files(media_id)
            return {
                'success': False,
                'error': f'Не удалось скачать фото: {str(e)}'
            }

    def _download_photo_file(self, url: str, media_id: str, index: int) -> Optional[str]:
        """Download a single image file."""
        request = Request(
            url,
            headers={
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/120.0.0.0 Safari/537.36'
                )
            }
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
        """Guess a file extension for a downloaded image."""
        ext = Path(urlparse(url).path).suffix.lower()
        if ext in self.IMAGE_EXTENSIONS:
            return ext

        guessed = mimetypes.guess_extension(content_type or '')
        if guessed in self.IMAGE_EXTENSIONS:
            return guessed

        return '.jpg'

    def _cleanup_matching_files(self, media_id: str):
        """Delete files created for a single media item."""
        for file_path in self.downloads_path.glob(f"{media_id}*"):
            try:
                if file_path.is_file():
                    file_path.unlink()
            except Exception:
                pass

    def _cleanup_paths(self, file_paths: List[str]):
        """Delete specific file paths."""
        for file_path in file_paths:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                pass

    def _file_too_large_error(self, size_bytes: int) -> Dict[str, Any]:
        """Format file size limit error."""
        size_mb = size_bytes / (1024 * 1024)
        max_mb = self.max_file_size_bytes / (1024 * 1024)
        return {
            'success': False,
            'error': f'Файл слишком большой ({size_mb:.1f} МБ). Максимум: {max_mb:.0f} МБ'
        }

    def _format_download_error(self, error: Exception) -> Dict[str, Any]:
        """Convert yt-dlp errors to user-friendly text."""
        error_msg = str(error)
        error_lower = error_msg.lower()

        if 'unavailable' in error_lower:
            return {
                'success': False,
                'error': 'Публикация недоступна или была удалена'
            }
        if 'private' in error_lower:
            return {
                'success': False,
                'error': 'Публикация приватная или аккаунт закрыт'
            }
        if 'blocked from accessing this post' in error_lower:
            return {
                'success': False,
                'error': 'TikTok временно ограничил доступ к этой публикации с текущего IP'
            }

        return {
            'success': False,
            'error': f'Ошибка загрузки: {error_msg}'
        }

    async def get_video_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Get video information without downloading.
        
        Args:
            url: TikTok video URL
            
        Returns:
            Video info dictionary or None
        """
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
            }
            
            loop = asyncio.get_event_loop()
            
            def _extract_info():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=False)
            
            info = await loop.run_in_executor(None, _extract_info)
            
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
