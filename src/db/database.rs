use std::path::Path;
use std::sync::{Arc, Mutex};
use rusqlite::{params, Connection};
use tracing::{error, info};

use crate::db::models::{CachedFile, ChatSettings, GlobalStats, TopUser, UserStats};

const SCHEMA: &str = r#"
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    video_url TEXT NOT NULL,
    file_size INTEGER,
    duration INTEGER,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (user_id)
);

CREATE TABLE IF NOT EXISTS statistics (
    user_id INTEGER PRIMARY KEY,
    total_downloads INTEGER DEFAULT 0,
    total_size INTEGER DEFAULT 0,
    last_download_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (user_id)
);

CREATE TABLE IF NOT EXISTS chat_settings (
    chat_id INTEGER PRIMARY KEY,
    require_pure_link BOOLEAN NOT NULL DEFAULT 0,
    delete_source_messages BOOLEAN NOT NULL DEFAULT 1,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS file_cache (
    url TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    media_type TEXT NOT NULL DEFAULT 'video',
    title TEXT,
    file_size INTEGER,
    duration INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_downloads_user_id ON downloads(user_id);
CREATE INDEX IF NOT EXISTS idx_downloads_created_at ON downloads(created_at);
CREATE INDEX IF NOT EXISTS idx_statistics_user_id ON statistics(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_settings_chat_id ON chat_settings(chat_id);
CREATE INDEX IF NOT EXISTS idx_file_cache_url ON file_cache(url);
"#;

#[derive(Clone)]
pub struct Database {
    conn: Arc<Mutex<Connection>>,
}

impl Database {
    pub fn new<P: AsRef<Path>>(path: P) -> anyhow::Result<Self> {
        let path_ref = path.as_ref();
        if let Some(parent) = path_ref.parent() {
            std::fs::create_dir_all(parent)?;
        }

        let conn = Connection::open(path_ref)?;

        // WAL mode for maximum performance and concurrency
        conn.execute_batch(
            r#"
            PRAGMA journal_mode = WAL;
            PRAGMA synchronous = NORMAL;
            PRAGMA foreign_keys = ON;
            "#,
        )?;

        let db = Self {
            conn: Arc::new(Mutex::new(conn)),
        };
        db.init_db()?;
        Ok(db)
    }

    pub fn init_db(&self) -> anyhow::Result<()> {
        let conn = self.conn.lock().unwrap();
        conn.execute_batch(SCHEMA)?;
        info!("Database schema verified successfully");
        Ok(())
    }

    pub async fn add_user(
        &self,
        user_id: i64,
        username: Option<String>,
        first_name: Option<String>,
        last_name: Option<String>,
    ) -> bool {
        let conn = Arc::clone(&self.conn);
        tokio::task::spawn_blocking(move || {
            let conn = conn.lock().unwrap();
            let res = conn.execute(
                r#"
                INSERT INTO users (user_id, username, first_name, last_name)
                VALUES (?1, ?2, ?3, ?4)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    last_name = excluded.last_name
                "#,
                params![user_id, username, first_name, last_name],
            );
            match res {
                Ok(_) => true,
                Err(e) => {
                    error!("Failed to add user {user_id}: {e}");
                    false
                }
            }
        })
        .await
        .unwrap_or(false)
    }

    pub async fn log_download(
        &self,
        user_id: i64,
        video_url: String,
        success: bool,
        file_size: Option<i64>,
        duration: Option<i64>,
        error_message: Option<String>,
    ) -> bool {
        let conn = Arc::clone(&self.conn);
        tokio::task::spawn_blocking(move || {
            let mut conn = conn.lock().unwrap();
            let tx = match conn.transaction() {
                Ok(t) => t,
                Err(e) => {
                    error!("Failed to start transaction: {e}");
                    return false;
                }
            };

            let res = tx.execute(
                r#"
                INSERT INTO downloads (user_id, video_url, success, file_size, duration, error_message)
                VALUES (?1, ?2, ?3, ?4, ?5, ?6)
                "#,
                params![
                    user_id,
                    video_url,
                    success,
                    file_size,
                    duration,
                    error_message
                ],
            );

            if let Err(e) = res {
                error!("Failed to log download for user {user_id}: {e}");
                return false;
            }

            if success {
                let size_val = file_size.unwrap_or(0);
                let stat_res = tx.execute(
                    r#"
                    INSERT INTO statistics (user_id, total_downloads, total_size, last_download_at)
                    VALUES (?1, 1, ?2, CURRENT_TIMESTAMP)
                    ON CONFLICT(user_id) DO UPDATE SET
                        total_downloads = total_downloads + 1,
                        total_size = total_size + ?2,
                        last_download_at = CURRENT_TIMESTAMP
                    "#,
                    params![user_id, size_val],
                );
                if let Err(e) = stat_res {
                    error!("Failed to update stats for user {user_id}: {e}");
                    return false;
                }
            }

            if let Err(e) = tx.commit() {
                error!("Failed to commit log_download transaction: {e}");
                return false;
            }
            true
        })
        .await
        .unwrap_or(false)
    }

    pub async fn get_user_stats(&self, user_id: i64) -> Option<UserStats> {
        let conn = Arc::clone(&self.conn);
        tokio::task::spawn_blocking(move || {
            let conn = conn.lock().unwrap();
            let mut stmt = conn
                .prepare(
                    r#"
                    SELECT 
                        s.total_downloads,
                        s.total_size,
                        s.last_download_at,
                        u.created_at
                    FROM statistics s
                    LEFT JOIN users u ON s.user_id = u.user_id
                    WHERE s.user_id = ?1
                    "#,
                )
                .ok()?;

            let mut rows = stmt.query(params![user_id]).ok()?;
            if let Some(row) = rows.next().ok().flatten() {
                Some(UserStats {
                    total_downloads: row.get(0).unwrap_or(0),
                    total_size: row.get(1).unwrap_or(0),
                    last_download_at: row.get(2).ok(),
                    member_since: row.get(3).ok(),
                })
            } else {
                Some(UserStats {
                    total_downloads: 0,
                    total_size: 0,
                    last_download_at: None,
                    member_since: None,
                })
            }
        })
        .await
        .unwrap_or(None)
    }

    #[allow(dead_code)]
    pub async fn get_global_stats(&self) -> Option<GlobalStats> {
        let conn = Arc::clone(&self.conn);
        tokio::task::spawn_blocking(move || {
            let conn = conn.lock().unwrap();
            let mut stmt = conn
                .prepare(
                    r#"
                    SELECT 
                        COUNT(DISTINCT user_id) as total_users,
                        COALESCE(SUM(total_downloads), 0) as total_downloads,
                        COALESCE(SUM(total_size), 0) as total_size
                    FROM statistics
                    "#,
                )
                .ok()?;

            let mut rows = stmt.query([]).ok()?;
            if let Some(row) = rows.next().ok().flatten() {
                Some(GlobalStats {
                    total_users: row.get(0).unwrap_or(0),
                    total_downloads: row.get(1).unwrap_or(0),
                    total_size: row.get(2).unwrap_or(0),
                })
            } else {
                Some(GlobalStats::default())
            }
        })
        .await
        .unwrap_or(None)
    }

    pub async fn get_top_users(&self, limit: usize) -> Vec<TopUser> {
        let conn = Arc::clone(&self.conn);
        tokio::task::spawn_blocking(move || {
            let conn = conn.lock().unwrap();
            let mut stmt = match conn.prepare(
                r#"
                SELECT
                    s.user_id,
                    s.total_downloads,
                    s.total_size,
                    s.last_download_at,
                    u.username,
                    u.first_name,
                    u.last_name
                FROM statistics s
                LEFT JOIN users u ON s.user_id = u.user_id
                ORDER BY s.total_downloads DESC, s.total_size DESC, s.last_download_at DESC
                LIMIT ?1
                "#,
            ) {
                Ok(s) => s,
                Err(e) => {
                    error!("Failed to prepare get_top_users: {e}");
                    return Vec::new();
                }
            };

            let rows = match stmt.query_map(params![limit as i64], |row| {
                Ok(TopUser {
                    user_id: row.get(0)?,
                    total_downloads: row.get(1)?,
                    total_size: row.get(2)?,
                    last_download_at: row.get(3)?,
                    username: row.get(4)?,
                    first_name: row.get(5)?,
                    last_name: row.get(6)?,
                })
            }) {
                Ok(iter) => iter,
                Err(e) => {
                    error!("Failed to execute get_top_users query: {e}");
                    return Vec::new();
                }
            };

            rows.filter_map(|r| r.ok()).collect()
        })
        .await
        .unwrap_or_default()
    }

    pub async fn get_chat_settings(&self, chat_id: i64) -> ChatSettings {
        let conn = Arc::clone(&self.conn);
        tokio::task::spawn_blocking(move || {
            let conn = conn.lock().unwrap();
            let mut stmt = match conn.prepare(
                "SELECT chat_id, require_pure_link, delete_source_messages, updated_at FROM chat_settings WHERE chat_id = ?1",
            ) {
                Ok(s) => s,
                Err(_) => return ChatSettings { chat_id, ..Default::default() },
            };

            let mut rows = match stmt.query(params![chat_id]) {
                Ok(r) => r,
                Err(_) => return ChatSettings { chat_id, ..Default::default() },
            };

            if let Some(row) = rows.next().ok().flatten() {
                ChatSettings {
                    chat_id: row.get(0).unwrap_or(chat_id),
                    require_pure_link: row.get::<_, i64>(1).unwrap_or(0) != 0,
                    delete_source_messages: row.get::<_, i64>(2).unwrap_or(1) != 0,
                    updated_at: row.get(3).ok(),
                }
            } else {
                ChatSettings {
                    chat_id,
                    ..Default::default()
                }
            }
        })
        .await
        .unwrap_or_else(|_| ChatSettings {
            chat_id,
            ..Default::default()
        })
    }

    pub async fn set_chat_setting(
        &self,
        chat_id: i64,
        require_pure_link: Option<bool>,
        delete_source_messages: Option<bool>,
    ) -> bool {
        let current = self.get_chat_settings(chat_id).await;
        let new_require = require_pure_link.unwrap_or(current.require_pure_link);
        let new_delete = delete_source_messages.unwrap_or(current.delete_source_messages);

        let conn = Arc::clone(&self.conn);
        tokio::task::spawn_blocking(move || {
            let conn = conn.lock().unwrap();
            let res = conn.execute(
                r#"
                INSERT INTO chat_settings (chat_id, require_pure_link, delete_source_messages, updated_at)
                VALUES (?1, ?2, ?3, CURRENT_TIMESTAMP)
                ON CONFLICT(chat_id) DO UPDATE SET
                    require_pure_link = excluded.require_pure_link,
                    delete_source_messages = excluded.delete_source_messages,
                    updated_at = excluded.updated_at
                "#,
                params![chat_id, new_require as i64, new_delete as i64],
            );
            match res {
                Ok(_) => true,
                Err(e) => {
                    error!("Failed to set chat settings for {chat_id}: {e}");
                    false
                }
            }
        })
        .await
        .unwrap_or(false)
    }

    pub async fn get_cached_file(&self, url: &str) -> Option<CachedFile> {
        let conn = Arc::clone(&self.conn);
        let u = url.to_string();
        tokio::task::spawn_blocking(move || {
            let conn = conn.lock().unwrap();
            let mut stmt = conn
                .prepare(
                    "SELECT url, file_id, media_type, title, file_size, duration FROM file_cache WHERE url = ?1 LIMIT 1",
                )
                .ok()?;
            stmt.query_row(params![u], |row| {
                let file_size: Option<i64> = row.get(4)?;
                let duration: Option<i64> = row.get(5)?;
                Ok(CachedFile {
                    url: row.get(0)?,
                    file_id: row.get(1)?,
                    media_type: row.get(2)?,
                    title: row.get(3)?,
                    file_size: file_size.map(|s| s as u64),
                    duration: duration.map(|d| d as u64),
                })
            })
            .ok()
        })
        .await
        .unwrap_or(None)
    }

    pub async fn save_cached_file(
        &self,
        url: &str,
        file_id: &str,
        media_type: &str,
        title: Option<&str>,
        file_size: Option<u64>,
        duration: Option<u64>,
    ) {
        let conn = Arc::clone(&self.conn);
        let u = url.to_string();
        let fid = file_id.to_string();
        let mt = media_type.to_string();
        let t = title.map(|s| s.to_string());
        let fs = file_size.map(|s| s as i64);
        let dur = duration.map(|d| d as i64);

        let _ = tokio::task::spawn_blocking(move || {
            let conn = conn.lock().unwrap();
            let _ = conn.execute(
                r#"
                INSERT INTO file_cache (url, file_id, media_type, title, file_size, duration)
                VALUES (?1, ?2, ?3, ?4, ?5, ?6)
                ON CONFLICT(url) DO UPDATE SET
                    file_id = excluded.file_id,
                    media_type = excluded.media_type,
                    title = COALESCE(excluded.title, file_cache.title),
                    file_size = COALESCE(excluded.file_size, file_cache.file_size),
                    duration = COALESCE(excluded.duration, file_cache.duration),
                    created_at = CURRENT_TIMESTAMP
                "#,
                params![u, fid, mt, t, fs, dur],
            );
        })
        .await;
    }
}
