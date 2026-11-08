use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime};
use tokio::time::sleep;
use tracing::{info, warn};

#[derive(Clone)]
pub struct FileManager {
    pub downloads_path: PathBuf,
    pub cleanup_interval_minutes: u64,
}

impl FileManager {
    pub fn new<P: AsRef<Path>>(downloads_path: P, cleanup_interval_minutes: u64) -> Self {
        let path = downloads_path.as_ref().to_path_buf();
        let _ = std::fs::create_dir_all(&path);
        Self {
            downloads_path: path,
            cleanup_interval_minutes,
        }
    }

    pub async fn delete_file<P: AsRef<Path>>(&self, file_path: P) -> bool {
        let path = file_path.as_ref();
        if path.exists() {
            match tokio::fs::remove_file(path).await {
                Ok(_) => {
                    info!("Deleted temporary file: {}", path.display());
                    true
                }
                Err(e) => {
                    warn!("Failed to delete file {}: {e}", path.display());
                    false
                }
            }
        } else {
            false
        }
    }

    pub async fn delete_files<P: AsRef<Path>>(&self, paths: &[P]) -> usize {
        let mut count = 0;
        for p in paths {
            if self.delete_file(p).await {
                count += 1;
            }
        }
        count
    }

    pub async fn cleanup_all_temp_files(&self) -> usize {
        let mut deleted = 0;
        let mut read_dir = match tokio::fs::read_dir(&self.downloads_path).await {
            Ok(rd) => rd,
            Err(e) => {
                warn!("Cannot read downloads directory: {e}");
                return 0;
            }
        };

        while let Ok(Some(entry)) = read_dir.next_entry().await {
            let path = entry.path();
            if let Some(file_name) = path.file_name().and_then(|n| n.to_str()) {
                if file_name.starts_with('.') || file_name == ".gitkeep" {
                    continue;
                }
            }
            if path.is_file() {
                if tokio::fs::remove_file(&path).await.is_ok() {
                    deleted += 1;
                }
            }
        }
        deleted
    }

    pub async fn cleanup_old_files(&self) -> usize {
        let mut deleted = 0;
        let max_age = Duration::from_secs(self.cleanup_interval_minutes * 60);
        let now = SystemTime::now();

        let mut read_dir = match tokio::fs::read_dir(&self.downloads_path).await {
            Ok(rd) => rd,
            Err(e) => {
                warn!("Cannot read downloads directory during cleanup: {e}");
                return 0;
            }
        };

        while let Ok(Some(entry)) = read_dir.next_entry().await {
            let path = entry.path();
            if let Some(file_name) = path.file_name().and_then(|n| n.to_str()) {
                if file_name.starts_with('.') || file_name == ".gitkeep" {
                    continue;
                }
            }

            if let Ok(metadata) = entry.metadata().await {
                if metadata.is_file() {
                    if let Ok(modified) = metadata.modified() {
                        if let Ok(age) = now.duration_since(modified) {
                            if age > max_age {
                                if tokio::fs::remove_file(&path).await.is_ok() {
                                    deleted += 1;
                                    info!("Cleaned up old file: {}", path.display());
                                }
                            }
                        }
                    }
                }
            }
        }

        deleted
    }

    pub async fn get_directory_size(&self) -> u64 {
        let mut total = 0;
        if let Ok(mut read_dir) = tokio::fs::read_dir(&self.downloads_path).await {
            while let Ok(Some(entry)) = read_dir.next_entry().await {
                if let Ok(meta) = entry.metadata().await {
                    if meta.is_file() {
                        total += meta.len();
                    }
                }
            }
        }
        total
    }

    pub async fn get_file_count(&self) -> usize {
        let mut count = 0;
        if let Ok(mut read_dir) = tokio::fs::read_dir(&self.downloads_path).await {
            while let Ok(Some(entry)) = read_dir.next_entry().await {
                if let Ok(meta) = entry.metadata().await {
                    if meta.is_file() {
                        count += 1;
                    }
                }
            }
        }
        count
    }

    pub fn start_cleanup_task(&self, interval_minutes: u64) {
        let fm = self.clone();
        tokio::spawn(async move {
            info!("File manager background cleanup task started (runs every {interval_minutes}m)");
            loop {
                sleep(Duration::from_secs(interval_minutes * 60)).await;
                let deleted = fm.cleanup_old_files().await;
                if deleted > 0 {
                    let size = fm.get_directory_size().await;
                    let count = fm.get_file_count().await;
                    info!(
                        "Cleanup stats: {deleted} files deleted, {count} files remaining ({:.1} MB)",
                        size as f64 / (1024.0 * 1024.0)
                    );
                }
            }
        });
    }
}
