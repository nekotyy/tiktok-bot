# TikTok Downloader Bot 🎬

Telegram бот для скачивания видео из TikTok без водяных знаков с поддержкой inline режима.

## 🌟 Особенности

- ✅ **Inline режим** - работает в любом чате без добавления бота
- ✅ **Без водяных знаков** - скачивает чистое видео
- ✅ **Высокое качество** - максимально доступное качество
- ✅ **Автоочистка** - файлы удаляются автоматически после отправки
- ✅ **Статистика** - отслеживание использования бота
- ✅ **Rate limiting** - защита от спама

## 📋 Требования

- Python 3.10+
- Telegram Bot Token (от [@BotFather](https://t.me/BotFather))

## 🚀 Быстрый старт

### 1. Установка зависимостей

```bash
# Клонировать репозиторий или скачать файлы
cd tiktok-bot

# Создать виртуальное окружение (рекомендуется)
python -m venv venv

# Активировать виртуальное окружение
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Установить зависимости
pip install -r requirements.txt
```

### 2. Настройка бота

#### Создать бота в Telegram

1. Написать [@BotFather](https://t.me/BotFather)
2. Отправить `/newbot`
3. Выбрать имя и username для бота
4. Получить токен (примерно так: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`)

#### Включить inline режим

1. Написать [@BotFather](https://t.me/BotFather)
2. Отправить `/setinline`
3. Выбрать вашего бота
4. Ввести placeholder текст: `Вставьте ссылку на TikTok видео`

#### Установить команды (опционально)

1. Написать [@BotFather](https://t.me/BotFather)
2. Отправить `/setcommands`
3. Выбрать вашего бота
4. Вставить:
```
start - Начать работу с ботом
help - Помощь и инструкции
stats - Моя статистика
```

### 3. Конфигурация

Создать файл `.env` из шаблона:

```bash
# Windows
copy .env.example .env

# Linux/Mac
cp .env.example .env
```

Отредактировать `.env` и вставить токен бота:

```env
BOT_TOKEN=ваш_токен_от_BotFather
```

### 4. Запуск бота

```bash
# Запустить бота
python -m bot.main
```

Бот запустится и будет работать. Вы увидите сообщение:
```
[2024-03-21 15:30:45] INFO - Bot started: @yourbot (ID: 123456789)
```

## 💻 Использование

### В любом чате

1. Начните писать `@yourbot` (имя вашего бота)
2. После пробела вставьте ссылку на TikTok видео
3. Выберите результат из всплывающего меню
4. Видео будет отправлено в личные сообщения

### Поддерживаемые форматы ссылок

- `https://www.tiktok.com/@username/video/123456789`
- `https://vm.tiktok.com/XXXXXX` (короткие ссылки)
- `https://vt.tiktok.com/XXXXXX`
- `https://m.tiktok.com/v/123456789`

### Команды бота

- `/start` - Приветствие и инструкция
- `/help` - Подробная справка
- `/stats` - Ваша статистика использования

## 🛠️ Деплой на VPS (Linux)

### Установка на Ubuntu/Debian

```bash
# Обновить систему
sudo apt update && sudo apt upgrade -y

# Установить Python 3.10+
sudo apt install python3 python3-pip python3-venv git -y

# Клонировать/загрузить проект
cd /opt
sudo git clone <your-repo-url> tiktok-bot
cd tiktok-bot

# Создать виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Установить зависимости
pip install -r requirements.txt

# Настроить .env
cp .env.example .env
nano .env  # Вставить токен бота
```

### Создать systemd service

```bash
sudo nano /etc/systemd/system/tiktok-bot.service
```

Вставить:

```ini
[Unit]
Description=TikTok Downloader Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/tiktok-bot
ExecStart=/opt/tiktok-bot/venv/bin/python -m bot.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Запустить сервис

```bash
# Перезагрузить systemd
sudo systemctl daemon-reload

# Включить автозапуск
sudo systemctl enable tiktok-bot

# Запустить бота
sudo systemctl start tiktok-bot

# Проверить статус
sudo systemctl status tiktok-bot

# Просмотреть логи
sudo journalctl -u tiktok-bot -f
```

### Управление сервисом

```bash
# Остановить
sudo systemctl stop tiktok-bot

# Перезапустить
sudo systemctl restart tiktok-bot

# Посмотреть статус
sudo systemctl status tiktok-bot
```

## 📊 Структура проекта

```
tiktok-bot/
├── bot/
│   ├── __init__.py
│   ├── main.py              # Точка входа
│   ├── config.py            # Конфигурация
│   ├── handlers/
│   │   ├── commands.py      # Обработчики команд
│   │   └── inline.py        # Inline handlers
│   ├── services/
│   │   ├── downloader.py    # Скачивание видео
│   │   ├── file_manager.py  # Управление файлами
│   │   └── url_parser.py    # Парсинг ссылок
│   ├── database/
│   │   ├── models.py        # Модели БД
│   │   └── db.py            # CRUD операции
│   └── utils/
│       ├── validators.py    # Валидация
│       └── formatters.py    # Форматирование сообщений
├── downloads/               # Временные файлы
├── data/                    # База данных
├── .env                     # Конфигурация (не в git)
├── .env.example             # Шаблон конфигурации
├── requirements.txt         # Зависимости Python
└── README.md                # Документация
```

## ⚙️ Конфигурация

Все настройки в файле `.env`:

| Параметр | Описание | По умолчанию |
|----------|----------|--------------|
| `BOT_TOKEN` | Токен Telegram бота | *обязательно* |
| `ADMIN_ID` | ID админа (опционально) | 0 |
| `MAX_FILE_SIZE_MB` | Макс. размер файла (МБ) | 50 |
| `FILE_CLEANUP_INTERVAL` | Время жизни файлов (мин) | 10 |
| `DATABASE_PATH` | Путь к БД | data/bot.db |
| `DOWNLOADS_PATH` | Папка для скачивания | downloads |

## 🔍 Логирование

Логи сохраняются в:
- Консоль (stdout)
- Файл `bot.log`

Формат логов:
```
[2024-03-21 15:30:45] INFO - bot.main - Bot started: @yourbot
[2024-03-21 15:31:12] INFO - bot.handlers.inline - User 123456 requested download
[2024-03-21 15:31:18] INFO - bot.services.downloader - Download successful: video.mp4
```

## ❓ Частые вопросы

**Q: Бот не отвечает на inline запросы?**  
A: Убедитесь, что вы включили inline режим в @BotFather командой `/setinline`

**Q: Видео слишком большое?**  
A: Telegram ограничивает размер файлов до 50 МБ для ботов (2 ГБ для Premium)

**Q: Как обновить бота?**  
A: 
```bash
cd /opt/tiktok-bot
git pull
sudo systemctl restart tiktok-bot
```

**Q: Где посмотреть ошибки?**  
A: `sudo journalctl -u tiktok-bot -f` или файл `bot.log`

## 🐛 Устранение проблем

### Бот не запускается

1. Проверьте токен в `.env`
2. Проверьте установку зависимостей: `pip install -r requirements.txt`
3. Проверьте логи: `cat bot.log`

### Ошибка "Module not found"

```bash
# Переустановить зависимости
pip install --upgrade -r requirements.txt
```

### База данных заблокирована

```bash
# Остановить бота
sudo systemctl stop tiktok-bot

# Удалить lock файл
rm data/bot.db-journal

# Запустить снова
sudo systemctl start tiktok-bot
```

## 📝 Лицензия

MIT License - свободное использование

## 🤝 Вклад

Проект открыт для улучшений! Pull requests приветствуются.

## 📧 Контакты

По вопросам и предложениям - создайте Issue в репозитории.

---

**Сделано с ❤️ для удобства скачивания TikTok видео**
