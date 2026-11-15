import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
import re
import time

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
import discord
from discord import app_commands
from dotenv import load_dotenv
from mcstatus import JavaServer

# Load configuration from .env
load_dotenv()

TG_TOKEN = os.getenv("TG_TOKEN")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
SERVER_HOST = os.getenv("SERVER_HOST", "basyasmp.gomc.me")
OWNER_NICKNAME = os.getenv("OWNER_NICKNAME", "alexcrish")

# Parse comma-separated moderators preserving original casing
raw_mods = os.getenv("MODERATORS", "")
MODERATORS = [m.strip() for m in raw_mods.split(",") if m.strip()]

CHECK_INTERVAL = 15
OFFLINE_TIMEOUT = 45 * 60
USERS_FILE = "users.txt"
SETTINGS_FILE = "user_settings.json"

if not TG_TOKEN:
    raise ValueError("Error: TG_TOKEN not found in .env file!")
if not DISCORD_TOKEN:
    raise ValueError("Error: DISCORD_TOKEN not found in .env file!")

# Initialize Telegram bot
tg_bot = Bot(token=TG_TOKEN)
dp = Dispatcher()

# Initialize Discord bot
intents = discord.Intents.default()
dc_client = discord.Client(intents=intents)
dc_tree = app_commands.CommandTree(dc_client)

# Automatically handles standard ports, custom ports, and DNS SRV records
server = JavaServer.lookup(SERVER_HOST)

# Shared server status cache
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


def load_users() -> set[str]:
    """Loads prefixed user keys (e.g., 'tg_12345', 'dc_67890')."""
    if not os.path.exists(USERS_FILE):
        return set()
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        users = set()
        for line in f:
            val = line.strip()
            if not val:
                continue
            # Migrate legacy numeric IDs to Telegram prefix automatically
            if val.isdigit():
                users.add(f"tg_{val}")
            else:
                users.add(val)
        return users


def save_users(users: set[str]):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        for uid in sorted(users):
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


def load_all_user_settings() -> dict:
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
            migrated = {}
            for k, v in raw_data.items():
                key = f"tg_{k}" if k.isdigit() else k
                migrated[key] = v
            return migrated
    except Exception:
        return {}


def save_all_user_settings(data: dict):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def register_user_if_new(user_key: str):
    """Registers a platform-prefixed user on first interaction with default settings."""
    users = load_users()
    if user_key not in users:
        users.add(user_key)
        save_users(users)
        settings_data = load_all_user_settings()
        if user_key not in settings_data:
            settings_data[user_key] = default_user_settings()
            save_all_user_settings(settings_data)


def get_user_settings(user_key: str) -> dict:
    all_settings = load_all_user_settings()
    cfg = all_settings.get(user_key, default_user_settings())
    defaults = default_user_settings()
    for k, v in defaults.items():
        if k not in cfg:
            cfg[k] = v
    return cfg


def get_user_time_str(user_key: str, dt: datetime = None) -> str:
    if dt is None:
        dt = datetime.now(timezone.utc)
    settings = get_user_settings(user_key)
    offset_hours = settings.get("timezone_offset", 0)
    user_tz = timezone(timedelta(hours=offset_hours))
    return dt.astimezone(user_tz).strftime("%Y-%m-%d %H:%M:%S")


def html_to_discord_md(text: str) -> str:
    """Converts basic HTML tags used in Telegram messages into Discord Markdown."""
    text = re.sub(r"<b>(.*?)</b>", r"**\1**", text, flags=re.DOTALL)
    text = re.sub(r"<i>(.*?)</i>", r"*\1*", text, flags=re.DOTALL)
    text = re.sub(r"<code>(.*?)</code>", r"`\1`", text, flags=re.DOTALL)
    return text


