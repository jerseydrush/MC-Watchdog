# 🐕 MC Watchdog

[🇺🇸 English](#-english-version) • [🇷🇺 Русский](#-русская-версия)

---
---

## 🇺🇸 English Version

An asynchronous cross-platform bot built with `aiogram 3`, `discord.py`, and `mcstatus` for real-time Minecraft Java Edition server monitoring. **MC Watchdog** works simultaneously in **Telegram** and **Discord**, tracking online players, joins/leaves of the server owner and moderators, and sending customizable hourly status summaries.

---

### ✨ Key Features

- **Cross-Platform Support (Telegram & Discord):**
  * Unified monitoring loop with platform-prefixed user storage (`tg_` and `dc_`).
  * Native inline buttons in Telegram and interactive UI buttons/dropdowns with slash commands in Discord.
- **Real-Time Monitoring (15-second interval):**
  * Tracks server owner status (`Online` / `Offline` / `Completely offline` after 45 minutes of inactivity).
  * Tracks moderator activity and server latency (ping).
  * Instant alerts when the server goes down or staff members join/leave.
- **Hourly Statistics (`Hourly update`):**
  * Automatic broadcast at the top of every hour (`00` minutes), formatted in each user's personal timezone.
  * Includes ping, total player count, owner status, online moderator list, and player nicknames (complete when Query is enabled on the server).
- **Interactive Commands & Settings:**
  * `/start` — register in the bot and open the welcome menu.
  * `/status` — view current server state with a local timestamp and an interactive refresh button.
  * `/settings` — customize visible sections (Owner, Moderators, Players), toggle auto-notifications, and select your UTC timezone offset.
  * `/stop` — disable all automatic notifications.

---

### 🛠️ Installation & Setup

#### 1. Requirements
- Python 3.9 or higher.

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
MODERATORS=moder1,moder2,moder3
# QUERY_PORT=25565
```
*Note: List `MODERATORS` separated by commas without spaces (original letter casing is preserved in bot messages). To retrieve a complete player list, set `enable-query=true` in the Minecraft server's `server.properties` and allow UDP traffic to its query port. Set `QUERY_PORT` above if that port differs from the port in `SERVER_HOST`. Without Query access, the bot falls back to the sample provided by the status response and marks an incomplete list. For Discord DM notifications to work, users must share at least one server with the bot and allow DMs from server members.*

#### 4. Run the Bot
Start the main script:

```bash
python bot.py
```

---

### 📁 Project Structure

- `bot.py` — main bot code (Telegram + Discord) and background monitoring loop.
- `requirements.txt` — list of dependencies (`aiogram`, `discord.py`, `mcstatus`, `python-dotenv`).
- `.env` — configuration file containing bot tokens and server settings *(do not commit to public repositories)*.
- `TERMS.md` — Terms of Service for the bot.
- `PRIVACY.md` — Privacy Policy explaining data collection and user preferences storage.
- `users.txt` — database of platform-prefixed user IDs *(created automatically)*.
- `user_settings.json` — per-user display, notification, and timezone preferences *(created automatically)*.

---
---

## 🇷🇺 Русская версия

Асинхронный кроссплатформенный бот на базе `aiogram 3`, `discord.py` и `mcstatus` для мониторинга статуса Minecraft Java Edition сервера в реальном времени. **MC Watchdog** работает одновременно в **Telegram** и **Discord**, отслеживая онлайн игроков, заходы и выходы владельца сервера и модераторов, а также отправляя ежечасные сводки с учетом часового пояса пользователя.

---

### ✨ Основные возможности

- **Поддержка двух платформ (Telegram и Discord):**
  * Единый цикл мониторинга и общая база пользователей с префиксами платформ (`tg_` и `dc_`).
  * Интерактивные inline-кнопки в Telegram и слеш-команды с кнопками и выпадающим списком в Discord.
- **Мониторинг в реальном времени (интервал 15 сек):**
  * Отслеживание статуса владельца сервера (`Online` / `Offline` / `Completely offline` спустя 45 минут отсутствия).
  * Отслеживание активности модераторов и пинга сервера.
  * Мгновенные оповещения при изменении статуса администрации или недоступности сервера.
- **Ежечасная статистика (`Hourly update`):**
  * Автоматическая рассылка в начале каждого часа (`00` минут) с локальным временем каждого пользователя.
  * Включает пинг, количество игроков, статус владельца, список модераторов и ники игроков онлайн (полный список доступен при включенном Query на сервере).
- **Интерактивные команды и настройки:**
  * `/start` — регистрация в боте и открытие главного меню.
  * `/status` — текущий статус сервера с локальным временем и кнопкой быстрого обновления.
  * `/settings` — персональная настройка отображения блоков (владелец, модераторы, игроки), вкл/выкл авто-уведомлений и выбор часового пояса (UTC).
  * `/stop` — отключение всех автоматических уведомлений.

---

### 🛠️ Установка и запуск

#### 1. Требования
- Python 3.9 или выше.

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
MODERATORS=moder1,moder2,moder3
# QUERY_PORT=25565
```
*Примечание: `MODERATORS` указываются через запятую без пробелов (регистр букв сохраняется при выводе). Чтобы получать полный список игроков, установите `enable-query=true` в `server.properties` Minecraft-сервера и разрешите UDP-трафик на Query-порт. Если он отличается от порта в `SERVER_HOST`, задайте `QUERY_PORT`. Без доступа к Query бот использует только список из ответа статуса и помечает его как неполный. Чтобы бот мог отправлять личные уведомления в Discord, у пользователя должен быть хотя бы один общий сервер с ботом и включен прием ЛС от участников сервера.*

#### 4. Запуск бота
Запустите главный скрипт:

```bash
python bot.py
```

---

### 📁 Структура файлов проекта

- `bot.py` — основной код бота (Telegram + Discord) и фоновый цикл мониторинга.
- `requirements.txt` — список зависимостей (`aiogram`, `discord.py`, `mcstatus`, `python-dotenv`).
- `.env` — конфигурационный файл с токенами и настройками сервера *(не публикуйте в открытых репозиториях)*.
- `TERMS.md` — Условия использования бота (Terms of Service).
- `PRIVACY.md` — Политика конфиденциальности (Privacy Policy).
- `users.txt` — база ID подписанных пользователей с префиксами платформ *(создается автоматически)*.
- `user_settings.json` — персональные настройки отображения, уведомлений и часового пояса *(создается автоматически)*.