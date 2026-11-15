import asyncio
from datetime import datetime, timezone, timedelta
import os
import json
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from dotenv import load_dotenv
from mcstatus import JavaServer
import time

# Load configuration from .env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SERVER_HOST = os.getenv("SERVER_HOST", "basyasmp.gomc.me")
OWNER_NICKNAME = os.getenv("OWNER_NICKNAME", "alexcrish")

# Parse comma-separated moderators preserving original casing
raw_mods = os.getenv("MODERATORS", "")
MODERATORS = [m.strip() for m in raw_mods.split(",") if m.strip()]
moders_lower_set = {m.lower() for m in MODERATORS}

CHECK_INTERVAL = 15
OFFLINE_TIMEOUT = 45 * 60
USERS_FILE = "users.txt"
SETTINGS_FILE = "user_settings.json"

if not BOT_TOKEN:
    raise ValueError("Error: BOT_TOKEN not found in .env file!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Automatically handles standard ports, custom ports, and DNS SRV records
server = JavaServer.lookup(SERVER_HOST)

# Server status cache
current_status_cache = {
    "total_players": 0,
    "owner_online": False,
    "owner_completely_offline": False,
    "online_moders": [],
    "all_players": [],
    "is_down": False,
    "ping": None,
    "last_error": None
}


def load_users() -> set:
    if not os.path.exists(USERS_FILE):
        return set()
    with open(USERS_FILE, "r") as f:
        return {int(line.strip()) for line in f if line.strip().isdigit()}


def save_users(users: set):
    with open(USERS_FILE, "w") as f:
        for uid in users:
            f.write(f"{uid}\n")


def default_user_settings() -> dict:
    return {
        "timezone_offset": 0,  # UTC offset in hours (-12 to +14)
        "notify_hourly": True,
        "notify_prelim": True,
        "show_owner": True,
        "show_moders": True,
        "show_players": True
    }


def register_user_if_new(user_id: int):
    """Registers user on first interaction with default settings enabled."""
    users = load_users()
    if user_id not in users:
        users.add(user_id)
        save_users(users)
        settings_data = load_all_user_settings()
        if str(user_id) not in settings_data:
            settings_data[str(user_id)] = default_user_settings()
            save_all_user_settings(settings_data)


def load_all_user_settings() -> dict:
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_all_user_settings(data: dict):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=4)


def get_user_settings(user_id: int) -> dict:
    all_settings = load_all_user_settings()
    cfg = all_settings.get(str(user_id), default_user_settings())
    defaults = default_user_settings()
    for k, v in defaults.items():
        if k not in cfg:
            cfg[k] = v
    return cfg


def get_user_time_str(user_id: int, dt: datetime = None) -> str:
    if dt is None:
        dt = datetime.now(timezone.utc)
    settings = get_user_settings(user_id)
    offset_hours = settings.get("timezone_offset", 0)
    user_tz = timezone(timedelta(hours=offset_hours))
    return dt.astimezone(user_tz).strftime("%Y-%m-%d %H:%M:%S")


async def broadcast(text_template: str, setting_key: str, is_hourly: bool = False):
    """Broadcasts a message to users, formatting time according to each user's timezone offset."""
    settings_data = load_all_user_settings()
    users = load_users()
    
    utc_now = datetime.now(timezone.utc)
    
    for user_id in users:
        user_cfg = settings_data.get(str(user_id), default_user_settings())
        if not user_cfg.get(setting_key, True):
            continue
        try:
            if is_hourly:
                offset_hours = user_cfg.get("timezone_offset", 0)
                user_tz = timezone(timedelta(hours=offset_hours))
                user_time = utc_now.astimezone(user_tz)
                formatted_time = user_time.strftime('%H:00')
                
                personalized_text = text_template.replace("{TIME_PLACEHOLDER}", formatted_time)
                await bot.send_message(chat_id=user_id, text=personalized_text, parse_mode="HTML")
            else:
                await bot.send_message(chat_id=user_id, text=text_template, parse_mode="HTML")
        except Exception as e:
            print(f"[Broadcast error to {user_id}]: {e}")