async def broadcast(text_template: str, setting_key: str, is_hourly: bool = False):
    """Broadcasts a message to both Telegram and Discord users according to their settings."""
    settings_data = load_all_user_settings()
    users = load_users()
    utc_now = datetime.now(timezone.utc)

    for user_key in users:
        user_cfg = settings_data.get(user_key, default_user_settings())
        if not user_cfg.get(setting_key, True):
            continue

        text_to_send = text_template
        if is_hourly:
            offset_hours = user_cfg.get("timezone_offset", 0)
            user_tz = timezone(timedelta(hours=offset_hours))
            formatted_time = utc_now.astimezone(user_tz).strftime("%H:00")
            text_to_send = text_template.replace("{TIME_PLACEHOLDER}", formatted_time)

        if user_key.startswith("tg_"):
            tg_id = int(user_key.split("_", 1)[1])
            try:
                await tg_bot.send_message(chat_id=tg_id, text=text_to_send, parse_mode="HTML")
            except Exception as e:
                print(f"[TG Broadcast error to {tg_id}]: {e}")

        elif user_key.startswith("dc_"):
            dc_id = int(user_key.split("_", 1)[1])
            try:
                dc_user = dc_client.get_user(dc_id) or await dc_client.fetch_user(dc_id)
                if dc_user:
                    await dc_user.send(html_to_discord_md(text_to_send))
            except Exception as e:
                print(f"[DC Broadcast error to {dc_id}]: {e}")


def get_status_text_for_user(user_key: str) -> str:
    st = current_status_cache
    if st["is_down"]:
        err_msg = st.get("last_error")
        err_details = f"\n<code>{err_msg}</code>" if err_msg else ""
        return f"⚠️ <b>Server is currently unavailable.</b>{err_details}"

    settings = get_user_settings(user_key)
    show_owner = settings.get("show_owner", True)
    show_moders = settings.get("show_moders", True)
    show_players = settings.get("show_players", True)

    time_str = get_user_time_str(user_key)
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


def get_main_menu_text() -> str:
    return (
        "👋 <b>Welcome to MC Watchdog!</b>\n\n"
        "<b>Commands:</b>\n"
        " /status — get current server state\n"
        " /settings — configure display toggles & notifications\n"
        " /stop — disable all auto notifications"
    )


# ==========================================
# TELEGRAM UI & HANDLERS
# ==========================================

def get_tg_settings_keyboard(user_key: str) -> InlineKeyboardMarkup:
    settings = get_user_settings(user_key)

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


def get_tg_timezone_keyboard(user_key: str) -> InlineKeyboardMarkup:
    settings = get_user_settings(user_key)
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


def get_tg_status_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="🔄 Refresh Status", callback_data="refresh_status")],
        [InlineKeyboardButton(text="⚙️ Settings", callback_data="open_settings")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_tg_stop_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")]
    ])


@dp.message(Command("start"))
async def tg_cmd_start(message: Message):
    user_key = f"tg_{message.from_user.id}"
    register_user_if_new(user_key)
    await message.answer(get_main_menu_text(), parse_mode="HTML")


@dp.message(Command("settings"))
async def tg_cmd_settings(message: Message):
    user_key = f"tg_{message.from_user.id}"
    register_user_if_new(user_key)

    await message.answer(
        "⚙️ <b>Bot Settings & Preferences</b>\n\n"
        "Use the toggle buttons below to choose what information you want to see, manage notifications, and set your timezone.",
        reply_markup=get_tg_settings_keyboard(user_key),
        parse_mode="HTML"
    )


@dp.callback_query(lambda c: c.data in [
    "toggle_owner", "toggle_moders", "toggle_players",
    "toggle_hourly", "toggle_prelim", "open_tz_menu",
    "refresh_settings_status", "refresh_status", "open_settings", "main_menu"
] or c.data.startswith("set_tz_"))
async def tg_process_callback(callback: CallbackQuery):
    user_key = f"tg_{callback.from_user.id}"
    register_user_if_new(user_key)

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
                reply_markup=get_tg_settings_keyboard(user_key),
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
                reply_markup=get_tg_timezone_keyboard(user_key),
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
            user_cfg = get_user_settings(user_key)
            user_cfg["timezone_offset"] = offset_val
            settings_data[user_key] = user_cfg
            save_all_user_settings(settings_data)

            sign = "+" if offset_val >= 0 else ""
            await callback.message.edit_text(
                "🌐 <b>Select your Timezone</b>\n\n"
                f"Timezone successfully set to <b>UTC {sign}{offset_val}</b>!",
                reply_markup=get_tg_timezone_keyboard(user_key),
                parse_mode="HTML"
            )
            await callback.answer(f"Timezone updated to UTC {sign}{offset_val}")
        except Exception:
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
                get_status_text_for_user(user_key),
                reply_markup=get_tg_status_keyboard(),
                parse_mode="HTML"
            )
        except Exception:
            pass
        await callback.answer("Status refreshed!")
        return

    settings_data = load_all_user_settings()
    user_cfg = get_user_settings(user_key)

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
                get_status_text_for_user(user_key),
                reply_markup=get_tg_settings_keyboard(user_key),
                parse_mode="HTML"
            )
        except Exception:
            pass
        await callback.answer("Status refreshed!")
        return

    settings_data[user_key] = user_cfg
    save_all_user_settings(settings_data)

    try:
        await callback.message.edit_reply_markup(reply_markup=get_tg_settings_keyboard(user_key))
    except Exception:
        pass
    await callback.answer("Settings updated!")


