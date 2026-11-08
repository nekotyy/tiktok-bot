#![allow(dead_code)]

use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct User {
    pub user_id: i64,
    pub username: Option<String>,
    pub first_name: Option<String>,
    pub last_name: Option<String>,
    pub created_at: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct DownloadRecord {
    pub id: i64,
    pub user_id: i64,
    pub video_url: String,
    pub file_size: Option<i64>,
    pub duration: Option<i64>,
    pub success: bool,
    pub error_message: Option<String>,
    pub created_at: String,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct UserStats {
    pub total_downloads: i64,
    pub total_size: i64,
    pub last_download_at: Option<String>,
    pub member_since: Option<String>,
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
pub struct GlobalStats {
    pub total_users: i64,
    pub total_downloads: i64,
    pub total_size: i64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct TopUser {
    pub user_id: i64,
    pub total_downloads: i64,
    pub total_size: i64,
    pub last_download_at: Option<String>,
    pub username: Option<String>,
    pub first_name: Option<String>,
    pub last_name: Option<String>,
}

impl TopUser {
    pub fn display_name(&self) -> String {
        if let Some(ref u) = self.username {
            if !u.trim().is_empty() {
                return format!("@{u}");
            }
        }
        let first = self.first_name.as_deref().unwrap_or("").trim();
        let last = self.last_name.as_deref().unwrap_or("").trim();
        let full = format!("{first} {last}").trim().to_string();
        if !full.is_empty() {
            return full;
        }
        self.user_id.to_string()
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ChatSettings {
    pub chat_id: i64,
    pub require_pure_link: bool,
    pub delete_source_messages: bool,
    pub updated_at: Option<String>,
}

impl Default for ChatSettings {
    fn default() ->  Self {
        Self {
            chat_id: 0,
            require_pure_link: false,
            delete_source_messages: true,
            updated_at: None,
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CachedFile {
    pub url: String,
    pub file_id: String,
    pub media_type: String,
    pub title: Option<String>,
    pub file_size: Option<u64>,
    pub duration: Option<u64>,
}
