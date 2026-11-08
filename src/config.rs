use std::collections::HashSet;
use std::env;
use std::path::{Path, PathBuf};

#[derive(Clone, Debug)]
#[allow(dead_code)]
pub struct Config {
    pub bot_token: String,
    pub admin_id: i64,
    pub cache_channel_id: i64,
    pub allowed_chat_ids: HashSet<i64>,
    pub auto_allow_member_chats: bool,
    pub max_file_size_mb: u64,
    pub max_file_size_bytes: u64,
    pub file_cleanup_interval: u64,
    pub database_path: PathBuf,
    pub downloads_path: PathBuf,
    pub ytdlp_proxy: Option<String>,
    pub ytdlp_impersonate: Option<String>,
    pub rate_limit_requests: usize,
    pub rate_limit_period_secs: u64,
}

impl Config {
    pub fn load() -> anyhow::Result<Self> {
        let _ = dotenvy::dotenv();

        let bot_token = env::var("BOT_TOKEN").unwrap_or_default().trim().to_string();
        if bot_token.is_empty() || bot_token == "your_bot_token_here" {
            anyhow::bail!("BOT_TOKEN is not set or empty in .env file");
        }

        let admin_id = Self::get_i64_env("ADMIN_ID", 0);
        let cache_channel_id = Self::get_i64_env("CACHE_CHANNEL_ID", 0);

        let allowed_chat_ids = Self::parse_id_list(&env::var("ALLOWED_CHAT_IDS").unwrap_or_default());

        let auto_allow_member_chats = env::var("AUTO_ALLOW_MEMBER_CHATS")
            .map(|val| {
                let v = val.trim().to_lowercase();
                v == "1" || v == "true" || v == "yes"
            })
            .unwrap_or(true);

        let max_file_size_mb = Self::get_u64_env("MAX_FILE_SIZE_MB", 50);
        let max_file_size_bytes = max_file_size_mb * 1024 * 1024;

        let file_cleanup_interval = Self::get_u64_env("FILE_CLEANUP_INTERVAL", 10);

        let base_dir = env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
        let db_raw = env::var("DATABASE_PATH").unwrap_or_else(|_| "data/bot.db".to_string());
        let database_path = base_dir.join(Path::new(&db_raw));

        let dl_raw = env::var("DOWNLOADS_PATH").unwrap_or_else(|_| "downloads".to_string());
        let downloads_path = base_dir.join(Path::new(&dl_raw));

        let ytdlp_proxy = env::var("YTDLP_PROXY")
            .ok()
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty());

        let ytdlp_impersonate = env::var("YTDLP_IMPERSONATE")
            .ok()
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty());

        Ok(Self {
            bot_token,
            admin_id,
            cache_channel_id,
            allowed_chat_ids,
            auto_allow_member_chats,
            max_file_size_mb,
            max_file_size_bytes,
            file_cleanup_interval,
            database_path,
            downloads_path,
            ytdlp_proxy,
            ytdlp_impersonate,
            rate_limit_requests: 10,
            rate_limit_period_secs: 60,
        })
    }

    pub fn is_chat_allowed(&self, chat_id: i64) -> bool {
        if self.auto_allow_member_chats {
            return true;
        }
        if self.allowed_chat_ids.is_empty() {
            return true;
        }
        self.allowed_chat_ids.contains(&chat_id)
    }

    fn get_i64_env(name: &str, default: i64) -> i64 {
        env::var(name)
            .ok()
            .and_then(|v| v.trim().parse::<i64>().ok())
            .unwrap_or(default)
    }

    fn get_u64_env(name: &str, default: u64) -> u64 {
        env::var(name)
            .ok()
            .and_then(|v| v.trim().parse::<u64>().ok())
            .unwrap_or(default)
    }

    fn parse_id_list(raw: &str) -> HashSet<i64> {
        let mut ids = HashSet::new();
        let normalized = raw.replace('\n', ",").replace(';', ",").replace(' ', ",");
        for item in normalized.split(',') {
            let trimmed = item.trim();
            if let Ok(id) = trimmed.parse::<i64>() {
                ids.insert(id);
            }
        }
        ids
    }
}
