use serde_json::Value;
use std::collections::HashSet;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::sync::LazyLock;
use tokio::process::Command;
use tracing::{debug, error, warn};
use uuid::Uuid;

use crate::services::instagram_extractor::{InstagramExtractor, InstagramPostData};
use crate::services::tiktok_api::{TikTokApiClient, TikTokApiMedia};
use crate::services::url_parser::Platform;

static VIDEO_EXTENSIONS: LazyLock<HashSet<&'static str>> = LazyLock::new(|| {
    HashSet::from(["mp4", "mov", "webm", "mkv"])
});

static IMAGE_EXTENSIONS: LazyLock<HashSet<&'static str>> = LazyLock::new(|| {
    HashSet::from(["jpg", "jpeg", "png", "webp"])
});

#[derive(Clone, Debug)]
#[allow(dead_code)]
pub enum DownloadedMedia {
    Video {
        file_path: PathBuf,
        file_size: u64,
        duration: Option<u64>,
        title: String,
        thumbnail: Option<String>,
    },
    Photos {
        file_paths: Vec<PathBuf>,
        total_size: u64,
        title: String,
        photo_count: usize,
    },
    Album {
        file_paths: Vec<PathBuf>,
        total_size: u64,
        title: String,
    },
}

impl DownloadedMedia {
    pub fn file_size(&self) -> u64 {
        match self {
            DownloadedMedia::Video { file_size, .. } => *file_size,
            DownloadedMedia::Photos { total_size, .. } => *total_size,
            DownloadedMedia::Album { total_size, .. } => *total_size,
        }
    }

    pub fn duration(&self) -> Option<u64> {
        match self {
            DownloadedMedia::Video { duration, .. } => *duration,
            _ => None,
        }
    }

    pub fn title(&self) -> &str {
        match self {
            DownloadedMedia::Video { title, .. } => title,
            DownloadedMedia::Photos { title, .. } => title,
            DownloadedMedia::Album { title, .. } => title,
        }
    }
}

#[derive(Clone)]
pub struct MediaDownloader {
    downloads_path: PathBuf,
    max_file_size_bytes: u64,
    proxy: Option<String>,
    impersonate: Option<String>,
    instagram: InstagramExtractor,
    tiktok: TikTokApiClient,
}

impl MediaDownloader {
    pub fn new<P: AsRef<Path>>(
        downloads_path: P,
        max_file_size_bytes: u64,
        proxy: Option<String>,
        impersonate: Option<String>,
    ) -> Self {
        let p_ref = downloads_path.as_ref().to_path_buf();
        let _ = std::fs::create_dir_all(&p_ref);

        let instagram = InstagramExtractor::new(proxy.as_deref());
        let tiktok = TikTokApiClient::new(proxy.as_deref());

        Self {
            downloads_path: p_ref,
            max_file_size_bytes,
            proxy,
            impersonate,
            instagram,
            tiktok,
        }
    }

    pub async fn download_media(
        &self,
        platform: Platform,
        url: &str,
    ) -> Result<DownloadedMedia, String> {
        let media_id = Uuid::new_v4().to_string();

        match platform {
            Platform::TikTok => self.download_tiktok(url, &media_id).await,
            Platform::InstagramReels => self.download_instagram(url, &media_id).await,
            Platform::YouTubeShorts => self.download_youtube(url, &media_id).await,
            Platform::Vk => self.download_vk(url, &media_id).await,
            Platform::Other => self.download_other(url, &media_id).await,
        }
    }

    async fn download_tiktok(&self, url: &str, media_id: &str) -> Result<DownloadedMedia, String> {
        // 1. High-speed direct API (TikWM) - unwatermarked HD video and slideshows
        match self
            .tiktok
            .fetch_media(url, &self.downloads_path, media_id, self.max_file_size_bytes)
            .await
        {
            Ok(Some(TikTokApiMedia::Video {
                file_path,
                file_size,
                title,
                duration,
                ..
            })) => {
                let compatible_path = self
                    .ensure_telegram_compatibility(&file_path, media_id)
                    .await
                    .unwrap_or(file_path);

                let actual_size = tokio::fs::metadata(&compatible_path)
                    .await
                    .map(|m| m.len())
                    .unwrap_or(file_size);

                return Ok(DownloadedMedia::Video {
                    file_path: compatible_path,
                    file_size: actual_size,
                    duration,
                    title,
                    thumbnail: None,
                });
            }
            Ok(Some(TikTokApiMedia::Photos {
                file_paths,
                total_size,
                title,
                photo_count,
                ..
            })) => {
                return Ok(DownloadedMedia::Photos {
                    file_paths,
                    total_size,
                    title,
                    photo_count,
                });
            }
            Ok(None) => {
                debug!("TikWM did not return media, falling back to yt-dlp...");
            }
            Err(e) => {
                debug!("TikWM error: {e}, falling back to yt-dlp...");
            }
        }

        // 2. yt-dlp fallback
        self.download_with_ytdlp(url, media_id, "TikTok Video").await
    }

