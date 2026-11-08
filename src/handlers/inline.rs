use std::sync::Arc;
use std::time::Duration;
use teloxide::prelude::*;
use teloxide::types::{
    ChatId, FileId, InlineQuery, InlineQueryId, InlineQueryResult, InlineQueryResultArticle,
    InlineQueryResultCachedPhoto, InlineQueryResultCachedVideo, InlineQueryResultsButton,
    InlineQueryResultsButtonKind, InputFile, InputMessageContent, InputMessageContentText,
};
use tracing::{info, warn};

use crate::config::Config;
use crate::db::models::CachedFile;
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

    // 1. FAST-PATH: Check database file cache first (< 5ms response)
    if let Some(cached) = db.get_cached_file(&parsed.normalized_url).await {
        if answer_with_cached(&bot, q.id.clone(), &cached).await {
            db.log_download(
                user_id,
                parsed.normalized_url,
                true,
                cached.file_size.map(|s| s as i64),
                cached.duration.map(|d| d as i64),
                None,
            )
            .await;
            return Ok(());
        }
    }

    // 2. Wrap download + upload in a 5.5-second timeout to prevent Telegram from dropping the query
    let dl = Arc::clone(&downloader);
    let fm = Arc::clone(&file_manager);
    let b = bot.clone();
    let cfg = Arc::clone(&config);
    let target_url = parsed.normalized_url.clone();
    let platform = parsed.platform;

    let download_fut = async move {
        let res = dl.download_media(platform, &target_url).await.ok()?;
        upload_to_cache(&b, &cfg, user_id, &res, &fm).await
    };

    match tokio::time::timeout(Duration::from_millis(5500), download_fut).await {
        Ok(Some(uploaded)) => {
            // Save to database cache
            match uploaded {
                UploadedCache::Video {
                    ref file_id,
                    ref title,
                    file_size,
                    duration,
                } => {
                    db.save_cached_file(
                        &parsed.normalized_url,
                        file_id,
                        "video",
                        Some(title),
                        Some(file_size),
                        duration,
                    )
                    .await;

                    let res_id = format!("v_{}", &file_id[..file_id.len().min(30)]);
                    let short_title = title.chars().take(50).collect::<String>();
                    let dur_str = duration.map(|d| format!(" • ⏱ {d}с")).unwrap_or_default();
                    let desc = format!("📦 {}{dur_str}", format_file_size(file_size));

                    let cached_video = InlineQueryResultCachedVideo::new(
                        res_id,
                        FileId(file_id.clone()),
                        format!("🎬 {short_title}"),
                    )
                    .description(desc)
                    .caption(format!("🎬 {title}\n\n🤖 Скачано через @luxsittbot"));

                    let _ = bot
                        .answer_inline_query(
                            q.id,
                            vec![InlineQueryResult::CachedVideo(cached_video)],
                        )
                        .cache_time(86400)
                        .is_personal(false)
                        .await;

                    db.log_download(
                        user_id,
                        parsed.normalized_url,
                        true,
                        Some(file_size as i64),
                        duration.map(|d| d as i64),
                        None,
                    )
                    .await;
                }
                UploadedCache::Photos {
                    ref file_ids,
                    ref title,
                    total_size,
                } => {
                    if let Some(first_id) = file_ids.first() {
                        db.save_cached_file(
                            &parsed.normalized_url,
                            first_id,
                            "photo",
                            Some(title),
                            Some(total_size),
                            None,
                        )
                        .await;
                    }

                    let results: Vec<InlineQueryResult> = file_ids
                        .iter()
                        .enumerate()
                        .map(|(idx, fid)| {
                            let item_num = idx + 1;
                            let res_id = format!("p_{idx}_{}", &fid[..fid.len().min(20)]);
                            let cached = InlineQueryResultCachedPhoto::new(res_id, FileId(fid.clone()))
                                .title(format!("📷 {item_num}/{}", file_ids.len()))
                                .description(format!("{title} ({item_num})"))
                                .caption(format!("{title}\n\n🤖 Скачано через @luxsittbot"));
                            InlineQueryResult::CachedPhoto(cached)
                        })
                        .collect();

                    let _ = bot
                        .answer_inline_query(q.id, results)
                        .cache_time(86400)
                        .is_personal(false)
                        .await;

                    db.log_download(
                        user_id,
                        parsed.normalized_url,
                        true,
                        Some(total_size as i64),
                        None,
                        None,
                    )
                    .await;
                }
            }
        }
        Ok(None) => {
            // Upload or download returned None
            let _ = bot
                .answer_inline_query(q.id, vec![])
                .cache_time(2)
                .is_personal(true)
                .button(pm_button(
                    "❌ Не удалось загрузить. Откройте бота в ЛС",
                    "start",
                ))
                .await;

            db.log_download(
                user_id,
                parsed.normalized_url,
                false,
                None,
                None,
                Some("Inline upload/download failed".to_string()),
            )
            .await;
        }
        Err(_timeout) => {
            // Timed out (> 5.5s) - Answer immediately so Telegram doesn't show an infinite dead spinner
            warn!("Inline query for {} exceeded 5.5s timeout. Answering processing card...", parsed.normalized_url);

            let article = InlineQueryResultArticle::new(
                "processing",
                format!("⏳ {platform_label}: Видео обрабатывается..."),
                InputMessageContent::Text(InputMessageContentText::new(format!(
                    "🎬 **{}**\n{}\n\n⏳ Видео скачивается на сервер. Нажмите повторно через пару секунд или откройте бота: @luxsittbot",
                    platform_label, parsed.normalized_url
                ))),
            )
            .description("Нажмите для отправки или повторите выбор через 2-3 секунды");

            let _ = bot
                .answer_inline_query(q.id, vec![InlineQueryResult::Article(article)])
                .cache_time(2)
                .is_personal(true)
                .button(pm_button(
                    "⏳ Видео обрабатывается... Открыть бота",
                    "start",
                ))
                .await;

            // Continue download & upload in background so next inline query is an instant cache hit
            let bg_dl = Arc::clone(&downloader);
            let bg_fm = Arc::clone(&file_manager);
            let bg_db = Arc::clone(&db);
            let bg_bot = bot.clone();
            let bg_cfg = Arc::clone(&config);
            let bg_url = parsed.normalized_url.clone();
            let bg_platform = parsed.platform;

            tokio::spawn(async move {
                if let Ok(media) = bg_dl.download_media(bg_platform, &bg_url).await {
                    if let Some(uploaded) = upload_to_cache(&bg_bot, &bg_cfg, user_id, &media, &bg_fm).await {
                        match uploaded {
                            UploadedCache::Video {
                                file_id,
                                title,
                                file_size,
                                duration,
                            } => {
                                bg_db.save_cached_file(
                                    &bg_url,
                                    &file_id,
                                    "video",
                                    Some(&title),
                                    Some(file_size),
                                    duration,
                                )
                                .await;
                                info!("Background inline cache saved for {bg_url}");
                            }
                            UploadedCache::Photos {
                                file_ids,
                                title,
                                total_size,
                            } => {
                                if let Some(first_id) = file_ids.first() {
                                    bg_db.save_cached_file(
                                        &bg_url,
                                        first_id,
                                        "photo",
                                        Some(&title),
                                        Some(total_size),
                                        None,
                                    )
                                    .await;
                                    info!("Background inline photo cache saved for {bg_url}");
                                }
                            }
                        }
                    }
                }
            });
        }
    }

    Ok(())
}

