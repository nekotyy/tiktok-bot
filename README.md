<div align="center">
  <h1>TikTok Downloader Bot</h1>
  <p><strong>Telegram-бот для скачивания видео, фото и каруселей из социальных сетей</strong></p>

  <p>
    <a href="#"><img src="https://img.shields.io/badge/python-3.10%2B-blue.svg?style=flat-square&amp;logo=python&amp;logoColor=white" alt="Python 3.10+"></a>
    <a href="#"><img src="https://img.shields.io/badge/aiogram-3.x-2CA5E0.svg?style=flat-square&amp;logo=telegram&amp;logoColor=white" alt="Aiogram 3"></a>
    <a href="#"><img src="https://img.shields.io/badge/docker-ready-2496ED.svg?style=flat-square&amp;logo=docker&amp;logoColor=white" alt="Docker"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg?style=flat-square" alt="License: MIT"></a>
  </p>

  <p>
    <a href="#возможности">Возможности</a> •
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
| **Inline-режим** | Работает в любом чате — просто начни писать `@username` + ссылка |
| **Видео со звуком** | Раздельные video/audio-потоки объединяются, результат проверяется через `ffprobe` |
| **YouTube** | Поддержка обычных видео, Shorts и коротких ссылок |
| **Instagram** | Reels, видео, фото-посты и смешанные карусели |
| **VK и другие площадки** | VK Видео/Клипы, X, Facebook, Reddit, Rutube, OK, Twitch, Vimeo и другие |
| **Фото без аудиофайла** | Фото-посты отправляются только как фото/альбом, без отдельной фоновой дорожки |
| **Настройки чата** | `/settings` — настрой поведение бота под свой чат |
| **Только чистые ссылки** | Опционально: игнорировать сообщения вида «смотри <ссылка>» |
| **Удаление сообщений** | Опционально: удалять исходное сообщение после скачивания |
| **Rate limiting** | Защита от спама — макс. 10 запросов в минуту на пользователя |
| **Автоочистка** | Временные файлы удаляются автоматически каждые 10–15 минут |
| **Статистика** | Личная статистика скачиваний (`/stats`) и общий топ (`/top`) |
| **Кэш-канал** | Опционально: кэшировать видео в канале, чтобы не перекачивать |
| **Docker** | Готовый `Dockerfile` и `compose.yml` для деплоя |

## Быстрый старт

### Требования

