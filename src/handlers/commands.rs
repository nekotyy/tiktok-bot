use std::sync::Arc;
use teloxide::prelude::*;
use teloxide::types::{
    ChatAction, ChatMemberStatus, InputFile, InputMedia, InputMediaPhoto, InputMediaVideo,
    Message, ReplyParameters,
};
use tracing::{error, info};

use crate::config::Config;
use crate::db::Database;
use crate::services::downloader::{DownloadedMedia, MediaDownloader};
use crate::services::file_manager::FileManager;
use crate::services::url_parser::URLParser;
use crate::utils::formatters::{
    back_keyboard, format_help_message, format_start_message, format_stats_message,
    format_top_message, main_keyboard, settings_keyboard,
};

pub async fn handle_command(
    bot: Bot,
    msg: Message,
    cmd_text: &str,
    config: Arc<Config>,
    db: Arc<Database>,
) -> anyhow::Result<()> {
    if !config.is_chat_allowed(msg.chat.id.0) {
        return Ok(());
    }

    let user_id = msg.from.as_ref().map(|u| u.id.0 as i64).unwrap_or(msg.chat.id.0);
    let username = msg.from.as_ref().and_then(|u| u.username.clone());
    let first_name = msg.from.as_ref().map(|u| u.first_name.clone());
    let last_name = msg.from.as_ref().and_then(|u| u.last_name.clone());

    let clean_cmd = cmd_text.split_whitespace().next().unwrap_or("").to_lowercase();
    let base_cmd = clean_cmd.split('@').next().unwrap_or("");

    match base_cmd {
        "/start" => {
            db.add_user(user_id, username, first_name, last_name).await;
            bot.send_message(msg.chat.id, format_start_message())
                .reply_markup(main_keyboard())
                .await?;
        }
        "/help" => {
            bot.send_message(msg.chat.id, format_help_message())
                .reply_markup(back_keyboard())
                .await?;
        }
        "/stats" => {
            let stats = db.get_user_stats(user_id).await.unwrap_or_default();
            bot.send_message(msg.chat.id, format_stats_message(&stats))
                .reply_markup(back_keyboard())
                .await?;
        }
        "/top" => {
            let top_users = db.get_top_users(10).await;
            bot.send_message(msg.chat.id, format_top_message(&top_users))
                .reply_markup(back_keyboard())
                .await?;
        }
        "/settings" => {
            if !is_chat_admin(&bot, &msg).await {
                bot.send_message(msg.chat.id, "⚠️ Настройки доступны только администраторам чата.")
                    .await?;
                return Ok(());
            }

            let settings = db.get_chat_settings(msg.chat.id.0).await;
            let text = "⚙️ <b>Настройки чата</b>\n\n\
                        <b>Только чистые ссылки</b> — бот отвечает только если сообщение \
                        состоит только из ссылки (без лишнего текста).\n\n\
                        <b>Удалять сообщения со ссылками</b> — бот удаляет исходное сообщение \
                        пользователя после отправки видео.";

            bot.send_message(msg.chat.id, text)
                .parse_mode(teloxide::types::ParseMode::Html)
                .reply_markup(settings_keyboard(&settings))
                .await?;
        }
        _ => {}
    }

    Ok(())
}

