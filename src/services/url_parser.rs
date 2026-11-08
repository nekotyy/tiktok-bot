use regex::Regex;
use std::collections::HashSet;
use std::sync::LazyLock;
use url::Url;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Platform {
    TikTok,
    YouTubeShorts,
    InstagramReels,
    Vk,
    Other,
}

impl Platform {
    #[allow(dead_code)]
    pub fn as_str(&self) -> &'static str {
        match self {
            Platform::TikTok => "tiktok",
            Platform::YouTubeShorts => "youtube_shorts",
            Platform::InstagramReels => "instagram_reels",
            Platform::Vk => "vk",
            Platform::Other => "other",
        }
    }

    pub fn display_label(&self) -> &'static str {
        match self {
            Platform::TikTok => "TikTok",
            Platform::YouTubeShorts => "YouTube",
            Platform::InstagramReels => "Instagram",
            Platform::Vk => "VK",
            Platform::Other => "медиа",
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ParsedUrl {
    pub platform: Platform,
    pub original_url: String,
    pub normalized_url: String,
}

static URL_REGEX: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)https?://[^\s<>\x22\x27]+").unwrap()
});

static TIKTOK_PATH_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)(?:^|/)(?:video|photo)/\d+|(?:t|v|embed)/").unwrap()
});

static YT_SHORTS_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)^(?:shorts|live|embed|clip)/[^/]+").unwrap()
});

static IG_PATH_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)^(?:[^/]+/)?(?:p|reel|reels|tv)/[^/]+|^share/(?:p|reel)/[^/]+|^stories/[^/]+/[^/]+").unwrap()
});

static VK_PATH_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)^(?:video|clip|wall)-?\d+_\d+|^@[^/]+/(?:clip|video)-?\d+_\d+").unwrap()
});

static VK_VIDEOS_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)^videos-?\d+$").unwrap()
});

static VK_EMBEDDED_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?i)(?:video|clip)-?\d+_\d+").unwrap()
});

static X_PATH_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^[^/]+/status/\d+").unwrap()
});

static FB_PATH_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^(?:reel/[^/]+|share/(?:r|v)/[^/]+|[^/]+/(?:videos|posts)/[^/]+)").unwrap()
});

static THREADS_PATH_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^@[^/]+/post/[^/]+").unwrap()
});

static REDDIT_PATH_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^r/[^/]+/comments/[^/]+").unwrap()
});

static PINTEREST_PATH_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^pin/\d+").unwrap()
});

static RUTUBE_PATH_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^(?:video|shorts)/[^/]+").unwrap()
});

static OK_PATH_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^(?:video|videoembed)/\d+").unwrap()
});

static TWITCH_PATH_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^(?:videos/\d+|[^/]+/clip/[^/]+)").unwrap()
});

static VIMEO_PATH_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^(?:\d+(?:$|/)|(?:channels|showcase)/[^/]+/(?:video/)?\d+)").unwrap()
});

static DAILYMOTION_PATH_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^video/[^/]+").unwrap()
});

static COUB_PATH_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^view/[^/]+").unwrap()
});

static SNAPCHAT_PATH_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^spotlight/[^/]+").unwrap()
});

static TUMBLR_PATH_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"(?:^|/)\d{5,}(?:/|$)").unwrap()
});

static TIKTOK_DOMAINS: LazyLock<HashSet<&'static str>> = LazyLock::new(|| {
    HashSet::from([
        "tiktok.com",
        "www.tiktok.com",
        "m.tiktok.com",
        "vm.tiktok.com",
        "vt.tiktok.com",
    ])
});

static YOUTUBE_DOMAINS: LazyLock<HashSet<&'static str>> = LazyLock::new(|| {
    HashSet::from([
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
    ])
});

static INSTAGRAM_DOMAINS: LazyLock<HashSet<&'static str>> = LazyLock::new(|| {
    HashSet::from(["instagram.com", "www.instagram.com"])
});

static VK_DOMAINS: LazyLock<HashSet<&'static str>> = LazyLock::new(|| {
    HashSet::from([
        "vk.com",
        "m.vk.com",
        "vk.ru",
        "m.vk.ru",
        "vkvideo.ru",
        "www.vkvideo.ru",
    ])
});

static OTHER_DOMAINS: LazyLock<HashSet<&'static str>> = LazyLock::new(|| {
    HashSet::from([
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
    ])
});

static TRACKING_KEYS: LazyLock<HashSet<&'static str>> = LazyLock::new(|| {
    HashSet::from([
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
    ])
});

pub struct URLParser;

impl URLParser {
    fn host_matches(hostname: &str, domains: &HashSet<&'static str>) -> bool {
        let h = hostname.to_lowercase();
        domains
            .iter()
            .any(|&d| h == d || h.ends_with(&format!(".{d}")))
    }

