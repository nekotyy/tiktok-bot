<div align="center">
  <h1>TikTok Downloader Bot (Rust Edition) 🦀⚡</h1>
  <p><strong>Высокопроизводительный асинхронный Telegram-бот на Rust для мгновенного скачивания видео, фото и каруселей из социальных сетей</strong></p>

  <p>
    <a href="#"><img src="https://img.shields.io/badge/rust-1.80%2B-orange.svg?style=flat-square&amp;logo=rust&amp;logoColor=white" alt="Rust 1.80+"></a>
    <a href="#"><img src="https://img.shields.io/badge/teloxide-0.17-blue.svg?style=flat-square&amp;logo=telegram&amp;logoColor=white" alt="Teloxide 0.17"></a>
    <a href="#"><img src="https://img.shields.io/badge/tokio-async-red.svg?style=flat-square&amp;logo=tokio&amp;logoColor=white" alt="Tokio"></a>
    <a href="#"><img src="https://img.shields.io/badge/docker-ready-2496ED.svg?style=flat-square&amp;logo=docker&amp;logoColor=white" alt="Docker"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg?style=flat-square" alt="License: MIT"></a>
  </p>

  <p>
    <a href="#возможности">Возможности</a> •
    <a href="#архитектура-и-производительность">Производительность</a> •
    <a href="#быстрый-старт">Быстрый старт</a> •
    <a href="#конфигурация">Конфигурация</a> •
    <a href="#команды">Команды</a> •
    <a href="#настройки-чата">Настройки</a> •
    <a href="#разработка">Разработка</a>
  </p>
</div>

---

## Возможности

| Фича | Описание |
|------|----------|
| ⚡ **Максимальная скорость** | Написан на Rust с Tokio runtime: параллельные загрузки, нулевой оверхед памяти, мгновенный отклик |
| 🚀 **Прямой TikWM API** | Для TikTok используется прямой HTTP API (видео без водяных знаков и параллельная загрузка фотоальбомов) без запуска тяжелых внешних процессов |
| 📸 **Быстрый Instagram Embed** | Анонимный парсер `embed/captioned` через мобильные заголовки: прямое скачивание CDN без cookies и аккаунтов |
| 🎥 **yt-dlp fallback** | YouTube (видео и Shorts), VK (клипы/видео/посты), Twitter/X, Reddit, Pinterest и др. через оптимизированный пул yt-dlp |
| 🔍 **Inline-режим** | Работает в любом чате: напиши `@username <ссылка>` и выбери медиа для отправки |
| 🔊 **Проверка аудио/видео** | Автоматическая проверка через `ffprobe` и ремуксинг через `ffmpeg` (faststart, h264/aac) для 100% совместимости с Telegram |
| 🖼 **Фото и карусели** | Полноценная поддержка слайд-шоу и каруселей (отправка медиагруппами без лишних аудиофайлов) |
| 🛡 **Rate limiting** | Встроенный thread-safe sliding window rate-limiter (10 запросов в минуту на пользователя) |
| ⚙️ **Настройки чата** | `/settings` — режим «только чистые ссылки» и автоудаление исходных сообщений |
| 📊 **Статистика и топ** | База SQLite (WAL-режим, connection pool) — личные данные `/stats` и глобальный топ `/top` |
| 🧹 **Автоочистка** | Фоновый асинхронный воркер удаляет временные файлы по таймеру |
| 🐳 **Docker ready** | Multi-stage Dockerfile на базе `rust:1-bookworm` и `python:3.12-slim` с `ffmpeg`, `yt-dlp` и `deno` |

---

## Архитектура и производительность

В новой версии бот полностью переписан с Python на **Rust**:
1. **Многоуровневый пайплайн скачивания (Tiered Pipeline):**
   - **TikTok:** Сначала опрашивается высокоскоростной API TikWM. Видео и фотоальбомы скачиваются напрямую через пул соединений `reqwest` с параллельной загрузкой (`join_all`). Если API недоступен, прозрачно включается yt-dlp.
   - **Instagram:** Сначала используется прямой парсер Instagram Embed. Если пост приватный или embed заблокирован, запрос направляется в yt-dlp.
   - **YouTube, VK, X и др.:** Скачиваются через yt-dlp с жестким ограничением форматов под Telegram (`mp4[vcodec^=avc1][height<=1080]`), Deno JS runtime и флагами быстрого старта.
2. **SQLite + WAL режим:**
   - База данных работает в режиме `PRAGMA journal_mode = WAL` и `PRAGMA synchronous = NORMAL`.
   - Полная обратная совместимость со схемой таблиц из предыдущей версии (`users`, `downloads`, `statistics`, `chat_settings`).