def get_status_text_for_user(user_id: int) -> str:
    st = current_status_cache
    if st["is_down"]:
        err_msg = st.get("last_error")
        err_details = f"\n<code>{err_msg}</code>" if err_msg else ""
        return f"⚠️ <b>Server is currently unavailable.</b>{err_details}"

    settings = get_user_settings(user_id)
    show_owner = settings.get("show_owner", True)
    show_moders = settings.get("show_moders", True)
    show_players = settings.get("show_players", True)

    time_str = get_user_time_str(user_id)
    ping_val = st.get("ping")
    ping_str = f" | 🏓 <code>{ping_val}ms</code>" if ping_val is not None else ""
    
    lines = [f"📊 <b>SERVER STATUS</b>{ping_str}\n<code>{time_str}</code>\n"]

    if st["owner_online"]:
        owner_status = "🟢 <b>Online</b>"
    elif st.get("owner_completely_offline", False):
        owner_status = "🔴 <b>Completely offline</b>"
    else:
        owner_status = "🔴 <b>Offline</b>"

    owner_str = f"👑 <b>Owner:</b> <code>{OWNER_NICKNAME}</code> — {owner_status}"

    moders_list = st["online_moders"]
    if moders_list:
        moders_str = "🛡️ <b>Moderators:</b>\n" + "\n".join(f"   ▫️ <code>{m}</code>" for m in moders_list)
    else:
        moders_str = "🛡️ <b>Moderators:</b> <i>None online</i>"

    all_players = st.get("all_players", [])
    if all_players:
        players_str = f"👥 <b>Players online ({st['total_players']}):</b>\n" + "\n".join(f"   ▪️ <code>{p}</code>" for p in all_players)
    else:
        players_str = f"👥 <b>Players online:</b> <code>{st['total_players']}</code> (<i>No sample</i>)"

    has_content = False
    if show_owner:
        lines.append(owner_str)
        has_content = True

    if show_moders:
        if has_content:
            lines.append("")
        lines.append(moders_str)
        has_content = True

    if show_players:
        if has_content:
            lines.append("")
        lines.append(players_str)
        has_content = True

    if not has_content:
        lines.append("<i>All display options are turned off in settings.</i>")

    return "\n".join(lines)


