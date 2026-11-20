# 🐕 MC Watchdog

[🇺🇸 English](#-english-version) • [🇷🇺 Русский](#-русская-версия)

---
---

## 🇺🇸 English Version

An asynchronous cross-platform bot built with `aiogram 3`, `discord.py`, `mcstatus`, and `aiohttp` for real-time Minecraft Java Edition server and owner stream monitoring. **MC Watchdog** works simultaneously in **Telegram** and **Discord**, tracking online players, staff activity, TikTok live streams of the server owner, daily peak statistics, and customizable hourly status summaries.

---

### ✨ Key Features

- **Cross-Platform Support (Telegram & Discord):**
  * Unified monitoring loops with platform-prefixed user storage (`tg_` and `dc_`).
  * Native inline buttons in Telegram and interactive UI buttons/dropdowns with slash commands in Discord.
- **Real-Time Server Monitoring (15-second interval):**
  * Tracks server owner status (`Online` / `Offline` / `Possibly offline (partial list)` / `Completely offline` after 45 minutes of confirmed inactivity).
  * Tracks moderator activity, server latency (ping), and strips legacy Minecraft color/formatting codes and slot counters from player samples.
  * Consecutive-error filtering (3 failed attempts before reporting server downtime) to prevent false timeout alerts.
  * Automatically detects incomplete player lists (`partial list`) when `Query` is unavailable or capped by MOTD plugins.
- **Owner TikTok Stream Tracking:**
  * Monitors the server owner's TikTok profile (`OWNER_TIKTOK`) every 2 minutes for live broadcasts.
  * Sends instant stream start/end alerts to subscribers with `Preliminary Alerts` enabled.
  * Displays current stream status in `/status` and hourly updates, and records the timestamp of the last stream for `/stats` and `/check`.
- **Daily Player Statistics & Activity Tracking (`/stats` & `/check`):**
  * Records daily peak online counts and per-player online duration with automatic 7-day rotation in `player_stats.json`.
  * All timestamps (`last seen`, `peak time`, `last stream`) automatically adjust to each user's configured UTC offset.
- **Interactive Commands & Settings:**
  * `/start` — register in the bot and open the welcome menu.
  * `/status` — view current server state, owner stream status, local timestamp, and an interactive refresh button.
  * `/check <nickname>` — check a specific player's role, current online status, time played today, last seen time, and last stream time (for the owner).
  * `/stats` — view today's peak online, unique tracked players, top active players, and the owner's last stream timestamp.
  * `/settings` — customize visible sections (Owner, Moderators, Players), toggle hourly updates and preliminary/stream alerts, and select your UTC timezone offset.
  * `/stop` — disable all automatic notifications.

---

### 🛠️ Installation & Setup

#### 1. Requirements
- Python 3.9 or higher (Python 3.11+ recommended).

#### 2. Clone & Install Dependencies
Clone the repository and install the required packages from `requirements.txt`:

```bash
git clone https://github.com/jerseydrush/MC-Watchdog.git
cd MC-Watchdog
pip install -r requirements.txt
```

#### 3. Environment Configuration (`.env`)
Create a `.env` file in the root directory of the project with the following variables:

```env
TG_TOKEN=your_token_from_BotFather
DISCORD_TOKEN=your_token_from_Discord_Developer_Portal
SERVER_HOST=your_server_address
OWNER_NICKNAME=owner_nickname
OWNER_TIKTOK=@owner_tiktok_handle
MODERATORS=moder1,moder2,moder3
# QUERY_PORT=25565
```
*Note: List `MODERATORS` separated by commas without spaces (original letter casing is preserved in bot messages). To retrieve a complete player list, set `enable-query=true` in the Minecraft server's `server.properties` and allow UDP traffic to its query port. Set `QUERY_PORT` above if that port differs from the port in `SERVER_HOST`. Without Query access, the bot falls back to the sample provided by the status response and marks an incomplete list as `partial list`. For Discord DM notifications to work, users must share at least one server with the bot and allow DMs from server members.*

#### 4. Run the Bot
Start the main script:

```bash
python bot.py
```

---

### 📁 Project Structure

- `bot.py` — main bot code (Telegram + Discord), server monitoring loop, and TikTok stream monitor.
- `requirements.txt` — list of dependencies (`aiogram`, `discord.py`, `mcstatus`, `python-dotenv`, `aiohttp`).
- `.env` — configuration file containing bot tokens, server settings, and the owner's TikTok handle *(do not commit to public repositories)*.
- `TERMS.md` — Terms of Service for the bot.
- `PRIVACY.md` — Privacy Policy explaining data collection and user preferences storage.
- `users.txt` — database of platform-prefixed user IDs *(created automatically)*.
- `user_settings.json` — per-user display, notification, and timezone preferences *(created automatically)*.
- `player_stats.json` — rolling 7-day statistics for daily peaks, player activity, and owner stream history *(created automatically)*.

---
---

## 🇷🇺 Русская версия

Асинхронный кроссплатформенный бот на базе `aiogram 3`, `discord.py`, `mcstatus` и `aiohttp` для мониторинга статуса Minecraft Java Edition сервера и стримов его владельца в реальном времени. **MC Watchdog** работает одновременно в **Telegram** и **Discord**, отслеживая онлайн игроков, активность администрации, прямые эфиры владельца в TikTok, дневную статистику пикового онлайна и ежечасные сводки.

---

### ✨ Основные возможности

- **Поддержка двух платформ (Telegram и Discord):**
  * Единые фоновые циклы мониторинга и общая база пользователей с префиксами платформ (`tg_` и `dc_`).
  * Интерактивные inline-кнопки в Telegram и слеш-команды с кнопками и выпадающим списком в Discord.
- **Мониторинг сервера в реальном времени (интервал 15 сек):**
  * Отслеживание статуса владельца сервера (`Online` / `Offline` / `Possibly offline (partial list)` / `Completely offline` спустя 45 минут подтверждённого отсутствия).
  * Отслеживание активности модераторов, пинга сервера и автоматическая очистка ников от цветовых кодов Minecraft и счётчиков слотов.
  * Фильтрация ложных таймаутов (уведомление о падении сервера отправляется только после 3 подряд неудачных проверок).
  * Корректная обработка неполных списков игроков (`partial list`), если `Query` закрыт или список урезан MOTD-плагином.
- **Отслеживание стримов владельца в TikTok:**
  * Фоновая проверка TikTok-профиля владельца (`OWNER_TIKTOK`) каждые 2 минуты на наличие активного прямого эфира.
  * Мгновенные оповещения о начале и завершении стрима для пользователей с включёнными предварительными уведомлениями (`Preliminary Alerts`).
  * Отображение статуса стрима в `/status` и ежечасных сводках, а также сохранение времени последнего эфира для `/stats` и `/check`.
- **Дневная статистика и активность игроков (`/stats` и `/check`):**
  * Подсчёт пикового онлайна за день и времени игры каждого игрока с автоматической ротацией за последние 7 дней в `player_stats.json`.
  * Все временные метки (`last seen`, время пика онлайна, время последнего стрима) автоматически переводятся в часовой пояс пользователя (UTC).
- **Интерактивные команды и настройки:**
  * `/start` — регистрация в боте и открытие главного меню.
  * `/status` — текущий статус сервера и стрима владельца с локальным временем и кнопкой быстрого обновления.
  * `/check <никнейм>` — проверка роли игрока, текущего онлайна, времени в игре за сегодня, времени последнего входа и последнего стрима (для владельца).
  * `/stats` — статистика за сегодня: пиковый онлайн, количество уникальных игроков, топ активных игроков и время последнего стрима владельца.
  * `/settings` — персональная настройка отображения блоков (владелец, модераторы, игроки), вкл/выкл ежечасных сводок и оповещений, выбор часового пояса (UTC).
  * `/stop` — отключение всех автоматических уведомлений.

---

### 🛠️ Установка и запуск

#### 1. Требования
- Python 3.9 или выше (рекомендуется Python 3.11+).

#### 2. Клонирование и установка зависимостей
Склонируйте репозиторий и установите необходимые библиотеки из `requirements.txt`:

```bash
git clone https://github.com/jerseydrush/MC-Watchdog.git
cd MC-Watchdog
pip install -r requirements.txt
```

#### 3. Настройка окружения (`.env`)
Создайте в корневой папке проекта файл `.env` со следующими параметрами:

```env
TG_TOKEN=ваш_токен_от_BotFather
DISCORD_TOKEN=ваш_токен_из_Discord_Developer_Portal
SERVER_HOST=адрес_вашего_сервера
OWNER_NICKNAME=никнейм_владельца
OWNER_TIKTOK=@аккаунт_владельца_в_tiktok
MODERATORS=moder1,moder2,moder3
# QUERY_PORT=25565
```
*Примечание: `MODERATORS` указываются через запятую без пробелов (регистр букв сохраняется при выводе). Чтобы получать полный список игроков, установите `enable-query=true` в `server.properties` Minecraft-сервера и разрешите UDP-трафик на Query-порт. Если он отличается от порта в `SERVER_HOST`, задайте `QUERY_PORT`. Без доступа к Query бот использует список из ответа статуса и помечает неполный список как `partial list`. Чтобы бот мог отправлять личные уведомления в Discord, у пользователя должен быть хотя бы один общий сервер с ботом и включён приём ЛС от участников сервера.*

#### 4. Запуск бота
Запустите главный скрипт:

```bash
python bot.py
```

---

### 📁 Структура файлов проекта

- `bot.py` — основной код бота (Telegram + Discord), фоновый мониторинг сервера и отслеживание стримов в TikTok.
- `requirements.txt` — список зависимостей (`aiogram`, `discord.py`, `mcstatus`, `python-dotenv`, `aiohttp`).
- `.env` — конфигурационный файл с токенами, настройками сервера и TikTok-аккаунтом владельца *(не публикуйте в открытых репозиториях)*.
- `TERMS.md` — Условия использования бота (Terms of Service).
- `PRIVACY.md` — Политика конфиденциальности (Privacy Policy).
- `users.txt` — база ID подписанных пользователей с префиксами платформ *(создаётся автоматически)*.
- `user_settings.json` — персональные настройки отображения, уведомлений и часового пояса *(создаётся автоматически)*.
- `player_stats.json` — статистика за последние 7 дней (пиковый онлайн, активность игроков и история стримов владельца) *(создаётся автоматически)*.