    pub fn detect_platform(url_str: &str) -> Option<Platform> {
        let parsed = Url::parse(url_str).ok()?;
        let host = parsed.host_str()?.to_lowercase();

        if Self::host_matches(&host, &TIKTOK_DOMAINS) {
            return Some(Platform::TikTok);
        }
        if Self::host_matches(&host, &YOUTUBE_DOMAINS) {
            return Some(Platform::YouTubeShorts);
        }
        if Self::host_matches(&host, &INSTAGRAM_DOMAINS) {
            return Some(Platform::InstagramReels);
        }
        if Self::host_matches(&host, &VK_DOMAINS) {
            return Some(Platform::Vk);
        }
        if Self::host_matches(&host, &OTHER_DOMAINS) {
            return Some(Platform::Other);
        }
        None
    }

    fn valid_http_url(parsed: &Url, domains: &HashSet<&'static str>) -> bool {
        let scheme = parsed.scheme().to_lowercase();
        if scheme != "http" && scheme != "https" {
            return false;
        }
        if !parsed.username().is_empty() || parsed.password().is_some() {
            return false;
        }
        if let Some(port) = parsed.port() {
            if port != 80 && port != 443 {
                return false;
            }
        }
        let host = match parsed.host_str() {
            Some(h) => h.to_lowercase(),
            None => return false,
        };
        if !Self::host_matches(&host, domains) {
            return false;
        }
        let path = parsed.path().trim_matches('/');
        !path.is_empty()
    }

    pub fn is_valid_tiktok_url(url_str: &str) -> bool {
        let parsed = match Url::parse(url_str) {
            Ok(u) => u,
            Err(_) => return false,
        };
        if !Self::valid_http_url(&parsed, &TIKTOK_DOMAINS) {
            return false;
        }
        let host = parsed.host_str().unwrap_or("").to_lowercase();
        let path = parsed.path().trim_matches('/');

        if host == "vm.tiktok.com" || host == "vt.tiktok.com" {
            return !path.is_empty();
        }
        TIKTOK_PATH_RE.is_match(path)
    }

    pub fn is_valid_youtube_url(url_str: &str) -> bool {
        let parsed = match Url::parse(url_str) {
            Ok(u) => u,
            Err(_) => return false,
        };
        if !Self::valid_http_url(&parsed, &YOUTUBE_DOMAINS) {
            return false;
        }
        let host = parsed.host_str().unwrap_or("").to_lowercase();
        let path = parsed.path().trim_matches('/');

        if host == "youtu.be" {
            return !path.split('/').next().unwrap_or("").is_empty();
        }
        if path.eq_ignore_ascii_case("watch") {
            return parsed
                .query_pairs()
                .any(|(k, v)| k == "v" && !v.is_empty());
        }
        YT_SHORTS_RE.is_match(path)
    }

    pub fn is_valid_instagram_url(url_str: &str) -> bool {
        let parsed = match Url::parse(url_str) {
            Ok(u) => u,
            Err(_) => return false,
        };
        if !Self::valid_http_url(&parsed, &INSTAGRAM_DOMAINS) {
            return false;
        }
        let path = parsed.path().trim_matches('/');
        IG_PATH_RE.is_match(path)
    }

    pub fn is_valid_vk_url(url_str: &str) -> bool {
        let parsed = match Url::parse(url_str) {
            Ok(u) => u,
            Err(_) => return false,
        };
        if !Self::valid_http_url(&parsed, &VK_DOMAINS) {
            return false;
        }
        let path = parsed.path().trim_matches('/');
        if path.eq_ignore_ascii_case("video_ext.php") {
            return parsed.query().is_some();
        }
        if VK_VIDEOS_RE.is_match(path) {
            let z_val = parsed
                .query_pairs()
                .find(|(k, _)| k == "z")
                .map(|(_, v)| v.to_string())
                .unwrap_or_default();
            return VK_EMBEDDED_RE.is_match(&z_val);
        }
        VK_PATH_RE.is_match(path)
    }