def get_settings_keyboard(user_id: int) -> InlineKeyboardMarkup:
    settings = get_user_settings(user_id)
    
    offset = settings.get("timezone_offset", 0)
    offset_sign = "+" if offset >= 0 else ""
    tz_text = f"🌐 Timezone: UTC {offset_sign}{offset}"

    hourly_check = "✅" if settings.get("notify_hourly", True) else "❌"
    prelim_check = "✅" if settings.get("notify_prelim", True) else "❌"
    owner_check = "✅" if settings.get("show_owner", True) else "❌"
    moders_check = "✅" if settings.get("show_moders", True) else "❌"
    players_check = "✅" if settings.get("show_players", True) else "❌"

    keyboard = [
        [InlineKeyboardButton(text=f"{owner_check} Show Owner", callback_data="toggle_owner")],
        [InlineKeyboardButton(text=f"{moders_check} Show Moderators", callback_data="toggle_moders")],
        [InlineKeyboardButton(text=f"{players_check} Show Players", callback_data="toggle_players")],
        [InlineKeyboardButton(text=f"{hourly_check} Hourly Updates", callback_data="toggle_hourly")],
        [InlineKeyboardButton(text=f"{prelim_check} Preliminary Alerts", callback_data="toggle_prelim")],
        [InlineKeyboardButton(text=tz_text, callback_data="open_tz_menu")],
        [InlineKeyboardButton(text="🔄 Refresh Status", callback_data="refresh_settings_status")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_timezone_keyboard(user_id: int) -> InlineKeyboardMarkup:
    settings = get_user_settings(user_id)
    current_offset = settings.get("timezone_offset", 0)

    rows = []
    row = []
    for offset in range(-12, 15):
        sign = "+" if offset >= 0 else ""
        label = f"UTC {sign}{offset}"
        if offset == current_offset:
            label = f"✅ {label}"
        
        row.append(InlineKeyboardButton(text=label, callback_data=f"set_tz_{offset}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    rows.append([InlineKeyboardButton(text="⬅️ Back to Settings", callback_data="open_settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_status_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="🔄 Refresh Status", callback_data="refresh_status")],
        [InlineKeyboardButton(text="⚙️ Settings", callback_data="open_settings")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_stop_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_main_menu_text() -> str:
    return (
        "👋 <b>Welcome to Server Monitor Bot!</b>\n\n"
        "<b>Commands:</b>\n"
        " /status — get current server state\n"
        " /settings — configure display toggles & notifications\n"
        " /stop — disable all auto notifications"
    )


@dp.message(Command("start"))
async def cmd_start(message: Message):
    register_user_if_new(message.from_user.id)
    await message.answer(get_main_menu_text(), parse_mode="HTML")


@dp.message(Command("settings"))
async def cmd_settings(message: Message):
    user_id = message.from_user.id
    register_user_if_new(user_id)

    await message.answer(
        "⚙️ <b>Bot Settings & Preferences</b>\n\n"
        "Use the toggle buttons below to choose what information you want to see, manage notifications, and set your timezone.",
        reply_markup=get_settings_keyboard(user_id),
        parse_mode="HTML"
    )


@dp.callback_query(lambda c: c.data in [
    "toggle_owner", "toggle_moders", "toggle_players", 
    "toggle_hourly", "toggle_prelim", "open_tz_menu",
    "refresh_settings_status", "refresh_status", "open_settings", "main_menu"
] or c.data.startswith("set_tz_"))
async def process_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    register_user_if_new(user_id)
    
    if callback.data == "main_menu":
        try:
            await callback.message.edit_text(get_main_menu_text(), parse_mode="HTML")
        except Exception:
            pass
        await callback.answer()
        return

    if callback.data == "open_settings":
        try:
            await callback.message.edit_text(
                "⚙️ <b>Bot Settings & Preferences</b>\n\n"
                "Use the toggle buttons below to choose what information you want to see, manage notifications, and set your timezone.",
                reply_markup=get_settings_keyboard(user_id),
                parse_mode="HTML"
            )
        except Exception:
            pass
        await callback.answer()
        return

    if callback.data == "open_tz_menu":
        try:
            await callback.message.edit_text(
                "🌐 <b>Select your Timezone</b>\n\n"
                "Choose your offset relative to UTC:",
                reply_markup=get_timezone_keyboard(user_id),
                parse_mode="HTML"
            )
        except Exception:
            pass
        await callback.answer()
        return

    if callback.data.startswith("set_tz_"):
        try:
            offset_val = int(callback.data.split("_")[2])
            settings_data = load_all_user_settings()
            user_cfg = get_user_settings(user_id)
            user_cfg["timezone_offset"] = offset_val
            settings_data[str(user_id)] = user_cfg
            save_all_user_settings(settings_data)

            sign = "+" if offset_val >= 0 else ""
            await callback.message.edit_text(
                "🌐 <b>Select your Timezone</b>\n\n"
                f"Timezone successfully set to <b>UTC {sign}{offset_val}</b>!",
                reply_markup=get_timezone_keyboard(user_id),
                parse_mode="HTML"
            )
            await callback.answer(f"Timezone updated to UTC {sign}{offset_val}")
        except Exception as e:
            await callback.answer("Failed to update timezone.", show_alert=True)
        return

    if callback.data == "refresh_status":
        if current_status_cache["is_down"]:
            err_msg = current_status_cache.get("last_error")
            alert_text = f"Server is currently down!\nError: {err_msg}" if err_msg else "Server is currently down!"
            await callback.answer(alert_text, show_alert=True)
            return
        try:
            await callback.message.edit_text(
                get_status_text_for_user(user_id),
                reply_markup=get_status_keyboard(),
                parse_mode="HTML"
            )
        except Exception:
            pass
        await callback.answer("Status refreshed!")
        return

    settings_data = load_all_user_settings()
    user_cfg = get_user_settings(user_id)

    if callback.data == "toggle_owner":
        user_cfg["show_owner"] = not user_cfg.get("show_owner", True)
    elif callback.data == "toggle_moders":
        user_cfg["show_moders"] = not user_cfg.get("show_moders", True)
    elif callback.data == "toggle_players":
        user_cfg["show_players"] = not user_cfg.get("show_players", True)
    elif callback.data == "toggle_hourly":
        user_cfg["notify_hourly"] = not user_cfg.get("notify_hourly", True)
    elif callback.data == "toggle_prelim":
        user_cfg["notify_prelim"] = not user_cfg.get("notify_prelim", True)
    elif callback.data == "refresh_settings_status":
        if current_status_cache["is_down"]:
            err_msg = current_status_cache.get("last_error")
            alert_text = f"Server is currently down!\nError: {err_msg}" if err_msg else "Server is currently down!"
            await callback.answer(alert_text, show_alert=True)
            return
        try:
            await callback.message.edit_text(
                get_status_text_for_user(user_id),
                reply_markup=get_settings_keyboard(user_id),
                parse_mode="HTML"
            )
        except Exception:
            pass
        await callback.answer("Status refreshed!")
        return

    settings_data[str(user_id)] = user_cfg
    save_all_user_settings(settings_data)

    try:
        await callback.message.edit_reply_markup(reply_markup=get_settings_keyboard(user_id))
    except Exception:
        pass
    await callback.answer("Settings updated!")


@dp.message(Command("stop"))
async def cmd_stop(message: Message):
    user_id = message.from_user.id
    register_user_if_new(user_id)

    settings_data = load_all_user_settings()
    user_cfg = get_user_settings(user_id)
    user_cfg["notify_hourly"] = False
    user_cfg["notify_prelim"] = False
    settings_data[str(user_id)] = user_cfg
    save_all_user_settings(settings_data)

    await message.answer(
        "🔕 <b>All notifications disabled.</b> You can turn them back on in /settings.",
        reply_markup=get_stop_keyboard(),
        parse_mode="HTML"
    )


@dp.message(Command("status"))
async def cmd_status(message: Message):
    user_id = message.from_user.id
    register_user_if_new(user_id)

    if current_status_cache["is_down"]:
        err_msg = current_status_cache.get("last_error")
        err_details = f"\n<code>{err_msg}</code>" if err_msg else ""
        await message.answer(
            f"⚠️ <b>Server is unavailable</b>, please try again later.{err_details}", 
            reply_markup=get_status_keyboard(),
            parse_mode="HTML"
        )
        return

    await message.answer(
        get_status_text_for_user(user_id), 
        reply_markup=get_status_keyboard(),
        parse_mode="HTML"
    )


async def monitor_loop():
    owner_online = None
    owner_last_seen = None
    owner_45_notified = False

    moders_count = None
    moders_last_seen = None
    moders_45_notified = False

    last_reported_hour = -1

    owner_lower = OWNER_NICKNAME.lower()

    while True:
        now_time_utc = datetime.now(timezone.utc)
        current_hour = now_time_utc.hour
        current_minute = now_time_utc.minute

        try:
            status = await server.async_status()
            current_status_cache["is_down"] = False
            current_status_cache["last_error"] = None
            current_status_cache["ping"] = round(status.latency)

            sample_players = status.players.sample if status.players.sample else []
            online_names_lower = {p.name.lower() for p in sample_players}
            all_player_names = [p.name for p in sample_players]
            total_players = status.players.online

            curr_owner = owner_lower in online_names_lower
            curr_moders_list = [m for m in MODERATORS if m.lower() in online_names_lower]
            curr_moders_count = len(curr_moders_list)

            # Update cache for commands
            current_status_cache["total_players"] = total_players
            current_status_cache["owner_online"] = curr_owner
            current_status_cache["online_moders"] = curr_moders_list
            current_status_cache["all_players"] = all_player_names

            # Hourly report at exact 00 minutes
            if owner_online is not None and current_minute == 0 and last_reported_hour != current_hour:
                owner_status_str = "🟢 <b>Online</b>" if curr_owner else "🔴 <b>Offline</b>"
                owner_line = f"👑 <b>Owner:</b> <code>{OWNER_NICKNAME}</code> — {owner_status_str}"
                
                if curr_moders_list:
                    moders_line = "🛡️ <b>Moderators:</b>\n" + "\n".join(f"   ▫️ <code>{m}</code>" for m in curr_moders_list)
                else:
                    moders_line = "🛡️ <b>Moderators:</b> <i>None online</i>"
                
                if all_player_names:
                    players_line = f"👥 <b>Players online ({total_players}):</b>\n" + "\n".join(f"   ▪️ <code>{p}</code>" for p in all_player_names)
                else:
                    players_line = f"👥 <b>Players online:</b> <code>{total_players}</code> (<i>No sample</i>)"

                ping_val = current_status_cache.get("ping")
                ping_str = f" | 🏓 <code>{ping_val}ms</code>" if ping_val is not None else ""

                hourly_text_template = (
                    f"📈 <b>Hourly update</b> ({{TIME_PLACEHOLDER}}){ping_str} — Players online: <code>{total_players}</code>\n\n"
                    f"{owner_line}\n\n"
                    f"{moders_line}\n\n"
                    f"{players_line}"
                )

                await broadcast(hourly_text_template, "notify_hourly", is_hourly=True)
                last_reported_hour = current_hour
            elif current_minute != 0:
                last_reported_hour = -1

            # First run initialization (silent sync, no spam on startup)
            if owner_online is None:
                owner_online = curr_owner
                moders_count = curr_moders_count
                if not curr_owner:
                    owner_last_seen = time.time()
                if curr_moders_count == 0:
                    moders_last_seen = time.time()
                await asyncio.sleep(CHECK_INTERVAL)
                continue

            current_timestamp = time.time()

            # Track timestamps for 45-minute offline checks
            if curr_owner and not owner_online:
                owner_45_notified = False
                current_status_cache["owner_completely_offline"] = False
            elif not curr_owner and owner_online:
                owner_last_seen = current_timestamp
                owner_45_notified = False
                current_status_cache["owner_completely_offline"] = False

            if curr_moders_count == 0 and moders_count > 0:
                moders_last_seen = current_timestamp
                moders_45_notified = False
            elif curr_moders_count > 0:
                moders_45_notified = False

            # Unified staff state change notification (prevents duplicate Preliminary alerts)
            if (curr_owner != owner_online) or (curr_moders_count != moders_count):
                mod_names_str = f"Moderators online: {', '.join(f'<code>{m}</code>' for m in curr_moders_list)}"

                if not curr_owner and curr_moders_count > 0:
                    await broadcast(
                        f"👑 <code>{OWNER_NICKNAME}</code> is <b>offline</b> (Preliminary).\n🛡️ {mod_names_str}.",
                        "notify_prelim"
                    )
                elif curr_owner and curr_moders_count == 0:
                    await broadcast(
                        f"👑 <code>{OWNER_NICKNAME}</code> is <b>online</b>, Moderators are <b>offline</b>.",
                        "notify_prelim"
                    )
                elif curr_owner and curr_moders_count > 0:
                    await broadcast(
                        f"👑 <code>{OWNER_NICKNAME}</code> is <b>online</b>.\n🛡️ {mod_names_str}.",
                        "notify_prelim"
                    )
                elif not curr_owner and curr_moders_count == 0:
                    await broadcast(
                        f"👑 <code>{OWNER_NICKNAME}</code> is <b>offline</b> (Preliminary), Moderators are <b>offline</b>.",
                        "notify_prelim"
                    )

            owner_online = curr_owner
            moders_count = curr_moders_count

            # 45-minute timeout checks
            owner_45_ready = (
                not owner_online
                and owner_last_seen is not None
                and (current_timestamp - owner_last_seen >= OFFLINE_TIMEOUT)
            )
            moders_45_ready = (
                moders_count == 0
                and moders_last_seen is not None
                and (current_timestamp - moders_last_seen >= OFFLINE_TIMEOUT)
            )

            if owner_45_ready:
                current_status_cache["owner_completely_offline"] = True

            if owner_45_ready and moders_45_ready and (not owner_45_notified or not moders_45_notified):
                await broadcast(
                    f"🚨 <b>CRITICAL STATUS UPDATE</b>\n\n"
                    f"❌ <code>{OWNER_NICKNAME}</code> is <b>completely offline</b> (>45m).\n"
                    f"❌ <b>All Moderators</b> are <b>completely offline</b> (>45m).",
                    "notify_prelim"
                )
                owner_45_notified = True
                moders_45_notified = True

            elif owner_45_ready and not owner_45_notified:
                await broadcast(
                    f"⚠️ <b>STATUS UPDATE</b>\n\n"
                    f"👑 <code>{OWNER_NICKNAME}</code> is now <b>completely offline</b> (>45m).",
                    "notify_prelim"
                )
                owner_45_notified = True

        except Exception as e:
            current_status_cache["is_down"] = True
            current_status_cache["last_error"] = str(e)
            print(f"[Server unavailable]: {e}")

        await asyncio.sleep(CHECK_INTERVAL)


async def main():
    print("Server Monitor Bot is running...")
    asyncio.create_task(monitor_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped.")