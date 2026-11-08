use regex::Regex;
use serde_json::Value;
use std::path::Path;
use std::sync::LazyLock;
use std::time::Duration;
use tokio::io::AsyncWriteExt;

static SHORTCODE_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)/(?:reel|reels|p|tv)/([A-Za-z0-9_-]+)").unwrap()
});

static CONTEXT_JSON_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r#""contextJSON":"((?:\\.|[^"\\])*)""#).unwrap()
});

const MOBILE_USER_AGENT: &str =
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1";

#[derive(Clone, Debug)]
#[allow(dead_code)]
pub struct InstagramMediaItem {
    pub is_video: bool,
    pub url: String,
    pub thumbnail: Option<String>,
}

#[derive(Clone, Debug)]
#[allow(dead_code)]
pub struct InstagramPostData {
    pub shortcode: String,
    pub title: String,
    pub description: String,
    pub uploader: String,
    pub items: Vec<InstagramMediaItem>,
}

#[derive(Clone)]
pub struct InstagramExtractor {
    client: reqwest::Client,
}

impl InstagramExtractor {
    pub fn new(proxy: Option<&str>) -> Self {
        let mut builder = reqwest::Client::builder()
            .timeout(Duration::from_secs(30))
            .user_agent(MOBILE_USER_AGENT)
            .redirect(reqwest::redirect::Policy::limited(10));

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

    pub fn extract_shortcode(url: &str) -> Option<String> {
        let mat = SHORTCODE_RE.captures(url)?;
        Some(mat.get(1)?.as_str().to_string())
    }

    pub async fn extract(&self, post_url: &str) -> anyhow::Result<InstagramPostData> {
        let shortcode = Self::extract_shortcode(post_url)
            .ok_or_else(|| anyhow::anyhow!("Ссылка не содержит публичный пост или Reel"))?;

        let embed_url = format!("https://www.instagram.com/p/{shortcode}/embed/captioned/");

        let res = self
            .client
            .get(&embed_url)
            .header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
            .header("Accept-Language", "en-US,en;q=0.5")
            .header("Referer", "https://www.instagram.com/")
            .send()
            .await?;

        if !res.status().is_success() {
            anyhow::bail!("Публичная embed-страница вернула HTTP {}", res.status());
        }

        let final_url = res.url().to_string();
        if final_url.to_lowercase().contains("accounts/login") {
            anyhow::bail!("Instagram перенаправил публичную embed-страницу на вход");
        }

        let html = res.text().await?;
        let captures = CONTEXT_JSON_RE
            .captures(&html)
            .ok_or_else(|| anyhow::anyhow!("В публичной embed-странице отсутствуют данные публикации"))?;

        let raw_escaped = captures.get(1).unwrap().as_str();
        let unescaped_json: String = serde_json::from_str(&format!("\"{raw_escaped}\""))?;
        let parsed_json: Value = serde_json::from_str(&unescaped_json)?;

        let media = parsed_json
            .pointer("/gql_data/shortcode_media")
            .ok_or_else(|| anyhow::anyhow!("Instagram не вернул описание публикации"))?;

        let owner = media
            .pointer("/owner/username")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();

        let caption = media
            .pointer("/edge_media_to_caption/edges/0/node/text")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();

        let title = if !caption.is_empty() {
            caption.clone()
        } else if !owner.is_empty() {
            format!("Instagram — @{owner}")
        } else {
            "Instagram".to_string()
        };

        let mut items = Vec::new();
        if let Some(edges) = media.pointer("/edge_sidecar_to_children/edges").and_then(|v| v.as_array()) {
            for edge in edges {
                if let Some(node) = edge.get("node") {
                    if let Some(item) = Self::parse_media_node(node) {
                        items.push(item);
                    }
                }
            }
        } else if let Some(item) = Self::parse_media_node(media) {
            items.push(item);
        }

        if items.is_empty() {
            anyhow::bail!("Instagram не вернул медиа для этой публичной публикации");
        }

        Ok(InstagramPostData {
            shortcode,
            title,
            description: caption,
            uploader: owner,
            items,
        })
    }

    fn parse_media_node(node: &Value) -> Option<InstagramMediaItem> {
        let is_video = node.get("is_video").and_then(|v| v.as_bool()).unwrap_or(false);
        let media_url = if is_video {
            node.get("video_url").and_then(|v| v.as_str())?
        } else {
            node.get("display_url").and_then(|v| v.as_str())?
        };

        if media_url.is_empty() {
            return None;
        }

        let thumbnail = node.get("display_url").and_then(|v| v.as_str()).map(|s| s.to_string());

        Some(InstagramMediaItem {
            is_video,
            url: media_url.to_string(),
            thumbnail,
        })
    }

    pub async fn download_file(
        &self,
        url: &str,
        dest_path: &Path,
        max_bytes: u64,
    ) -> anyhow::Result<u64> {
        let res = self
            .client
            .get(url)
            .header("Accept", "*/*")
            .header("Referer", "https://www.instagram.com/")
            .send()
            .await?;

        if !res.status().is_success() {
            anyhow::bail!("Instagram CDN вернул HTTP {}", res.status());
        }

        if let Some(len) = res.content_length() {
            if len > max_bytes {
                anyhow::bail!("Медиа из Instagram превышает допустимый размер ({} MB)", len / (1024 * 1024));
            }
        }

        let mut file = tokio::fs::File::create(dest_path).await?;
        let mut stream = res.bytes_stream();
        let mut written: u64 = 0;

        use futures::StreamExt;
        while let Some(chunk) = stream.next().await {
            let chunk = chunk?;
            written += chunk.len() as u64;
            if written > max_bytes {
                let _ = tokio::fs::remove_file(dest_path).await;
                anyhow::bail!("Медиа из Instagram превышает допустимый размер ({} MB)", written / (1024 * 1024));
            }
            file.write_all(&chunk).await?;
        }
        file.flush().await?;

        if written == 0 {
            let _ = tokio::fs::remove_file(dest_path).await;
            anyhow::bail!("Instagram CDN вернул пустой файл");
        }

        Ok(written)
    }
}