- **Python 3.10+**
- **FFmpeg и ffprobe** — объединение и проверка видео/аудио
- **Node.js или Deno** — полноценная поддержка YouTube в актуальном `yt-dlp`
- **Токен Telegram-бота** — получи у [@BotFather](https://t.me/BotFather)
- (Опционально) **Кэш-канал** — приватный канал для хранения кэша

### 1. Клонирование и настройка

```bash
git clone <your-repo-url>
cd tiktok-bot
cp .env.example .env
# Открой .env в редакторе и вставь BOT_TOKEN
```

### 2. Локальный запуск

```bash
# Создать виртуальное окружение
python -m venv .venv

# Активировать
source .venv/bin/activate        # Linux / macOS
.venv\Scripts\activate          # Windows

# Установить зависимости
pip install -r requirements.txt

# Запустить бота
python -m bot.main
```

Бот запустится в режиме polling. В консоли увидишь:
```
[INFO] Bot started: @your_bot_username (ID: 123456789)
```

### 3. Docker (рекомендуется для сервера)

```bash
cp .env.example .env
# Отредактируй .env
docker compose up -d --build

# Смотреть логи
docker compose logs -f tiktok-bot
```

Бот работает в фоне, перезапускается автоматически при падении.

## Конфигурация

Все настройки задаются через переменные окружения в файле `.env`:

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `BOT_TOKEN` | Токен Telegram-бота (обязательно) | — |
| `ADMIN_ID` | ID администратора для расширенных возможностей | `0` |
| `ALLOWED_CHAT_IDS` | Белый список ID чатов/каналов через запятую | *(пусто = все)* |
| `AUTO_ALLOW_MEMBER_CHATS` | `true` — работать везде; `false` — только из ALLOWED_CHAT_IDS | `true` |
| `CACHE_CHANNEL_ID` | ID канала для кэширования медиа (опционально) | `0` |
| `MAX_FILE_SIZE_MB` | Максимальный размер файла для отправки | `50` |
| `FILE_CLEANUP_INTERVAL` | Время жизни временных файлов в минутах | `10` |
| `DATABASE_PATH` | Путь к базе данных SQLite | `data/bot.db` |
| `DOWNLOADS_PATH` | Папка для временных файлов | `downloads` |
| `YTDLP_PROXY` | HTTP/SOCKS-прокси для обоих загрузчиков | *(пусто)* |
| `YTDLP_IMPERSONATE` | TLS-имперсонация `curl_cffi`, например `chrome`; включать только при необходимости | *(пусто)* |

Публичные Instagram-посты и Reels скачиваются анонимно через embed-страницу:
экспортировать браузерную сессию или настраивать cookies не нужно.

### Режим работы: везде или только в определённых чатах

По умолчанию `AUTO_ALLOW_MEMBER_CHATS=true` — бот отвечает в любом чате, где он является участником.

Если установить `false`, бот будет работать **только** в чатах, ID которых указаны в `ALLOWED_CHAT_IDS`:

```env
AUTO_ALLOW_MEMBER_CHATS=false
ALLOWED_CHAT_IDS=-1001234567890,-1009876543210
```

## Команды бота

| Команда | Описание | Кто может |
|---------|----------|-----------|
| `/start` | Приветствие, инструкция и меню | Все |
| `/help` | Подробная справка по использованию | Все |
| `/stats` | Персональная статистика скачиваний | Все |
| `/top` | Топ пользователей по скачиваниям | Все |
| `/settings` | Настройки поведения бота в чате | Только админы |

## Настройки чата

Команда `/settings` доступна **только администраторам** чата/канала. В личных сообщениях доступна всегда.

### «Только чистые ссылки»

- **Включено** — бот отвечает только если сообщение состоит исключительно из ссылки.
  - ✅ `https://www.tiktok.com/@user/video/123` → бот отвечает
  - ❌ `Смотри что нашел: https://www.tiktok.com/@user/video/123` → игнорируется
- **Выключено** — бот парсит любое сообщение, содержащее ссылку.

### «Удалять сообщения со ссылками»

- **Включено** — после отправки видео исходное сообщение пользователя удаляется.
- **Выключено** — исходное сообщение остаётся в чате.

## Как это работает

### Способ 1: Inline-режим (в любом чате)

Не нужно добавлять бота в группу. Просто:

1. Открой любой чат
2. Напиши `@your_bot_username https://www.tiktok.com/@user/video/123`
3. Нажми на результат — медиа отправится в чат!

### Способ 2: Прямое сообщение боту

1. Найди бота в Telegram
2. Отправь ему ссылку
3. Получи видео, фото или карусель сразу в ответ

### Поддерживаемые ссылки

- TikTok: `tiktok.com/@user/video/123`, `vm.tiktok.com/xxx`, `vt.tiktok.com/xxx`
- YouTube: `youtube.com/watch?v=...`, `youtube.com/shorts/...`, `youtu.be/...`
- Instagram: `instagram.com/reel/...`, `instagram.com/p/...`
- VK: `vk.com/video...`, `vk.com/clip...`, медиапосты `vk.com/wall...`
- Другие: X/Twitter, Facebook, Threads, Reddit, Pinterest, Rutube, OK, Twitch, Vimeo, Dailymotion, Likee, Coub и Streamable

## Структура проекта

```
tiktok-bot/
├── bot/
│   ├── main.py              # Точка входа: инициализация и polling
│   ├── config.py            # Загрузка переменных из .env
│   ├── handlers/
│   │   ├── commands.py      # /start, /help, /stats, /settings, обработка URL
│   │   └── inline.py        # Inline-запросы и отправка результата
│   ├── services/
│   │   ├── downloader.py    # Скачивание через yt-dlp
│   │   ├── file_manager.py  # Автоочистка временных файлов
│   │   └── url_parser.py    # Валидация и нормализация ссылок
│   ├── database/
│   │   ├── models.py        # SQLAlchemy-модели и схема
│   │   ├── db.py            # Асинхронные CRUD-операции
│   │   └── migrations.py    # Alembic-хелперы
│   └── utils/
│       ├── validators.py    # Валидация входных данных
│       └── formatters.py    # Форматирование сообщений, размеров, времени
├── alembic/                 # Миграции базы данных
│   └── versions/
│       ├── 20260427_0001_initial_schema.py
│       └── 20260512_0002_add_chat_settings.py
├── data/                    # SQLite-база (игнорируется git)
├── downloads/               # Временные медиа (игнорируются git)
├── requirements.txt         # Python-зависимости
├── Dockerfile               # Образ Docker
├── compose.yml              # Docker Compose конфиг
├── .env.example             # Шаблон конфигурации
├── README.md                # Этот файл
├── LICENSE                  # MIT License
├── CONTRIBUTING.md          # Руководство по вкладу
├── SECURITY.md              # Политика безопасности
└── CHANGELOG.md             # История изменений
```

## Безопасность

- **Токен бота** хранится только в `.env`, никогда не попадает в код или git
- **Валидация URL** — принимаются только известные публичные домены из явного allow-list
- **Rate limiting** — защита от злоупотреблений и спама
- **Path traversal** — пути файлов нормализуются, запрещён выход за пределы директорий
- **Белый список чатов** — можно ограничить доступ к боту

Подробнее читай в [SECURITY.md](SECURITY.md).

## Разработка

Хочешь улучшить бота? Круто! Читай [CONTRIBUTING.md](CONTRIBUTING.md).

Кратко:
```bash
# Форк → клон → ветка
git checkout -b feature/my-improvement
# Код → тест → коммит → push → Pull Request
```

## Лицензия

Проект распространяется под лицензией [MIT](LICENSE).

## Контакты и вклад

- Нашёл баг? Создай [issue](../../issues)
- Хочешь предложить идею? Создай [discussion](../../discussions) или [issue](../../issues)
- Pull requests приветствуются! Читай [CONTRIBUTING.md](CONTRIBUTING.md)

---

<div align="center">
  <sub>Сделано с ❤️ для удобного скачивания видео</sub>
</div>