@dp.message(Command("stop"))
async def tg_cmd_stop(message: Message):
    user_key = f"tg_{message.from_user.id}"
    register_user_if_new(user_key)

    settings_data = load_all_user_settings()
    user_cfg = get_user_settings(user_key)
    user_cfg["notify_hourly"] = False
    user_cfg["notify_prelim"] = False
    settings_data[user_key] = user_cfg
    save_all_user_settings(settings_data)

    await message.answer(
        "🔕 <b>All notifications disabled.</b> You can turn them back on in /settings.",
        reply_markup=get_tg_stop_keyboard(),
        parse_mode="HTML"
    )


@dp.message(Command("status"))
async def tg_cmd_status(message: Message):
    user_key = f"tg_{message.from_user.id}"
    register_user_if_new(user_key)

    if current_status_cache["is_down"]:
        err_msg = current_status_cache.get("last_error")
        err_details = f"\n<code>{err_msg}</code>" if err_msg else ""
        await message.answer(
            f"⚠️ <b>Server is currently unavailable.</b>{err_details}",
            reply_markup=get_tg_status_keyboard(),
            parse_mode="HTML"
        )
        return

    await message.answer(
        get_status_text_for_user(user_key),
        reply_markup=get_tg_status_keyboard(),
        parse_mode="HTML"
    )


# ==========================================
# DISCORD UI & SLASH COMMANDS
# ==========================================