async fn answer_with_cached(bot: &Bot, q_id: InlineQueryId, cached: &CachedFile) -> bool {
    let title = cached.title.as_deref().unwrap_or("Медиа");
    let short_title = title.chars().take(50).collect::<String>();

    if cached.media_type == "video" {
        let dur_str = cached
            .duration
            .map(|d| format!(" • ⏱ {d}с"))
            .unwrap_or_default();
        let desc = format!(
            "📦 {}{dur_str}",
            format_file_size(cached.file_size.unwrap_or(0))
        );
        let res_id = format!("v_{}", &cached.file_id[..cached.file_id.len().min(30)]);

        let cached_video = InlineQueryResultCachedVideo::new(
            res_id,
            FileId(cached.file_id.clone()),
            format!("🎬 {short_title}"),
        )
        .description(desc)
        .caption(format!("🎬 {title}\n\n🤖 Скачано через @luxsittbot"));

        bot.answer_inline_query(q_id, vec![InlineQueryResult::CachedVideo(cached_video)])
            .cache_time(86400)
            .is_personal(false)
            .await
            .is_ok()
    } else {
        let res_id = format!("p_{}", &cached.file_id[..cached.file_id.len().min(30)]);
        let cached_photo = InlineQueryResultCachedPhoto::new(res_id, FileId(cached.file_id.clone()))
            .title(format!("📷 {short_title}"))
            .description(format!(
                "📦 {}",
                format_file_size(cached.file_size.unwrap_or(0))
            ))
            .caption(format!("📷 {title}\n\n🤖 Скачано через @luxsittbot"));

        bot.answer_inline_query(q_id, vec![InlineQueryResult::CachedPhoto(cached_photo)])
            .cache_time(86400)
            .is_personal(false)
            .await
            .is_ok()
    }
}