    async fn download_instagram(&self, url: &str, media_id: &str) -> Result<DownloadedMedia, String> {
        // 1. Anonymous public embed extractor
        match self.instagram.extract(url).await {
            Ok(data) => {
                if let Ok(media) = self.download_instagram_items(data, media_id).await {
                    return Ok(media);
                }
            }
            Err(e) => {
                debug!("Anonymous Instagram extraction failed: {e}; trying yt-dlp...");
            }
        }

        // 2. yt-dlp fallback
        self.download_with_ytdlp(url, media_id, "Instagram Video").await
    }

    async fn download_instagram_items(
        &self,
        data: InstagramPostData,
        media_id: &str,
    ) -> anyhow::Result<DownloadedMedia> {
        let is_all_photos = data.items.iter().all(|item| !item.is_video);
        let is_single = data.items.len() == 1;

        if is_single && data.items[0].is_video {
            let item = &data.items[0];
            let raw_path = self.downloads_path.join(format!("{media_id}_raw.mp4"));
            self.instagram
                .download_file(&item.url, &raw_path, self.max_file_size_bytes)
                .await?;

            let compatible = self.ensure_telegram_compatibility(&raw_path, media_id).await?;
            let size = tokio::fs::metadata(&compatible).await?.len();
            let duration = self.probe_duration(&compatible).await;

            return Ok(DownloadedMedia::Video {
                file_path: compatible,
                file_size: size,
                duration,
                title: data.title,
                thumbnail: item.thumbnail.clone(),
            });
        }

        let mut file_paths = Vec::new();
        let mut total_size: u64 = 0;

        for (idx, item) in data.items.iter().enumerate() {
            let ext = if item.is_video { "mp4" } else { "jpg" };
            let path = self.downloads_path.join(format!("{media_id}_{:03}.{ext}", idx + 1));
            let s = self
                .instagram
                .download_file(&item.url, &path, self.max_file_size_bytes)
                .await?;

            let final_path = if item.is_video {
                self.ensure_telegram_compatibility(&path, &format!("{media_id}_{idx}"))
                    .await
                    .unwrap_or(path)
            } else {
                path
            };

            total_size += s;
            file_paths.push(final_path);
        }

        if file_paths.is_empty() {
            anyhow::bail!("Не удалось скачать элементы публикации");
        }

        if is_all_photos {
            Ok(DownloadedMedia::Photos {
                photo_count: file_paths.len(),
                file_paths,
                total_size,
                title: data.title,
            })
        } else {
            Ok(DownloadedMedia::Album {
                file_paths,
                total_size,
                title: data.title,
            })
        }
    }

    async fn download_youtube(&self, url: &str, media_id: &str) -> Result<DownloadedMedia, String> {
        self.download_with_ytdlp(url, media_id, "YouTube Video").await
    }

    async fn download_vk(&self, url: &str, media_id: &str) -> Result<DownloadedMedia, String> {
        self.download_with_ytdlp(url, media_id, "VK Video").await
    }

    async fn download_other(&self, url: &str, media_id: &str) -> Result<DownloadedMedia, String> {
        self.download_with_ytdlp(url, media_id, "Video").await
    }

