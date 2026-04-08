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


def format_time_ago(timestamp: Optional[str]) -> str:
    """Format timestamp as relative time.
    
    Args:
        timestamp: ISO timestamp string
        
    Returns:
        Relative time string (e.g., "2 часа назад")
    """
    if not timestamp:
        return "никогда"
    
    try:
        dt = datetime.fromisoformat(timestamp)
        now = datetime.now()
        diff = now - dt
        
        if diff.days > 365:
            years = diff.days // 365
            return f"{years} {'год' if years == 1 else 'лет'} назад"
        elif diff.days > 30:
            months = diff.days // 30
            return f"{months} {'месяц' if months == 1 else 'месяцев'} назад"
        elif diff.days > 0:
            return f"{diff.days} {'день' if diff.days == 1 else 'дней'} назад"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} {'час' if hours == 1 else 'часов'} назад"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} {'минуту' if minutes == 1 else 'минут'} назад"
        else:
            return "только что"
    except Exception:
        return "неизвестно"


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
    message += f"✅ Скачано видео: {total_downloads}\n"
    message += f"📦 Общий размер: {format_file_size(total_size)}\n"
    
    if member_since:
        message += f"📅 В боте с: {format_time_ago(member_since)}\n"
    
    if last_download:
        message += f"⏰ Последнее скачивание: {format_time_ago(last_download)}\n"
    
    return message


def format_start_message() -> str:
    """Format start/welcome message.
    
    Returns:
        Welcome message
    """
    return (
        "👋 Привет! Я помогу скачать видео из TikTok без водяных знаков.\n\n"
        "🎬 Два способа использования:\n\n"
        "1️⃣ Через inline-режим (в любом чате):\n"
        "   • Напишите @luxsittbot и ссылку\n"
        "   • Видео появится прямо в чате!\n\n"
        "2️⃣ Просто отправьте ссылку мне:\n"
        "   • Вставьте ссылку на TikTok\n"
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
        "   Просто отправьте мне ссылку на TikTok!\n"
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
        "• https://m.tiktok.com/v/123\n\n"
        "⚡ Особенности:\n"
        "• Без водяных знаков\n"
        "• Высокое качество\n"
        "• Быстрая загрузка\n"
        "• Работает в группах и каналах!\n\n"
        "❓ Частые вопросы:\n\n"
        "Q: Бот не отвечает?\n"
        "A: Проверьте правильность ссылки\n\n"
        "Q: Видео слишком большое?\n"
        "A: Telegram ограничивает размер до 50 МБ\n\n"
        "Q: Видео недоступно?\n"
        "A: Возможно, автор удалил видео или сделал аккаунт приватным\n\n"
        "💬 Команды:\n"
        "/start - главное меню\n"
        "/stats - моя статистика\n"
        "/help - эта справка"
    )