    pub fn is_valid_other_url(url_str: &str) -> bool {
        let parsed = match Url::parse(url_str) {
            Ok(u) => u,
            Err(_) => return false,
        };
        if !Self::valid_http_url(&parsed, &OTHER_DOMAINS) {
            return false;
        }
        let host = parsed.host_str().unwrap_or("").to_lowercase();
        let path = parsed.path().trim_matches('/');

        if host.ends_with("x.com") || host.ends_with("twitter.com") {
            return X_PATH_RE.is_match(path);
        }
        if host == "fb.watch" {
            return !path.is_empty();
        }
        if host.ends_with("facebook.com") {
            return FB_PATH_RE.is_match(path)
                || (path == "watch"
                    && parsed
                        .query_pairs()
                        .any(|(k, v)| k == "v" && !v.is_empty()));
        }
        if host.ends_with("threads.net") {
            return THREADS_PATH_RE.is_match(path);
        }
        if host == "redd.it" {
            return !path.is_empty();
        }
        if host.ends_with("reddit.com") {
            return REDDIT_PATH_RE.is_match(path);
        }
        if host == "pin.it" {
            return !path.is_empty();
        }
        if host.ends_with("pinterest.com") {
            return PINTEREST_PATH_RE.is_match(path);
        }
        if host.ends_with("rutube.ru") {
            return RUTUBE_PATH_RE.is_match(path);
        }
        if host.ends_with("ok.ru") {
            return OK_PATH_RE.is_match(path);
        }
        if host == "clips.twitch.tv" {
            return !path.is_empty();
        }
        if host.ends_with("twitch.tv") {
            return TWITCH_PATH_RE.is_match(path);
        }
        if host.ends_with("vimeo.com") {
            return VIMEO_PATH_RE.is_match(path);
        }
        if host == "dai.ly" {
            return !path.is_empty();
        }
        if host.ends_with("dailymotion.com") {
            return DAILYMOTION_PATH_RE.is_match(path);
        }
        if host.ends_with("likee.video") {
            return !path.is_empty();
        }
        if host.ends_with("coub.com") {
            return COUB_PATH_RE.is_match(path);
        }
        if host.ends_with("streamable.com") {
            return !path.is_empty();
        }
        if host.ends_with("snapchat.com") {
            return SNAPCHAT_PATH_RE.is_match(path);
        }
        if host.ends_with("tumblr.com") {
            return TUMBLR_PATH_RE.is_match(path);
        }
        false
    }

    pub fn normalize_url(url_str: &str) -> String {
        let mut parsed = match Url::parse(url_str) {
            Ok(u) => u,
            Err(_) => return url_str.to_string(),
        };

        let host = parsed.host_str().unwrap_or("").to_lowercase();
        let path = parsed.path().to_string();

        if Self::host_matches(&host, &INSTAGRAM_DOMAINS) {
            let mut normalized_path = path;
            if !normalized_path.ends_with('/') {
                normalized_path.push('/');
            }
            return format!("https://www.instagram.com{normalized_path}");
        }

        if host == "youtu.be" {
            return format!("https://youtu.be{path}");
        }

        if Self::host_matches(&host, &YOUTUBE_DOMAINS) {
            if path.eq_ignore_ascii_case("/watch") {
                if let Some((_, vid)) = parsed.query_pairs().find(|(k, _)| k == "v") {
                    return format!("https://www.youtube.com/watch?v={vid}");
                }
            }
            if path.to_lowercase().starts_with("/shorts/") {
                let parts: Vec<&str> = path.split('/').collect();
                if parts.len() > 2 {
                    return format!("https://www.youtube.com/shorts/{}", parts[2]);
                }
            }
        }

        // Clean tracking query parameters
        let pairs: Vec<(String, String)> = parsed
            .query_pairs()
            .filter(|(k, _)| {
                let lower = k.to_lowercase();
                !TRACKING_KEYS.contains(lower.as_str()) && !lower.starts_with("utm_")
            })
            .map(|(k, v)| (k.to_string(), v.to_string()))
            .collect();

        parsed.set_query(None);
        if !pairs.is_empty() {
            let mut serializer = form_urlencoded::Serializer::new(String::new());
            for (k, v) in pairs {
                serializer.append_pair(&k, &v);
            }
            parsed.set_query(Some(&serializer.finish()));
        }

        let _ = parsed.set_scheme("https");
        parsed.to_string()
    }

    pub fn extract_and_validate(text: &str) -> Option<ParsedUrl> {
        if text.trim().is_empty() {
            return None;
        }

        for mat in URL_REGEX.find_iter(text) {
            let raw = mat.as_str().trim_end_matches([
                '.', ',', ';', ':', '!', '?', ')', ']', '}', '>', '»', '”', '’',
            ]);
            if let Some(platform) = Self::detect_platform(raw) {
                let is_valid = match platform {
                    Platform::TikTok => Self::is_valid_tiktok_url(raw),
                    Platform::YouTubeShorts => Self::is_valid_youtube_url(raw),
                    Platform::InstagramReels => Self::is_valid_instagram_url(raw),
                    Platform::Vk => Self::is_valid_vk_url(raw),
                    Platform::Other => Self::is_valid_other_url(raw),
                };
                if is_valid {
                    return Some(ParsedUrl {
                        platform,
                        original_url: raw.to_string(),
                        normalized_url: Self::normalize_url(raw),
                    });
                }
            }
        }
        None
    }

    pub fn is_pure_link_message(text: &str) -> bool {
        let Some(parsed) = Self::extract_and_validate(text) else {
            return false;
        };
        let cleaned = text.replace(&parsed.original_url, "");
        cleaned.trim().is_empty()
    }
}