3. **Безопасность памяти и надёжность:**
   - Все ошибки сетевых вызовов, процессов `ffmpeg`/`yt-dlp` и парсинга строго типизированы и изолированы, не приводя к падению бота.
   - Исходный Python-код заботливо сохранен в директории `.old/` для истории.

---

## Быстрый старт

### Требования
- **Rust 1.80+** (Cargo)
- **FFmpeg и ffprobe** — для проверки и ремуксинга медиафайлов
- **yt-dlp** — установлен в `PATH`
- **Deno или Node.js** (рекомендуется) — для JS-интерпретатора YouTube
- **Токен Telegram-бота** — от [@BotFather](https://t.me/BotFather)

### 1. Клонирование и настройка

```bash
git clone <your-repo-url>
cd tiktok-bot
cp .env.example .env
# Заполни BOT_TOKEN в .env
```

### 2. Локальный запуск на Rust

```bash
# Проверка и сборка
cargo build --release

# Запуск
cargo run --release
```

### 3. Запуск через Docker Compose (рекомендуется)

```bash
docker compose up -d --build

# Просмотр логов
docker compose logs -f tiktok-bot
```

---

## Конфигурация

Все параметры задаются через `.env` (обратная совместимость сохранена на 100%):

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `BOT_TOKEN` | Токен Telegram-бота (обязательно) | — |
| `ADMIN_ID` | ID администратора | `0` |
| `ALLOWED_CHAT_IDS` | Белый список ID чатов через запятую | *(пусто = все чаты)* |
| `AUTO_ALLOW_MEMBER_CHATS` | `true` — отвечать в любых группах, где бот состоит | `true` |
| `CACHE_CHANNEL_ID` | ID канала для кэширования видео (опционально) | `0` |
| `MAX_FILE_SIZE_MB` | Максимальный размер файла для отправки в Telegram | `50` |
| `FILE_CLEANUP_INTERVAL` | Интервал очистки временных файлов (в минутах) | `10` |
| `DATABASE_PATH` | Путь к SQLite файлу | `data/bot.db` |
| `DOWNLOADS_PATH` | Каталог для временных файлов | `downloads` |
| `YTDLP_PROXY` | HTTP/SOCKS5 прокси | *(пусто)* |
| `YTDLP_IMPERSONATE` | TLS-имперсонация браузера (например, `chrome`) | *(пусто)* |

---

## Команды бота

| Команда | Описание | Доступ |
|---------|----------|--------|
| `/start` | Приветствие, обзор возможностей и клавиатура | Все |
| `/help` | Подробная справка по поддерживаемым сервисам | Все |
| `/stats` | Личная статистика пользователя по скачиваниям | Все |
| `/top` | Глобальная таблица лидеров | Все |
| `/settings` | Меню настроек чата (только ссылки / удаление) | Админы / ЛС |

---

## Структура проекта

```
tiktok-bot/
├── src/
│   ├── main.rs                  # Точка входа: логгирование, задачи, запуск поллинга
│   ├── lib.rs                   # Библиотечный корень
│   ├── config.rs                # Валидация и парсинг конфигурации .env
│   ├── db/
│   │   ├── mod.rs
│   │   ├── models.rs            # Модели БД (User, Stats, TopUser, Settings)
│   │   └── database.rs          # Асинхронный SQLite wrapper, миграции, WAL
│   ├── handlers/
│   │   ├── mod.rs
│   │   ├── commands.rs          # /start, /help, /stats, /top, /settings, обработка ссылок
│   │   └── inline.rs            # Inline Query обработчик
│   ├── services/
│   │   ├── mod.rs
│   │   ├── downloader.rs        # Главный пайплайн скачивания (TikWM -> Embed -> yt-dlp)
│   │   ├── tiktok_api.rs        # Прямой TikWM API клиент с параллельной загрузкой
│   │   ├── instagram_extractor.rs # Анонимный быстрый парсер Instagram Embed
│   │   ├── url_parser.rs        # Регулярные выражения, валидация и нормализация URL
│   │   ├── rate_limiter.rs      # Sliding window rate limiter
│   │   └── file_manager.rs      # Асинхронный клинер временных файлов
│   └── utils/
│       ├── mod.rs
│       └── formatters.rs        # Русская плюрализация, форматирование байт и времени
├── tests/
│   └── test_all.rs              # Интеграционные тесты (URL, парсинг, БД, форматирование)
├── .old/                        # Архив предыдущей реализации на Python
│   ├── bot/
│   ├── alembic/
│   ├── pyproject.toml
│   └── uv.lock
├── Cargo.toml                   # Зависимости Rust проекта
├── Dockerfile                   # Multi-stage production build
├── compose.yml                  # Docker compose конфигурация
└── README.md
```

---

## Лицензия

MIT License