enum UploadedCache {
    Video {
        file_id: String,
        title: String,
        file_size: u64,
        duration: Option<u64>,
    },
    Photos {
        file_ids: Vec<String>,
        title: String,
        total_size: u64,
    },
}

async fn upload_to_cache(
    bot: &Bot,
    config: &Config,
    user_id: i64,
    media: &DownloadedMedia,
    file_manager: &FileManager,
) -> Option<UploadedCache> {
    // Determine the cache chat targets in order of priority:
    // 1. Channel if configured
    // 2. User PM
    // 3. Admin PM (guaranteed to be active)
    let mut target_chats = Vec::new();
    if config.cache_channel_id != 0 {
        target_chats.push((ChatId(config.cache_channel_id), false));
    }
    target_chats.push((ChatId(user_id), true));
    if config.admin_id != 0 && config.admin_id != user_id {
        target_chats.push((ChatId(config.admin_id), true));
    }

    match media {
        DownloadedMedia::Video {
            file_path,
            file_size,
            duration,
            title,
            ..
        } => {
            let mut uploaded_file_id = None;

            for (chat, should_delete) in &target_chats {
                match bot
                    .send_video(*chat, InputFile::file(file_path))
                    .supports_streaming(true)
                    .await
                {
                    Ok(sent_msg) => {
                        if let Some(v) = sent_msg.video() {
                            uploaded_file_id = Some(v.file.id.to_string());
                            if *should_delete {
                                let _ = bot.delete_message(*chat, sent_msg.id).await;
                            }
                            break;
                        }
                    }
                    Err(e) => {
                        warn!("Failed to upload to cache chat {chat}: {e}");
                    }
                }
            }

            file_manager.delete_file(file_path).await;

            uploaded_file_id.map(|file_id| UploadedCache::Video {
                file_id,
                title: title.clone(),
                file_size: *file_size,
                duration: *duration,
            })
        }
        DownloadedMedia::Photos {
            file_paths,
            total_size,
            title,
            ..
        }
        | DownloadedMedia::Album {
            file_paths,
            total_size,
            title,
        } => {
            let mut uploaded_file_ids = Vec::new();

            // Take at most 5 items for inline query responsiveness
            let items: Vec<_> = file_paths.iter().take(5).collect();

            for fp in items {
                let is_photo = fp
                    .extension()
                    .and_then(|e| e.to_str())
                    .map(|e| !e.eq_ignore_ascii_case("mp4") && !e.eq_ignore_ascii_case("mov"))
                    .unwrap_or(true);

                let mut item_file_id = None;

                for (chat, should_delete) in &target_chats {
                    if is_photo {
                        if let Ok(sent_msg) = bot.send_photo(*chat, InputFile::file(fp)).await {
                            if let Some(photo) = sent_msg.photo().and_then(|p| p.last()) {
                                item_file_id = Some(photo.file.id.to_string());
                                if *should_delete {
                                    let _ = bot.delete_message(*chat, sent_msg.id).await;
                                }
                                break;
                            }
                        }
                    } else if let Ok(sent_msg) = bot
                        .send_video(*chat, InputFile::file(fp))
                        .supports_streaming(true)
                        .await
                    {
                        if let Some(vid) = sent_msg.video() {
                            item_file_id = Some(vid.file.id.to_string());
                            if *should_delete {
                                let _ = bot.delete_message(*chat, sent_msg.id).await;
                            }
                            break;
                        }
                    }
                }

                if let Some(fid) = item_file_id {
                    uploaded_file_ids.push(fid);
                }
            }

            file_manager.delete_files(file_paths).await;

            if uploaded_file_ids.is_empty() {
                None
            } else {
                Some(UploadedCache::Photos {
                    file_ids: uploaded_file_ids,
                    title: title.clone(),
                    total_size: *total_size,
                })
            }
        }
    }
}
