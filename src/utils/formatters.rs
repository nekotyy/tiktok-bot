use chrono::{DateTime, Utc};
use teloxide::types::{InlineKeyboardButton, InlineKeyboardMarkup};

use crate::db::models::{ChatSettings, TopUser, UserStats};

pub fn format_file_size(size_bytes: u64) -> String {
    if size_bytes < 1024 {
        format!("{size_bytes} Б")
    } else if size_bytes < 1024 * 1024 {
        format!("{:.1} КБ", size_bytes as f64 / 1024.0)
    } else if size_bytes < 1024 * 1024 * 1024 {
        format!("{:.1} МБ", size_bytes as f64 / (1024.0 * 1024.0))
    } else {
        format!("{:.1} ГБ", size_bytes as f64 / (1024.0 * 1024.0 * 1024.0))
    }
}

#[allow(dead_code)]
pub fn format_duration(seconds: Option<u64>) -> String {
    match seconds {
        Some(secs) => {
            let minutes = secs / 60;
            let rem_secs = secs % 60;
            format!("{minutes}:{rem_secs:02}")
        }
        None => "?".to_string(),
    }
}

pub fn pluralize<'a>(n: i64, one: &'a str, few: &'a str, many: &'a str) -> &'a str {
    let abs_n = n.abs();
    let mod10 = abs_n % 10;
    let mod100 = abs_n % 100;
    if (11..=14).contains(&mod100) {
        return many;
    }
    if mod10 == 1 {
        return one;
    }
    if (2..=4).contains(&mod10) {
        return few;
    }
    many
}

pub fn format_time_ago(timestamp: Option<&str>) -> String {
    let ts = match timestamp {
        Some(s) if !s.trim().is_empty() => s.trim(),
        _ => return "никогда".to_string(),
    };

    let dt = parse_sqlite_timestamp(ts);
    let dt = match dt {
        Some(val) => val,
        None => return "никогда".to_string(),
    };

    let now = Utc::now();
    let diff = now.signed_duration_since(dt);

    if diff.num_seconds() < 0 {
        return "только что".to_string();
    }

    let days = diff.num_days();
    let seconds = diff.num_seconds();

    if days > 365 {
        let years = days / 365;
        format!("{} {} назад", years, pluralize(years, "год", "года", "лет"))
    } else if days > 30 {
        let months = days / 30;
        format!(
            "{} {} назад",
            months,
            pluralize(months, "месяц", "месяца", "месяцев")
        )
    } else if days > 0 {
        format!("{} {} назад", days, pluralize(days, "день", "дня", "дней"))
    } else if seconds >= 3600 {
        let hours = seconds / 3600;
        format!("{} {} назад", hours, pluralize(hours, "час", "часа", "часов"))
    } else if seconds >= 60 {
        let minutes = seconds / 60;
        format!(
            "{} {} назад",
            minutes,
            pluralize(minutes, "минуту", "минуты", "минут")
        )
    } else {
        "только что".to_string()
    }
}

fn parse_sqlite_timestamp(ts: &str) -> Option<DateTime<Utc>> {
    let clean = ts.trim();
    if let Ok(dt) = DateTime::parse_from_rfc3339(clean) {
        return Some(dt.with_timezone(&Utc));
    }
    let formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S%.f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%.f",
        "%Y-%m-%d",
    ];
    for fmt in formats {
        if let Ok(naive) = chrono::NaiveDateTime::parse_from_str(clean, fmt) {
            return Some(DateTime::from_naive_utc_and_offset(naive, Utc));
        }
    }
    None
}

pub fn format_stats_message(stats: &UserStats) -> String {
    let mut msg = String::from("📊 Ваша статистика:\n\n");
    msg.push_str(&format!("✅ Скачано: {}\n", stats.total_downloads));
    msg.push_str(&format!(
        "📦 Общий размер: {}\n",
        format_file_size(stats.total_size as u64)
    ));

    if let Some(ref since) = stats.member_since {
        msg.push_str(&format!(
            "📅 В боте с: {}\n",
            format_time_ago(Some(since.as_str()))
        ));
    }

    if let Some(ref last) = stats.last_download_at {
        msg.push_str(&format!(
            "⏰ Последнее скачивание: {}\n",
            format_time_ago(Some(last.as_str()))
        ));
    }

    msg
}