    async fn download_with_ytdlp(
        &self,
        url: &str,
        media_id: &str,
        fallback_title: &str,
    ) -> Result<DownloadedMedia, String> {
        let out_tmpl = self
            .downloads_path
            .join(format!("{media_id}.%(ext)s"))
            .to_string_lossy()
            .to_string();

        let format_selector = "bv*[ext=mp4][vcodec^=avc]+ba[ext=m4a]/\
                               bv*[ext=mp4]+ba[acodec!=none]/\
                               bv*+ba[acodec!=none]/\
                               b[ext=mp4][vcodec^=avc][acodec!=none]/\
                               b[ext=mp4][vcodec^=h264][acodec!=none]/\
                               b[ext=mp4][vcodec!=none][acodec!=none]/\
                               b[vcodec!=none][acodec!=none]/\
                               bv*[ext=mp4][vcodec!=none][acodec=none]/\
                               bv*[vcodec!=none][acodec=none]";

        let mut args = vec![
            "--quiet".to_string(),
            "--no-warnings".to_string(),
            "--no-color".to_string(),
            "--no-playlist".to_string(),
            "--playlist-items".to_string(),
            "1".to_string(),
            "--socket-timeout".to_string(),
            "30".to_string(),
            "--retries".to_string(),
            "3".to_string(),
            "--format".to_string(),
            format_selector.to_string(),
            "--merge-output-format".to_string(),
            "mp4".to_string(),
            "-o".to_string(),
            out_tmpl,
        ];

        if let Some(ref p) = self.proxy {
            args.push("--proxy".to_string());
            args.push(p.clone());
        }

        if let Some(ref imp) = self.impersonate {
            args.push("--impersonate".to_string());
            args.push(imp.clone());
        }

        // Add URL
        args.push(url.to_string());

        let output = Command::new("yt-dlp")
            .args(&args)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .output()
            .await;

        let output = match output {
            Ok(o) => o,
            Err(e) => {
                error!("yt-dlp execution failed: {e}");
                return Err(format!("Не удалось запустить загрузчик yt-dlp: {e}"));
            }
        };

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            warn!("yt-dlp stderr: {stderr}");
            return Err(Self::format_ytdlp_error(&stderr));
        }

        let downloaded_file = self
            .find_file_with_prefix(media_id, &VIDEO_EXTENSIONS)
            .await;

        let file_path = match downloaded_file {
            Some(p) => p,
            None => {
                // If no video, check if images were downloaded
                let images = self.find_all_files_with_prefix(media_id, &IMAGE_EXTENSIONS).await;
                if !images.is_empty() {
                    let mut total_size = 0;
                    for p in &images {
                        if let Ok(m) = tokio::fs::metadata(p).await {
                            total_size += m.len();
                        }
                    }
                    return Ok(DownloadedMedia::Photos {
                        photo_count: images.len(),
                        file_paths: images,
                        total_size,
                        title: fallback_title.to_string(),
                    });
                }
                return Err("Файл не был создан после скачивания".to_string());
            }
        };

        // Ensure audio & telegram compatibility
        let final_path = self
            .ensure_telegram_compatibility(&file_path, media_id)
            .await
            .unwrap_or(file_path);

        let size = match tokio::fs::metadata(&final_path).await {
            Ok(m) => m.len(),
            Err(_) => return Err("Не удалось прочитать скачанный файл".to_string()),
        };

        if size > self.max_file_size_bytes {
            let _ = tokio::fs::remove_file(&final_path).await;
            return Err(format!(
                "Видео слишком большое ({:.1} МБ). Максимум: {:.0} МБ",
                size as f64 / (1024.0 * 1024.0),
                self.max_file_size_bytes as f64 / (1024.0 * 1024.0)
            ));
        }

        let duration = self.probe_duration(&final_path).await;

