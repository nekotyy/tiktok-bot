"""Message formatting utilities."""

from datetime import datetime
from typing import Optional


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted string (e.g., "12.5 МБ")
    """
    if size_bytes < 1024:
        return f"{size_bytes} Б"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} КБ"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} МБ"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} ГБ"


def format_duration(seconds: Optional[int]) -> str:
    """Format duration in human-readable format.
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Formatted string (e.g., "1:30")
    """
    if seconds is None:
        return "?"
    
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes}:{secs:02d}"


def _pluralize(n: int, one: str, few: str, many: str) -> str:
    """Russian pluralization helper."""
    mod10 = n % 10
    mod100 = n % 100
    if mod100 in (11, 12, 13, 14):
        return many
    if mod10 == 1:
        return one
    if mod10 in (2, 3, 4):
        return few
    return many


def _parse_timestamp(ts: str) -> Optional[datetime]:
    """Parse SQLite timestamp (handles both 'T' and space separators)."""
    if not ts:
        return None
    try:
        # Python 3.11+ handles space separator natively
        return datetime.fromisoformat(ts)
    except ValueError:
        pass
    # Fallback: replace space with T for older Python
    try:
        return datetime.fromisoformat(ts.replace(' ', 'T'))
    except Exception:
        return None


def format_time_ago(timestamp: Optional[str]) -> str:
    """Format timestamp as relative time."""
    dt = _parse_timestamp(timestamp)
    if dt is None:
        return "никогда"

    now = datetime.now()
    diff = now - dt

    if diff.total_seconds() < 0:
        return "только что"

    if diff.days > 365:
        years = diff.days // 365
        return f"{years} {_pluralize(years, 'год', 'года', 'лет')} назад"
    elif diff.days > 30:
        months = diff.days // 30
        return f"{months} {_pluralize(months, 'месяц', 'месяца', 'месяцев')} назад"
    elif diff.days > 0:
        return f"{diff.days} {_pluralize(diff.days, 'день', 'дня', 'дней')} назад"
    elif diff.seconds >= 3600:
        hours = diff.seconds // 3600
        return f"{hours} {_pluralize(hours, 'час', 'часа', 'часов')} назад"
    elif diff.seconds >= 60:
        minutes = diff.seconds // 60
        return f"{minutes} {_pluralize(minutes, 'минуту', 'минуты', 'минут')} назад"
    else:
        return "только что"


def format_stats_message(stats: dict) -> str:
    """Format user statistics message.
    
    Args:
        stats: Statistics dictionary
        
    Returns:
        Formatted message
    """
    total_downloads = stats.get('total_downloads', 0)
    total_size = stats.get('total_size', 0)
    last_download = stats.get('last_download_at')
    member_since = stats.get('member_since')
    
    message = "📊 Ваша статистика:\n\n"
    message += f"✅ Скачано: {total_downloads}\n"
    message += f"📦 Общий размер: {format_file_size(total_size)}\n"
    
    if member_since:
        message += f"📅 В боте с: {format_time_ago(member_since)}\n"
    
    if last_download:
        message += f"⏰ Последнее скачивание: {format_time_ago(last_download)}\n"
    
    return message


def _display_name(entry: dict) -> str:
    username = entry.get('username')
    if username:
        return f"@{username}"

    first_name = (entry.get('first_name') or '').strip()
    last_name = (entry.get('last_name') or '').strip()
    full_name = f"{first_name} {last_name}".strip()
    if full_name:
        return full_name

    return str(entry.get('user_id', 'unknown'))


def format_top_message(top_entries: list[dict]) -> str:
    """Format top usage leaderboard."""
    if not top_entries:
        return "\u041F\u043E\u043A\u0430 \u043D\u0435\u0442 \u0434\u0430\u043D\u043D\u044B\u0445 \u0434\u043B\u044F \u0442\u043E\u043F\u0430."

    lines = ["\u0422\u043E\u043F \u043F\u043E \u0438\u0441\u043F\u043E\u043B\u044C\u0437\u043E\u0432\u0430\u043D\u0438\u044E:\n"]
    for index, entry in enumerate(top_entries, start=1):
        downloads = entry.get('total_downloads', 0)
        lines.append(
            f"{index}. {_display_name(entry)} - "
            f"{downloads} "
            f"{_pluralize(downloads, '\u0441\u043A\u0430\u0447\u0438\u0432\u0430\u043D\u0438\u0435', '\u0441\u043A\u0430\u0447\u0438\u0432\u0430\u043D\u0438\u044F', '\u0441\u043A\u0430\u0447\u0438\u0432\u0430\u043D\u0438\u0439')}"
        )

    return "\n".join(lines)


def format_start_message() -> str:
    """Format start/welcome message.
    
    Returns:
        Welcome message
    """
    return (
        "👋 Привет! Я помогу скачать видео из TikTok и YouTube Shorts.\n\n"
        "🎬 Два способа использования:\n\n"
        "1️⃣ Через inline-режим (в любом чате):\n"
        "   • Напишите @luxsittbot и ссылку\n"
        "   • Видео появится прямо в чате!\n\n"
        "2️⃣ Просто отправьте ссылку мне:\n"
        "   • Вставьте ссылку на TikTok или YouTube Shorts\n"
        "   • Получите видео сразу здесь!\n\n"
        "💡 Попробуйте прямо сейчас - просто отправьте ссылку!\n\n"
        "Команды:\n"
        "/help - подробная инструкция\n"
        "/stats - моя статистика"
    )


def format_help_message() -> str:
    """Format help message.
    
    Returns:
        Help message
    """
    return (
        "📖 Подробная инструкция\n\n"
        "🎯 Способ 1: Прямо в личке (быстрее)\n"
        "   Отправьте мне ссылку на TikTok или YouTube Shorts!\n"
        "   Видео скачается и придёт прямо сюда.\n\n"
        "🎯 Способ 2: Через inline-режим (в любом чате)\n"
        "   1. Откройте любой чат (даже группу!)\n"
        "   2. Напишите @luxsittbot и вставьте ссылку\n"
        "   3. Нажмите на результат\n"
        "   4. Видео появится прямо в том чате! 🎉\n\n"
        "🔗 Поддерживаемые ссылки:\n"
        "• https://www.tiktok.com/@user/video/123\n"
        "• https://vm.tiktok.com/xxx (короткие)\n"
        "• https://vt.tiktok.com/xxx\n"
        "• https://m.tiktok.com/v/123\n"
        "• https://www.youtube.com/shorts/xxxxx\n"
        "• https://youtu.be/xxxxx\n\n"
        "⚡ Особенности:\n"
        "• TikTok — без водяных знаков\n"
        "• YouTube Shorts — только шорты (до 60 сек)\n"
        "• Высокое качество\n"
        "• Быстрая загрузка\n"
        "• Работает в группах и каналах!\n\n"
        "❓ Частые вопросы:\n\n"
        "Q: Бот не отвечает?\n"
        "A: Проверьте правильность ссылки\n\n"
        "Q: Видео слишком большое?\n"
        "A: Telegram ограничивает размер до 50 МБ\n\n"
        "Q: Обычное YouTube видео не грузится?\n"
        "A: Бот скачивает только YouTube Shorts (до 60 сек),\n"
        "   чтобы не перегружать сервер\n\n"
        "Q: Видео недоступно?\n"
        "A: Возможно, автор удалил видео или сделал аккаунт приватным\n\n"
        "💬 Команды:\n"
        "/start - главное меню\n"
        "/stats - моя статистика\n"
        "/settings - настройки чата\n"
        "/help - эта справка"
    )
