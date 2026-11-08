use futures::future::join_all;
use serde_json::Value;
use std::path::{Path, PathBuf};
use std::time::Duration;
use tokio::io::AsyncWriteExt;
use tracing::warn;

#[derive(Clone, Debug)]
#[allow(dead_code)]
pub enum TikTokApiMedia {
    Video {
        file_path: PathBuf,
        file_size: u64,
        title: String,
        caption: String,
        duration: Option<u64>,
    },
    Photos {
        file_paths: Vec<PathBuf>,
        total_size: u64,
        title: String,
        caption: String,
        photo_count: usize,
    },
}

#[derive(Clone)]
pub struct TikTokApiClient {
    client: reqwest::Client,
}

impl TikTokApiClient {
    pub fn new(proxy: Option<&str>) -> Self {
        let mut builder = reqwest::Client::builder()
            .timeout(Duration::from_secs(30))
            .user_agent(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
            );

        if let Some(proxy_str) = proxy {
            if !proxy_str.trim().is_empty() {
                if let Ok(p) = reqwest::Proxy::all(proxy_str) {
                    builder = builder.proxy(p);
                }
            }
        }

        Self {
            client: builder.build().unwrap_or_default(),
        }
    }

    pub async fn fetch_media(
        &self,
        url: &str,
        downloads_dir: &Path,
        media_id: &str,
        max_file_size_bytes: u64,
    ) -> anyhow::Result<Option<TikTokApiMedia>> {
        let encoded_url = form_urlencoded::byte_serialize(url.as_bytes()).collect::<String>();
        let api_endpoint = format!("https://tikwm.com/api/?url={encoded_url}");

        let res = match self.client.get(&api_endpoint).send().await {
            Ok(r) => r,
            Err(e) => {
                warn!("TikWM API request failed: {e}");
                return Ok(None);
            }
        };

        if !res.status().is_success() {
            warn!("TikWM API HTTP status: {}", res.status());
            return Ok(None);
        }

        let json: Value = match res.json().await {
            Ok(j) => j,
            Err(e) => {
                warn!("TikWM API JSON decode failed: {e}");
                return Ok(None);
            }
        };

        if json.get("code").and_then(|v| v.as_i64()).unwrap_or(-1) != 0 {
            let msg = json.get("msg").and_then(|v| v.as_str()).unwrap_or("unknown");
            warn!("TikWM API returned error message: {msg}");
            return Ok(None);
        }

        let data = match json.get("data") {
            Some(d) => d,
            None => return Ok(None),
        };

        let title = data
            .get("title")
            .and_then(|v| v.as_str())
            .unwrap_or("TikTok Video")
            .to_string();

        let author_nickname = data
            .pointer("/author/nickname")
            .and_then(|v| v.as_str())
            .or_else(|| data.pointer("/author/unique_id").and_then(|v| v.as_str()))
            .unwrap_or("");

        let caption = if !author_nickname.is_empty() {
            format!("{title} — {author_nickname}")
        } else {
            title.clone()
        };

        let duration = data.get("duration").and_then(|v| v.as_u64());

        // Check for slideshow / photos
        if let Some(images_val) = data.get("images").and_then(|v| v.as_array()) {
            if !images_val.is_empty() {
                let mut tasks = Vec::new();
                for (idx, img_val) in images_val.iter().enumerate() {
                    if let Some(img_url) = img_val.as_str() {
                        let client = self.client.clone();
                        let target_path = downloads_dir.join(format!("{media_id}_{:03}.jpg", idx + 1));
                        let url_clone = img_url.to_string();

                        tasks.push(tokio::spawn(async move {
                            match client.get(&url_clone).send().await {
                                Ok(resp) if resp.status().is_success() => {
                                    if let Ok(bytes) = resp.bytes().await {
                                        if tokio::fs::write(&target_path, &bytes).await.is_ok() {
                                            return Some((target_path, bytes.len() as u64));
                                        }
                                    }
                                }
                                _ => {}
                            }
                            None
                        }));
                    }
                }

                let results = join_all(tasks).await;
                let mut photo_paths = Vec::new();
                let mut total_size: u64 = 0;

                for res in results {
                    if let Ok(Some((p, s))) = res {
                        total_size += s;
                        photo_paths.push(p);
                    }
                }

                if !photo_paths.is_empty() {
                    if total_size > max_file_size_bytes {
                        for p in &photo_paths {
                            let _ = tokio::fs::remove_file(p).await;
                        }
                        anyhow::bail!(
                            "Размер файлов ({:.1} МБ) превышает лимит {:.0} МБ",
                            total_size as f64 / (1024.0 * 1024.0),
                            max_file_size_bytes as f64 / (1024.0 * 1024.0)
                        );
                    }

                    return Ok(Some(TikTokApiMedia::Photos {
                        photo_count: photo_paths.len(),
                        file_paths: photo_paths,
                        total_size,
                        title,
                        caption,
                    }));
                }
            }
        }

        // Video download
        let mut video_url = data
            .get("play")
            .and_then(|v| v.as_str())
            .or_else(|| data.get("wmplay").and_then(|v| v.as_str()))
            .unwrap_or("")
            .to_string();

        if video_url.is_empty() {
            return Ok(None);
        }

        if !video_url.starts_with("http") {
            video_url = format!("https://tikwm.com{video_url}");
        }

        let out_file = downloads_dir.join(format!("{media_id}.mp4"));
        let res = match self.client.get(&video_url).send().await {
            Ok(r) => r,
            Err(e) => {
                warn!("Failed to stream TikWM video: {e}");
                return Ok(None);
            }
        };

        if !res.status().is_success() {
            return Ok(None);
        }

        let mut file = tokio::fs::File::create(&out_file).await?;
        let mut stream = res.bytes_stream();
        let mut written: u64 = 0;

        use futures::StreamExt;
        while let Some(chunk_res) = stream.next().await {
            let chunk = match chunk_res {
                Ok(c) => c,
                Err(e) => {
                    let _ = tokio::fs::remove_file(&out_file).await;
                    warn!("Error while streaming TikWM video: {e}");
                    return Ok(None);
                }
            };
            written += chunk.len() as u64;
            if written > max_file_size_bytes {
                let _ = tokio::fs::remove_file(&out_file).await;
                anyhow::bail!(
                    "Размер файла ({:.1} МБ) превышает лимит {:.0} МБ",
                    written as f64 / (1024.0 * 1024.0),
                    max_file_size_bytes as f64 / (1024.0 * 1024.0)
                );
            }
            if let Err(e) = file.write_all(&chunk).await {
                let _ = tokio::fs::remove_file(&out_file).await;
                warn!("Error writing video chunk: {e}");
                return Ok(None);
            }
        }
        let _ = file.flush().await;

        if written == 0 {
            let _ = tokio::fs::remove_file(&out_file).await;
            return Ok(None);
        }

        Ok(Some(TikTokApiMedia::Video {
            file_path: out_file,
            file_size: written,
            title,
            caption,
            duration,
        }))
    }
}