        Ok(DownloadedMedia::Video {
            file_path: final_path,
            file_size: size,
            duration,
            title: fallback_title.to_string(),
            thumbnail: None,
        })
    }

    async fn ensure_telegram_compatibility(
        &self,
        file_path: &Path,
        media_id: &str,
    ) -> anyhow::Result<PathBuf> {
        let probe = self.probe_file(file_path).await?;
        let video_stream = Self::find_stream(&probe, "video");
        if video_stream.is_none() {
            anyhow::bail!("В скачанном файле отсутствует видеопоток");
        }

        let audio_stream = Self::find_stream(&probe, "audio");
        let v_codec = video_stream
            .and_then(|s| s.get("codec_name"))
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let pix_fmt = video_stream
            .and_then(|s| s.get("pix_fmt"))
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let a_codec = audio_stream
            .and_then(|s| s.get("codec_name"))
            .and_then(|v| v.as_str())
            .unwrap_or("");

        let compatible_video = v_codec == "h264" && (pix_fmt == "yuv420p" || pix_fmt == "yuvj420p");
        let compatible_audio = audio_stream.is_none() || a_codec == "aac";
        let is_mp4 = file_path
            .extension()
            .and_then(|e| e.to_str())
            .map(|e| e.eq_ignore_ascii_case("mp4"))
            .unwrap_or(false);

        if compatible_video && compatible_audio && is_mp4 {
            return Ok(file_path.to_path_buf());
        }

        let output_path = self
            .downloads_path
            .join(format!("{media_id}_telegram.mp4"));

        let mut cmd = Command::new("ffmpeg");
        cmd.arg("-hide_banner")
            .arg("-loglevel")
            .arg("error")
            .arg("-y")
            .arg("-i")
            .arg(file_path)
            .arg("-map")
            .arg("0:v:0");

        if audio_stream.is_some() {
            cmd.arg("-map").arg("0:a:0");
        }

        if compatible_video {
            cmd.arg("-c:v").arg("copy");
        } else {
            cmd.arg("-c:v")
                .arg("libx264")
                .arg("-preset")
                .arg("veryfast")
                .arg("-crf")
                .arg("23")
                .arg("-pix_fmt")
                .arg("yuv420p");
        }

        if audio_stream.is_some() {
            if compatible_audio {
                cmd.arg("-c:a").arg("copy");
            } else {
                cmd.arg("-c:a").arg("aac").arg("-b:a").arg("192k");
            }
        } else {
            cmd.arg("-an");
        }

        cmd.arg("-movflags").arg("+faststart").arg(&output_path);

        let status = cmd.status().await?;
        if !status.success() {
            anyhow::bail!("ffmpeg не смог перекодировать видео в совместимый MP4");
        }

        let _ = tokio::fs::remove_file(file_path).await;
        Ok(output_path)
    }

    async fn probe_file(&self, path: &Path) -> anyhow::Result<Value> {
        let output = Command::new("ffprobe")
            .args([
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type,codec_name,pix_fmt:format=format_name,duration",
                "-of",
                "json",
            ])
            .arg(path)
            .output()
            .await?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            anyhow::bail!("ffprobe error: {stderr}");
        }

        let json: Value = serde_json::from_slice(&output.stdout)?;
        Ok(json)
    }

    async fn probe_duration(&self, path: &Path) -> Option<u64> {
        let json = self.probe_file(path).await.ok()?;
        let duration_str = json.pointer("/format/duration")?.as_str()?;
        let duration_f: f64 = duration_str.parse().ok()?;
        Some(duration_f.round() as u64)
    }

    fn find_stream<'a>(probe: &'a Value, stream_type: &str) -> Option<&'a Value> {
        let streams = probe.get("streams")?.as_array()?;
        streams.iter().find(|s| {
            s.get("codec_type")
                .and_then(|v| v.as_str())
                .map(|t| t == stream_type)
                .unwrap_or(false)
        })
    }

    async fn find_file_with_prefix(&self, prefix: &str, exts: &HashSet<&str>) -> Option<PathBuf> {
        let mut read_dir = tokio::fs::read_dir(&self.downloads_path).await.ok()?;
        let mut candidates = Vec::new();

        while let Ok(Some(entry)) = read_dir.next_entry().await {
            let path = entry.path();
            if let Some(name) = path.file_name().and_then(|n| n.to_str()) {
                if name.starts_with(prefix) {
                    if let Some(ext) = path.extension().and_then(|e| e.to_str()) {
                        if exts.contains(ext.to_lowercase().as_str()) {
                            candidates.push(path);
                        }
                    }
                }
            }
        }

        candidates.into_iter().max_by_key(|p| {
            std::fs::metadata(p)
                .and_then(|m| m.modified())
                .unwrap_or(std::time::SystemTime::UNIX_EPOCH)
        })
    }

    async fn find_all_files_with_prefix(&self, prefix: &str, exts: &HashSet<&str>) -> Vec<PathBuf> {
        let mut read_dir = match tokio::fs::read_dir(&self.downloads_path).await {
            Ok(rd) => rd,
            Err(_) => return Vec::new(),
        };

        let mut list = Vec::new();
        while let Ok(Some(entry)) = read_dir.next_entry().await {
            let path = entry.path();
            if let Some(name) = path.file_name().and_then(|n| n.to_str()) {
                if name.starts_with(prefix) {
                    if let Some(ext) = path.extension().and_then(|e| e.to_str()) {
                        if exts.contains(ext.to_lowercase().as_str()) {
                            list.push(path);
                        }
                    }
                }
            }
        }
        list.sort();
        list
    }

    fn format_ytdlp_error(err_str: &str) -> String {
        let lower = err_str.to_lowercase();
        if lower.contains("unsupported url") {
            "Загрузчик пока не поддерживает эту ссылку".to_string()
        } else if lower.contains("unavailable") || lower.contains("not available") {
            "Публикация недоступна или была удалена".to_string()
        } else if lower.contains("private") {
            "Публикация приватная или аккаунт закрыт".to_string()
        } else if lower.contains("login required") || lower.contains("not logged in") {
            "Эта публикация не доступна анонимно или является приватной.".to_string()
        } else if lower.contains("sign in to confirm") || lower.contains("not a bot") {
            "Площадка отклонила запрос с IP сервера. Попробуйте позже или настройте YTDLP_PROXY.".to_string()
        } else {
            "Ошибка загрузки медиа. Попробуйте позже.".to_string()
        }
    }
}
