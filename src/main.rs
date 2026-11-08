mod config;
mod db;
mod handlers;
mod services;
mod utils;

use std::sync::Arc;
use teloxide::dispatching::UpdateFilterExt;
use teloxide::prelude::*;
use teloxide::types::Update;
use tracing::{error, info};
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

use crate::config::Config;
use crate::db::Database;
use crate::handlers::commands::{handle_callback_query, handle_command, handle_media_url_message};
use crate::handlers::inline::handle_inline_query;
use crate::services::downloader::MediaDownloader;
use crate::services::file_manager::FileManager;
use crate::services::rate_limiter::RateLimiter;
use crate::services::url_parser::URLParser;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Initialize structured logging
    tracing_subscriber::registry()
        .with(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "tiktok_bot=info,teloxide=info".into()),
        )
        .with(tracing_subscriber::fmt::layer())
        .init();

    info!("Starting TikTok Downloader Bot (Rust high-performance edition)...");

    // Load configuration
    let config = match Config::load() {
        Ok(cfg) => Arc::new(cfg),
        Err(err) => {
            error!("Configuration error: {err}");
            std::process::exit(1);
        }
    };
    info!("Configuration loaded successfully");

    // Initialize database
    let db = match Database::new(&config.database_path) {
        Ok(d) => Arc::new(d),
        Err(err) => {
            error!("Fatal database error: {err}");
            std::process::exit(1);
        }
    };
    info!("Database initialized at {}", config.database_path.display());

    // Initialize file manager and clean up temp files
    let file_manager = Arc::new(FileManager::new(
        &config.downloads_path,
        config.file_cleanup_interval,
    ));
    let cleaned_on_start = file_manager.cleanup_all_temp_files().await;
    if cleaned_on_start > 0 {
        info!("Cleaned {cleaned_on_start} leftover temp files on startup");
    }
    file_manager.start_cleanup_task(15);

    // Initialize rate limiter
    let rate_limiter = Arc::new(RateLimiter::new(
        config.rate_limit_requests,
        config.rate_limit_period_secs,
    ));

    // Initialize downloader
    let downloader = Arc::new(MediaDownloader::new(
        &config.downloads_path,
        config.max_file_size_bytes,
        config.ytdlp_proxy.clone(),
        config.ytdlp_impersonate.clone(),
    ));

    // Initialize Bot
    let bot = Bot::new(&config.bot_token);
    match bot.get_me().await {
        Ok(me) => {
            info!(
                "Bot authorized successfully: @{} (ID: {})",
                me.username(),
                me.id
            );
        }
        Err(err) => {
            error!("Failed to authorize Telegram bot: {err}");
            std::process::exit(1);
        }
    }

    // Build Dispatcher
    let handler = dptree::entry()
        .branch(
            Update::filter_message().endpoint(
                |bot: Bot,
                 msg: Message,
                 config: Arc<Config>,
                 db: Arc<Database>,
                 downloader: Arc<MediaDownloader>,
                 file_manager: Arc<FileManager>| async move {
                    let text_opt = msg.text().or_else(|| msg.caption()).map(|s| s.to_string());
                    if let Some(text) = text_opt {
                        let trimmed = text.trim();
                        if trimmed.starts_with('/') {
                            let cmd = trimmed.to_string();
                            if let Err(e) = handle_command(bot, msg, &cmd, config, db).await {
                                error!("Command error: {e}");
                            }
                            return respond(());
                        }

                        if URLParser::extract_and_validate(trimmed).is_some() {
                            if let Err(e) = handle_media_url_message(
                                bot,
                                msg,
                                config,
                                db,
                                downloader,
                                file_manager,
                            )
                            .await
                            {
                                error!("Media message error: {e}");
                            }
                            return respond(());
                        }
                    }
                    respond(())
                },
            ),
        )
        .branch(
            Update::filter_callback_query().endpoint(
                |bot: Bot, q: CallbackQuery, db: Arc<Database>| async move {
                    if let Err(e) = handle_callback_query(bot, q, db).await {
                        error!("Callback query error: {e}");
                    }
                    respond(())
                },
            ),
        )
        .branch(
            Update::filter_inline_query().endpoint(
                |bot: Bot,
                 q: InlineQuery,
                 config: Arc<Config>,
                 db: Arc<Database>,
                 downloader: Arc<MediaDownloader>,
                 file_manager: Arc<FileManager>,
                 rate_limiter: Arc<RateLimiter>| async move {
                    if let Err(e) = handle_inline_query(
                        bot,
                        q,
                        config,
                        db,
                        downloader,
                        file_manager,
                        rate_limiter,
                    )
                    .await
                    {
                        error!("Inline query error: {e}");
                    }
                    respond(())
                },
            ),
        );

    let mut dp = Dispatcher::builder(bot, handler)
        .dependencies(dptree::deps![
            config,
            db,
            downloader,
            file_manager,
            rate_limiter
        ])
        .enable_ctrlc_handler()
        .build();

    info!("Bot polling started");
    dp.dispatch().await;

    info!("Bot stopped");
    Ok(())
}