pub async fn handle_callback_query(
    bot: Bot,
    q: CallbackQuery,
    db: Arc<Database>,
) -> anyhow::Result<()> {
    let data = match q.data {
        Some(ref d) => d.as_str(),
        None => return Ok(()),
    };

    let user_id = q.from.id.0 as i64;
    let username = q.from.username.clone();
    let first_name = Some(q.from.first_name.clone());
    let last_name = q.from.last_name.clone();

    match data {
        "start" => {
            db.add_user(user_id, username, first_name, last_name).await;
            if let Some(msg) = q.message {
                let _ = bot
                    .edit_message_text(msg.chat().id, msg.id(), format_start_message())
                    .reply_markup(main_keyboard())
                    .await;
            }
            let _ = bot.answer_callback_query(q.id).await;
        }
        "help" => {
            if let Some(msg) = q.message {
                let _ = bot
                    .edit_message_text(msg.chat().id, msg.id(), format_help_message())
                    .reply_markup(back_keyboard())
                    .await;
            }
            let _ = bot.answer_callback_query(q.id).await;
        }
        "stats" => {
            let stats = db.get_user_stats(user_id).await.unwrap_or_default();
            if let Some(msg) = q.message {
                let _ = bot
                    .edit_message_text(msg.chat().id, msg.id(), format_stats_message(&stats))
                    .reply_markup(back_keyboard())
                    .await;
            }
            let _ = bot.answer_callback_query(q.id).await;
        }
        "rate_limit" => {
            let _ = bot
                .answer_callback_query(q.id)
                .text("⚠️ Вы отправляете слишком много запросов. Подождите немного.")
                .show_alert(true)
                .await;
        }
        "invalid_url" => {
            let _ = bot
                .answer_callback_query(q.id)
                .text("❌ Некорректная или неподдерживаемая ссылка.")
                .show_alert(true)
                .await;
        }
        "error" => {
            let _ = bot
                .answer_callback_query(q.id)
                .text("❌ Произошла ошибка. Попробуйте позже.")
                .show_alert(true)
                .await;
        }
        "toggle_require_pure_link" => {
            if let Some(msg) = q.message {
                let chat_id = msg.chat().id.0;
                let settings = db.get_chat_settings(chat_id).await;
                let new_val = !settings.require_pure_link;
                db.set_chat_setting(chat_id, Some(new_val), None).await;
                let updated = db.get_chat_settings(chat_id).await;
                let _ = bot
                    .edit_message_reply_markup(msg.chat().id, msg.id())
                    .reply_markup(settings_keyboard(&updated))
                    .await;
            }
            let _ = bot.answer_callback_query(q.id).await;
        }
        "toggle_delete_source" => {
            if let Some(msg) = q.message {
                let chat_id = msg.chat().id.0;
                let settings = db.get_chat_settings(chat_id).await;
                let new_val = !settings.delete_source_messages;
                db.set_chat_setting(chat_id, None, Some(new_val)).await;
                let updated = db.get_chat_settings(chat_id).await;
                let _ = bot
                    .edit_message_reply_markup(msg.chat().id, msg.id())
                    .reply_markup(settings_keyboard(&updated))
                    .await;
            }
            let _ = bot.answer_callback_query(q.id).await;
        }
        _ => {
            let _ = bot.answer_callback_query(q.id).await;
        }
    }

    Ok(())
}