pub fn format_top_message(top_entries: &[TopUser]) -> String {
    if top_entries.is_empty() {
        return "Пока нет данных для топа.".to_string();
    }

    let mut lines = vec!["Топ по использованию:\n".to_string()];
    for (idx, entry) in top_entries.iter().enumerate() {
        let rank = idx + 1;
        let count = entry.total_downloads;
        let word = pluralize(count, "скачивание", "скачивания", "скачиваний");
        let name = entry.display_name();
        lines.push(format!("{rank}. {name} - {count} {word}"));
    }

    lines.join("\n")
}

pub fn format_start_message() -> &'static str {
    "👋 Привет! Я помогу скачать видео и фото из социальных сетей.\n\n\
     🎬 Два способа использования:\n\n\
     1️⃣ Через inline-режим (в любом чате):\n\
        • Напишите @luxsittbot и ссылку\n\
        • Видео появится прямо в чате!\n\n\
     2️⃣ Просто отправьте ссылку мне:\n\
        • Вставьте ссылку на публикацию или видео\n\
        • Получите медиа сразу здесь!\n\n\
     💡 Попробуйте прямо сейчас - просто отправьте ссылку!\n\n\
     Команды:\n\
     /help - подробная инструкция\n\
     /stats - моя статистика"
}

pub fn format_help_message() -> &'static str {
    "📖 Подробная инструкция\n\n\
     🎯 Способ 1: Прямо в личке (быстрее)\n\
        Отправьте мне ссылку на публикацию или видео!\n\
        Медиа скачается и придёт прямо сюда.\n\n\
     🎯 Способ 2: Через inline-режим (в любом чате)\n\
        1. Откройте любой чат (даже группу!)\n\
        2. Напишите @luxsittbot и вставьте ссылку\n\
        3. Нажмите на результат\n\
        4. Видео появится прямо в том чате! 🎉\n\n\
     🔗 Поддерживаемые ссылки:\n\
     • https://www.tiktok.com/@user/video/123\n\
     • https://vm.tiktok.com/xxx (короткие)\n\
     • https://vt.tiktok.com/xxx\n\
     • https://m.tiktok.com/v/123\n\
     • https://www.youtube.com/shorts/xxxxx\n\
     • https://youtu.be/xxxxx\n\
     • https://www.instagram.com/reel/xxxxx/\n\
     • https://www.instagram.com/p/xxxxx/\n\
     • https://vk.com/video-123_456\n\
     • X, Facebook, Reddit, Pinterest, Rutube, OK, Twitch, Vimeo и другие\n\n\
     ⚡ Особенности:\n\
     • TikTok — без водяных знаков\n\
     • YouTube — видео, Shorts и короткие ссылки\n\
     • Instagram — Reels, посты и карусели\n\
     • VK — видео, клипы и медиапосты\n\
     • Фото отправляются без отдельной аудиодорожки\n\
     • Высокое качество\n\
     • Быстрая загрузка\n\
     • Работает в группах и каналах!\n\n\
     ❓ Частые вопросы:\n\n\
     Q: Бот не отвечает?\n\
     A: Проверьте правильность ссылки\n\n\
     Q: Видео слишком большое?\n\
     A: Telegram ограничивает размер до 50 МБ\n\n\
     Q: Площадка просит войти?\n\
     A: Бот скачивает только публично доступные публикации\n\n\
     Q: Видео недоступно?\n\
     A: Возможно, автор удалил видео или сделал аккаунт приватным\n\n\
     💬 Команды:\n\
     /start - главное меню\n\
     /stats - моя статистика\n\
     /settings - настройки чата\n\
     /help - эта справка"
}

pub fn main_keyboard() -> InlineKeyboardMarkup {
    InlineKeyboardMarkup::new(vec![vec![
        InlineKeyboardButton::callback("📖 Помощь", "help"),
        InlineKeyboardButton::callback("📊 Статистика", "stats"),
    ]])
}

pub fn back_keyboard() -> InlineKeyboardMarkup {
    InlineKeyboardMarkup::new(vec![vec![InlineKeyboardButton::callback(
        "◀️ Назад", "start",
    )]])
}

pub fn settings_keyboard(settings: &ChatSettings) -> InlineKeyboardMarkup {
    let req_icon = if settings.require_pure_link { "✅ " } else { "❌ " };
    let del_icon = if settings.delete_source_messages { "✅ " } else { "❌ " };

    InlineKeyboardMarkup::new(vec![
        vec![InlineKeyboardButton::callback(
            format!("{req_icon}Только чистые ссылки"),
            "toggle_require_pure_link",
        )],
        vec![InlineKeyboardButton::callback(
            format!("{del_icon}Удалять сообщения со ссылками"),
            "toggle_delete_source",
        )],
        vec![InlineKeyboardButton::callback("◀️ Назад", "start")],
    ])
}
