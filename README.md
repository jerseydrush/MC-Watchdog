# 📊 Minecraft Server Monitor Telegram Bot

[🇷🇺 Русский](#-русская-версия) • [🇬🇧 English](#-english-version)

---
---

## 🇷🇺 Русская версия

Асинхронный Telegram-бот на базе `aiogram 3` и `mcstatus` для мониторинга статуса Minecraft-сервера в реальном времени. Бот отслеживает общий онлайн, заходы и выходы владельца сервера и модераторов, а также отправляет ежечасные сводки.

---

### ✨ Основные возможности

* **Мониторинг в реальном времени (интервал 15 сек):**
  * Отслеживание статуса владельца сервера (`Online` / `Offline` / `Completely offline` спустя 45 минут отсутствия).
  * Отслеживание активности модераторов.
  * Оповещения о падении и восстановлении работы сервера.
* **Ежечасная статистика (`Hourly update`):**
  * Автоматическая рассылка в начале каждого часа (`00` минут) по **UTC**.
  * Включает количество игроков, статус владельца, список модераторов и ники всех игроков онлайн.
* **Интерактивные команды и настройки:**
  * `/start` — подписка на уведомления и главное меню.
  * `/status` — текущий статус сервера с актуальным временем (UTC) и кнопкой быстрого обновления.
  * `/settings` — персональная настройка отображения блоков (владелец, модераторы, игроки) и вкл/выкл авто-уведомлений.
  * `/stop` — отписка от рассылки.

---

### 🛠️ Установка и запуск

#### 1. Требования
* Python 3.9 или выше.

#### 2. Установка зависимостей
Склонируйте проект или поместите файлы в одну директорию, затем установите необходимые библиотеки из `requirements.txt`:

```bash
pip install -r requirements.txt
```

#### 3. Настройка окружения (`.env`)
Убедитесь, что в корневой папке проекта находится файл `.env` со следующими параметрами:

```env
BOT_TOKEN=ваш_токен_от_BotFather
SERVER_HOST=адрес_вашего_сервера
OWNER_NICKNAME=никнейм_владельца
MODERATORS=moder1,moder2,moder3
```
*Примечание: `MODERATORS` указываются через запятую без пробелов (регистр букв сохраняется при выводе).*

#### 4. Запуск бота
Запустите главный скрипт:

```bash
python bot.py
```

---

### 📁 Структура файлов проекта

* `bot.py` — основной код бота и фоновый цикл мониторинга.
* `requirements.txt` — список зависимостей (`aiogram`, `mcstatus`, `python-dotenv`).
* `.env` — конфигурационный файл с токеном и настройками сервера *(не рекомендуется публиковать в открытых репозиториях)*.
* `users.txt` — база ID подписанных пользователей *(создается автоматически)*.
* `user_settings.json` — персональные настройки отображения для каждого пользователя *(создается автоматически)*.

---
---

## 🇬🇧 English Version

An asynchronous Telegram bot built with `aiogram 3` and `mcstatus` for real-time Minecraft server monitoring. The bot tracks total online players, joins/leaves of the server owner and moderators, and sends hourly status summaries.

---

### ✨ Key Features

* **Real-Time Monitoring (15-second interval):**
  * Tracks server owner status (`Online` / `Offline` / `Completely offline` after 45 minutes of inactivity).
  * Tracks moderator activity.
  * Instant alerts when the server goes down or comes back online.
* **Hourly Statistics (`Hourly update`):**
  * Automatic broadcast at the top of every hour (`00` minutes) in **UTC**.
  * Includes total player count, owner status, list of online moderators, and all online player nicknames.
* **Interactive Commands & Settings:**
  * `/start` — subscribe to notifications and open the main menu.
  * `/status` — view current server state with UTC timestamp and an inline refresh button.
  * `/settings` — customize visible sections (Owner, Moderators, Players) and toggle auto-notifications.
  * `/stop` — unsubscribe from broadcasts.

---

### 🛠️ Installation & Setup

#### 1. Requirements
* Python 3.9 or higher.

#### 2. Install Dependencies
Clone the repository or place the files in a single directory, then install the required packages from `requirements.txt`:

```bash
pip install -r requirements.txt
```

#### 3. Environment Configuration (`.env`)
Make sure there is a `.env` file in the root directory of the project with the following variables:

```env
BOT_TOKEN=your_token_from_BotFather
SERVER_HOST=your_server_address
OWNER_NICKNAME=owner_nickname
MODERATORS=moder1,moder2,moder3
```
*Note: List `MODERATORS` separated by commas without spaces (original letter casing is preserved in bot messages).*

#### 4. Run the Bot
Start the main script:

```bash
python bot.py
```

---

### 📁 Project Structure

* `bot.py` — main bot code and background monitoring loop.
* `requirements.txt` — list of dependencies (`aiogram`, `mcstatus`, `python-dotenv`).
* `.env` — configuration file containing the bot token and server settings *(do not commit to public repositories)*.
* `users.txt` — database of subscribed user IDs *(created automatically)*.
* `user_settings.json` — per-user display and notification preferences *(created automatically)*.