pub async fn handle_media_url_message(
    bot: Bot,
    msg: Message,
    config: Arc<Config>,
    db: Arc<Database>,
    downloader: Arc<MediaDownloader>,
    file_manager: Arc<FileManager>,
) -> anyhow::Result<()> {
    if !config.is_chat_allowed(msg.chat.id.0) {
        return Ok(());
    }

    let text = match msg.text().or_else(|| msg.caption()) {
        Some(t) => t,
        None => return Ok(()),
    };

    let parsed = match URLParser::extract_and_validate(text) {
        Some(p) => p,
        None => return Ok(()),
    };

    let chat_settings = db.get_chat_settings(msg.chat.id.0).await;
    if chat_settings.require_pure_link && !URLParser::is_pure_link_message(text) {
        info!(
            "Skipping non-pure link in chat {} (require_pure_link is active)",
            msg.chat.id
        );
        return Ok(());
    }

    let user_id = msg.from.as_ref().map(|u| u.id.0 as i64).unwrap_or(msg.chat.id.0);
    let username = msg.from.as_ref().and_then(|u| u.username.clone());
    let first_name = msg.from.as_ref().map(|u| u.first_name.clone());
    let last_name = msg.from.as_ref().and_then(|u| u.last_name.clone());

    db.add_user(user_id, username, first_name, last_name).await;

    let platform_label = parsed.platform.display_label();
    info!(
        "Chat {}: user {} requested {} ({})",
        msg.chat.id, user_id, platform_label, parsed.normalized_url
    );

    let _ = bot.send_chat_action(msg.chat.id, ChatAction::UploadVideo).await;

    let download_res = downloader
        .download_media(parsed.platform, &parsed.normalized_url)
        .await;

    let media = match download_res {
        Ok(m) => m,
        Err(err_msg) => {
            let _ = bot
                .send_message(msg.chat.id, format!("❌ Ошибка: {err_msg}"))
                .reply_parameters(ReplyParameters::new(msg.id))
                .await;

            db.log_download(
                user_id,
                parsed.normalized_url.clone(),
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

    match media {
        DownloadedMedia::Video { file_path, .. } => {
            let _ = bot.send_chat_action(msg.chat.id, ChatAction::UploadVideo).await;
            let input_file = InputFile::file(&file_path);

            let send_res = bot
                .send_video(msg.chat.id, input_file)
                .supports_streaming(true)
                .reply_parameters(ReplyParameters::new(msg.id))
                .await;

            file_manager.delete_file(&file_path).await;

            if let Err(e) = send_res {
                error!("Failed to send video: {e}");
                let _ = bot
                    .send_message(msg.chat.id, "❌ Не удалось отправить видео")
                    .reply_parameters(ReplyParameters::new(msg.id))
                    .await;
                return Ok(());
            }
        }
        DownloadedMedia::Photos { ref file_paths, .. } => {
            let _ = bot.send_chat_action(msg.chat.id, ChatAction::UploadPhoto).await;

            if file_paths.len() == 1 {
                let input_file = InputFile::file(&file_paths[0]);
                let _ = bot
                    .send_photo(msg.chat.id, input_file)
                    .reply_parameters(ReplyParameters::new(msg.id))
                    .await;
            } else {
                for chunk in file_paths.chunks(10) {
                    let media_group: Vec<InputMedia> = chunk
                        .iter()
                        .map(|p| InputMedia::Photo(InputMediaPhoto::new(InputFile::file(p))))
                        .collect();
                    let _ = bot
                        .send_media_group(msg.chat.id, media_group)
                        .reply_parameters(ReplyParameters::new(msg.id))
                        .await;
                }
            }

            file_manager.delete_files(file_paths).await;
        }
        DownloadedMedia::Album { ref file_paths, .. } => {
            let _ = bot.send_chat_action(msg.chat.id, ChatAction::UploadVideo).await;

            for chunk in file_paths.chunks(10) {
                let media_group: Vec<InputMedia> = chunk
                    .iter()
                    .map(|p| {
                        let ext = p.extension().and_then(|e| e.to_str()).unwrap_or("");
                        if ext.eq_ignore_ascii_case("mp4") || ext.eq_ignore_ascii_case("mov") {
                            InputMedia::Video(
                                InputMediaVideo::new(InputFile::file(p)).supports_streaming(true),
                            )
                        } else {
                            InputMedia::Photo(InputMediaPhoto::new(InputFile::file(p)))
                        }
                    })
                    .collect();

                let _ = bot
                    .send_media_group(msg.chat.id, media_group)
                    .reply_parameters(ReplyParameters::new(msg.id))
                    .await;
            }

            file_manager.delete_files(file_paths).await;
        }
    }

    db.log_download(
        user_id,
        parsed.normalized_url.clone(),
        true,
        Some(file_size as i64),
        duration.map(|d| d as i64),
        None,
    )
    .await;

    if chat_settings.delete_source_messages {
        let _ = bot.delete_message(msg.chat.id, msg.id).await;
    }

    info!(
        "{platform_label} sent back to chat {} for user {user_id}",
        msg.chat.id
    );

    Ok(())
}

async fn is_chat_admin(bot: &Bot, msg: &Message) -> bool {
    if msg.chat.is_private() {
        return true;
    }

    let user_id = match msg.from.as_ref() {
        Some(u) => u.id,
        None => return false,
    };

    match bot.get_chat_member(msg.chat.id, user_id).await {
        Ok(member) => matches!(
            member.status(),
            ChatMemberStatus::Administrator | ChatMemberStatus::Owner
        ),
        Err(_) => false,
    }
}