class DiscordTimezoneSelect(discord.ui.Select):
    def __init__(self, user_key: str):
        self.user_key = user_key
        current_offset = get_user_settings(user_key).get("timezone_offset", 0)
        options = []
        # Discord Select allows up to 25 options; cover UTC-11 to UTC+13 (25 values)
        for offset in range(-11, 14):
            sign = "+" if offset >= 0 else ""
            label = f"UTC {sign}{offset}"
            options.append(discord.SelectOption(
                label=label,
                value=str(offset),
                default=(offset == current_offset)
            ))
        super().__init__(placeholder="Select your UTC timezone...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        offset_val = int(self.values[0])
        settings_data = load_all_user_settings()
        user_cfg = get_user_settings(self.user_key)
        user_cfg["timezone_offset"] = offset_val
        settings_data[self.user_key] = user_cfg
        save_all_user_settings(settings_data)

        sign = "+" if offset_val >= 0 else ""
        await interaction.response.edit_message(
            content=f"⚙️ **Bot Settings & Preferences**\n\nTimezone updated to **UTC {sign}{offset_val}**!",
            view=DiscordSettingsView(self.user_key)
        )


class DiscordSettingsView(discord.ui.View):
    def __init__(self, user_key: str):
        super().__init__(timeout=300)
        self.user_key = user_key
        self._build_items()

    def _build_items(self):
        self.clear_items()
        cfg = get_user_settings(self.user_key)

        toggles = [
            ("show_owner", "Show Owner", 0),
            ("show_moders", "Show Moderators", 0),
            ("show_players", "Show Players", 0),
            ("notify_hourly", "Hourly Updates", 1),
            ("notify_prelim", "Preliminary Alerts", 1),
        ]

        for key, label, row in toggles:
            enabled = cfg.get(key, True)
            icon = "✅" if enabled else "❌"
            style = discord.ButtonStyle.success if enabled else discord.ButtonStyle.secondary
            btn = discord.ui.Button(label=f"{icon} {label}", style=style, row=row)
            btn.callback = self._make_toggle_callback(key)
            self.add_item(btn)

        tz_select = DiscordTimezoneSelect(self.user_key)
        tz_select.row = 2
        self.add_item(tz_select)

    def _make_toggle_callback(self, setting_key: str):
        async def callback(interaction: discord.Interaction):
            settings_data = load_all_user_settings()
            user_cfg = get_user_settings(self.user_key)
            user_cfg[setting_key] = not user_cfg.get(setting_key, True)
            settings_data[self.user_key] = user_cfg
            save_all_user_settings(settings_data)

            self._build_items()
            await interaction.response.edit_message(view=self)
        return callback


class DiscordStatusView(discord.ui.View):
    def __init__(self, user_key: str):
        super().__init__(timeout=300)
        self.user_key = user_key

    @discord.ui.button(label="🔄 Refresh Status", style=discord.ButtonStyle.primary)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        text = html_to_discord_md(get_status_text_for_user(self.user_key))
        await interaction.response.edit_message(content=text, view=self)


@dc_tree.command(name="start", description="Welcome message and available commands")
async def dc_cmd_start(interaction: discord.Interaction):
    user_key = f"dc_{interaction.user.id}"
    register_user_if_new(user_key)
    await interaction.response.send_message(html_to_discord_md(get_main_menu_text()), ephemeral=True)


@dc_tree.command(name="status", description="Get current Minecraft server status")
async def dc_cmd_status(interaction: discord.Interaction):
    user_key = f"dc_{interaction.user.id}"
    register_user_if_new(user_key)
    text = html_to_discord_md(get_status_text_for_user(user_key))
    await interaction.response.send_message(text, view=DiscordStatusView(user_key), ephemeral=True)


@dc_tree.command(name="settings", description="Configure display toggles, notifications, and timezone")
async def dc_cmd_settings(interaction: discord.Interaction):
    user_key = f"dc_{interaction.user.id}"
    register_user_if_new(user_key)
    await interaction.response.send_message(
        "⚙️ **Bot Settings & Preferences**\n\n"
        "Use the buttons and dropdown below to customize your notifications and timezone:",
        view=DiscordSettingsView(user_key),
        ephemeral=True
    )


@dc_tree.command(name="stop", description="Disable all automatic notifications")
async def dc_cmd_stop(interaction: discord.Interaction):
    user_key = f"dc_{interaction.user.id}"
    register_user_if_new(user_key)

    settings_data = load_all_user_settings()
    user_cfg = get_user_settings(user_key)
    user_cfg["notify_hourly"] = False
    user_cfg["notify_prelim"] = False
    settings_data[user_key] = user_cfg
    save_all_user_settings(settings_data)

    await interaction.response.send_message(
        "🔕 **All notifications disabled.** You can turn them back on in `/settings`.",
        ephemeral=True
    )


@dc_client.event
async def on_ready():
    await dc_tree.sync()
    print(f"Discord bot logged in as {dc_client.user} (ID: {dc_client.user.id})")


# ==========================================
# SHARED MONITORING LOOP
# ==========================================

async def monitor_loop():
    owner_online = None
    owner_last_seen = None
    owner_45_notified = False

    moders_count = None
    moders_last_seen = None
    moders_45_notified = False
    
    server_down_notified = False

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
            server_down_notified = False

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

            owner_online = curr_owner
            moders_count = curr_moders_count

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

            if not server_down_notified:
                await broadcast(
                    f"🚨 <b>CRITICAL STATUS UPDATE</b>\n\n"
                    f"⚠️ <b>Server is down!</b>\n"
                    f"Error: <code>{e}</code>",
                    "notify_prelim"
                )
                server_down_notified = True

        await asyncio.sleep(CHECK_INTERVAL)


async def main():
    print("MC Watchdog (Telegram + Discord) is running...")
    asyncio.create_task(monitor_loop())
    await asyncio.gather(
        dp.start_polling(tg_bot),
        dc_client.start(DISCORD_TOKEN)
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped.")