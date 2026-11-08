use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};
use teloxide::prelude::*;
use teloxide::types::{
    ChatId, InlineQuery, InlineQueryResult, InlineQueryResultCachedPhoto,
    InlineQueryResultCachedVideo, InlineQueryResultsButton, InlineQueryResultsButtonKind,
    InputFile,
};
use tracing::{error, info};

use crate::config::Config;
use crate::db::Database;
use crate::services::downloader::{DownloadedMedia, MediaDownloader};
use crate::services::file_manager::FileManager;
use crate::services::rate_limiter::RateLimiter;
use crate::services::url_parser::URLParser;
use crate::utils::formatters::format_file_size;

fn pm_button(text: &str, param: &str) -> InlineQueryResultsButton {
    InlineQueryResultsButton {
        text: text.to_string(),
        kind: InlineQueryResultsButtonKind::StartParameter(param.to_string()),
    }
}

pub async fn handle_inline_query(
    bot: Bot,
    q: InlineQuery,
    config: Arc<Config>,
    db: Arc<Database>,
    downloader: Arc<MediaDownloader>,
    file_manager: Arc<FileManager>,
    rate_limiter: Arc<RateLimiter>,
) -> anyhow::Result<()> {
    let query_text = q.query.trim().to_string();
    let user_id = q.from.id.0 as i64;

    if !rate_limiter.check_and_record(user_id) {
        let _ = bot
            .answer_inline_query(q.id, vec![])
            .cache_time(1)
            .is_personal(true)
            .button(pm_button("⚠️ Слишком много запросов", "rate_limit"))
            .await;
        return Ok(());
    }

    if query_text.is_empty() {
        let _ = bot
            .answer_inline_query(q.id, vec![])
            .cache_time(1)
            .is_personal(true)
            .button(pm_button(
                "📝 Вставьте ссылку на видео или публикацию",
                "start",
            ))
            .await;
        return Ok(());
    }

    let parsed = match URLParser::extract_and_validate(&query_text) {
        Some(p) => p,
        None => {
            let _ = bot
                .answer_inline_query(q.id, vec![])
                .cache_time(1)
                .is_personal(true)
                .button(pm_button(
                    "❌ Эта ссылка не поддерживается",
                    "invalid_url",
                ))
                .await;
            return Ok(());
        }
    };

    let username = q.from.username.clone();
    let first_name = Some(q.from.first_name.clone());
    let last_name = q.from.last_name.clone();
    db.add_user(user_id, username, first_name, last_name).await;

    let platform_label = parsed.platform.display_label();
    info!("Inline query from {user_id}: {platform_label} -> {}", parsed.normalized_url);

    let cache_chat: ChatId = if config.cache_channel_id != 0 {
        ChatId(config.cache_channel_id)
    } else {
        ChatId(user_id)
    };

    let download_res = downloader
        .download_media(parsed.platform, &parsed.normalized_url)
        .await;

    let media = match download_res {
        Ok(m) => m,
        Err(err_msg) => {
            let short_err = if err_msg.len() > 30 {
                format!("{}...", &err_msg[..30])
            } else {
                err_msg.clone()
            };

            let _ = bot
                .answer_inline_query(q.id, vec![])
                .cache_time(1)
                .is_personal(true)
                .button(pm_button(&format!("❌ Ошибка: {short_err}"), "error"))
                .await;

            db.log_download(
                user_id,
                parsed.normalized_url,
                false,
                None,
                None,
                Some(err_msg),
            )
            .await;
            return Ok(());
        }
    };

    let file_size = media.file_size();
    let duration = media.duration();
    let title = media.title().to_string();
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();

    match media {
        DownloadedMedia::Video { file_path, .. } => {
            let send_res = bot
                .send_video(cache_chat, InputFile::file(&file_path))
                .supports_streaming(true)
                .await;

            file_manager.delete_file(&file_path).await;

            let sent_msg = match send_res {
                Ok(m) => m,
                Err(e) => {
                    error!("Failed to upload video for inline caching: {e}");
                    let _ = bot
                        .answer_inline_query(q.id, vec![])
                        .cache_time(1)
                        .is_personal(true)
                        .button(pm_button("❌ Ошибка загрузки", "error"))
                        .await;
                    return Ok(());
                }
            };

            let file_id = sent_msg
                .video()
                .map(|v| v.file.id.clone())
                .unwrap_or_default();

            if cache_chat.0 == user_id {
                let _ = bot.delete_message(cache_chat, sent_msg.id).await;
            }

            let result_id = format!("{user_id}_{timestamp}");
            let dur_str = duration
                .map(|d| format!(" • ⏱ {d}с"))
                .unwrap_or_default();

            let cached_video = InlineQueryResultCachedVideo::new(
                result_id,
                file_id,
                format!("🎬 {}", &title.chars().take(50).collect::<String>()),
            )
            .description(format!("📦 {}{dur_str}", format_file_size(file_size)));

            let _ = bot
                .answer_inline_query(q.id, vec![InlineQueryResult::CachedVideo(cached_video)])
                .cache_time(300)
                .is_personal(true)
                .await;
        }
        DownloadedMedia::Photos { ref file_paths, .. }
        | DownloadedMedia::Album { ref file_paths, .. } => {
            let mut results = Vec::new();

            for (idx, fp) in file_paths.iter().take(10).enumerate() {
                let is_photo = fp
                    .extension()
                    .and_then(|e| e.to_str())
                    .map(|e| !e.eq_ignore_ascii_case("mp4") && !e.eq_ignore_ascii_case("mov"))
                    .unwrap_or(true);

                let item_num = idx + 1;
                let total_items = file_paths.len();

                if is_photo {
                    if let Ok(sent_msg) = bot.send_photo(cache_chat, InputFile::file(fp)).await {
                        if let Some(photo) = sent_msg.photo().and_then(|p| p.last()) {
                            let file_id = photo.file.id.clone();
                            if cache_chat.0 == user_id {
                                let _ = bot.delete_message(cache_chat, sent_msg.id).await;
                            }
                            let res_id = format!("{user_id}_photo_{item_num}_{timestamp}");
                            let cached = InlineQueryResultCachedPhoto::new(res_id, file_id)
                                .title(format!("📷 {item_num}/{total_items}"))
                                .description(format!("{title} ({item_num})"));
                            results.push(InlineQueryResult::CachedPhoto(cached));
                        }
                    }
                } else if let Ok(sent_msg) = bot
                    .send_video(cache_chat, InputFile::file(fp))
                    .supports_streaming(true)
                    .await
                {
                    if let Some(vid) = sent_msg.video() {
                        let file_id = vid.file.id.clone();
                        if cache_chat.0 == user_id {
                            let _ = bot.delete_message(cache_chat, sent_msg.id).await;
                        }
                        let res_id = format!("{user_id}_video_{item_num}_{timestamp}");
                        let cached = InlineQueryResultCachedVideo::new(
                            res_id,
                            file_id,
                            format!("🎬 {item_num}/{total_items}"),
                        )
                        .description(format!("{title} ({item_num})"));
                        results.push(InlineQueryResult::CachedVideo(cached));
                    }
                }
            }

            file_manager.delete_files(file_paths).await;

            let _ = bot
                .answer_inline_query(q.id, results)
                .cache_time(300)
                .is_personal(true)
                .await;
        }
    }

    db.log_download(
        user_id,
        parsed.normalized_url,
        true,
        Some(file_size as i64),
        duration.map(|d| d as i64),
        None,
    )
    .await;

    Ok(())
}
