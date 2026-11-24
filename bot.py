import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
import re
import sys
import time

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
import aiohttp
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
OWNER_TIKTOK = os.getenv("OWNER_TIKTOK", "@teamcrish_draft").strip()

# Parse comma-separated moderators preserving original casing
raw_mods = os.getenv("MODERATORS", "")
MODERATORS = [m.strip() for m in raw_mods.split(",") if m.strip()]

CHECK_INTERVAL = 15
STREAM_CHECK_INTERVAL = 120
STREAM_OFFLINE_CONFIRMATIONS = 2
OFFLINE_TIMEOUT = 45 * 60
QUERY_RETRY_INTERVAL = 5 * 60
USERS_FILE = "users.txt"
SETTINGS_FILE = "user_settings.json"
STATS_FILE = "player_stats.json"
BLACKLIST_FILE = "blacklist.json"

# ==========================================
# BLACKLIST CONFIGURATION (ADD NEW IDs HERE)
# ==========================================
DEFAULT_BAN_REASON = "You are not ПАТАЧНОCÇTY enough"
SHOW_BAN_REASON_TO_USER = True

DEFAULT_BLACKLISTED_IDS: set[str] = {
    "6862549355",
    "tg_6862549355",
    "9018380285",
    "tg_9018380285",
}

# Threshold for server downtime protection (confirm after N consecutive errors)
SERVER_DOWN_THRESHOLD = 3

# Minecraft color/formatting codes and standard username pattern
MC_FORMATTING_RE = re.compile(r"[§&][0-9A-FK-ORa-fk-or]")
MC_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")
MC_COUNTER_RE = re.compile(
    r"^\d+\s*/\s*\d+\s*(on|online|players?)?$|^(on|onli|online|offline|players?)$",
    re.IGNORECASE,
)

# Patterns for detecting active live stream in TikTok HTML/JSON payload
TT_LIVE_TRUE_RE = re.compile(
    r'("isLive"\s*:\s*true|"liveRoomId"\s*:\s*"[1-9][0-9]*"|"roomId"\s*:\s*"[1-9][0-9]*")',
    re.IGNORECASE,
)
TT_LIVE_FALSE_RE = re.compile(r'"isLive"\s*:\s*false', re.IGNORECASE)

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
query_port = os.getenv("QUERY_PORT")
if query_port:
    server.query_port = int(query_port)

# Shared server status cache
current_status_cache = {
    "total_players": 0,
    "owner_online": False,
    "owner_completely_offline": False,
    "online_moders": [],
    "all_players": [],
    "all_players_complete": True,
    "is_down": False,
    "ping": None,
    "last_error": None,
    "peak_today": 0,
    "peak_time": None,
    "owner_streaming": False,
    "last_stream_utc": None,
}


# ==========================================
# BLACKLIST SYSTEM
# ==========================================

def load_blacklist() -> set[str]:
    entries = set(DEFAULT_BLACKLISTED_IDS)
    if not os.path.exists(BLACKLIST_FILE):
        save_blacklist(entries)
        return entries
    try:
        with open(BLACKLIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    val = str(item).strip()
                    if val:
                        entries.add(val)
            elif isinstance(data, dict):
                for key in data.keys():
                    val = str(key).strip()
                    if val:
                        entries.add(val)
    except Exception as e:
        print(f"[Blacklist load warning]: {e}")
    return entries


def save_blacklist(entries: set[str]):
    tmp_file = f"{BLACKLIST_FILE}.tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(sorted(entries), f, indent=4, ensure_ascii=False)
    os.replace(tmp_file, BLACKLIST_FILE)


def get_blacklist_reason(user_key: str | None = None, raw_id: int | str | None = None) -> str | None:
    if is_blacklisted(user_key=user_key, raw_id=raw_id):
        return DEFAULT_BAN_REASON
    return None


def is_blacklisted(user_key: str | None = None, raw_id: int | str | None = None) -> bool:
    blacklist = load_blacklist()
    candidates: set[str] = set()

    if raw_id is not None:
        raw_str = str(raw_id).strip()
        if raw_str:
            candidates.update([raw_str, f"tg_{raw_str}", f"dc_{raw_str}"])

    if user_key:
        key_str = str(user_key).strip()
        if key_str:
            candidates.add(key_str)
            if "_" in key_str:
                _, pure_id = key_str.split("_", 1)
                if pure_id:
                    candidates.add(pure_id)

    return bool(candidates & blacklist)


def format_ban_notice_html(user_key: str | None = None, raw_id: int | str | None = None) -> str:
    reason = get_blacklist_reason(user_key=user_key, raw_id=raw_id)
    if SHOW_BAN_REASON_TO_USER and reason:
        return f"🚫 <b>You are banned from this bot.</b>\nReason: <code>{reason}</code>"
    return "🚫 <b>You are banned from this bot.</b>"


def format_ban_notice_plain(user_key: str | None = None, raw_id: int | str | None = None) -> str:
    reason = get_blacklist_reason(user_key=user_key, raw_id=raw_id)
    if SHOW_BAN_REASON_TO_USER and reason:
        return f"🚫 You are banned from this bot.\nReason: {reason}"
    return "🚫 You are banned from this bot."


def normalize_tiktok_handle(raw_handle: str) -> str:
    cleaned = (raw_handle or "").strip()
    if not cleaned:
        return ""
    if "tiktok.com/" in cleaned:
        cleaned = cleaned.split("tiktok.com/", 1)[1].split("?", 1)[0].strip("/")
    if not cleaned.startswith("@"):
        cleaned = f"@{cleaned}"
    return cleaned


OWNER_TIKTOK_HANDLE = normalize_tiktok_handle(OWNER_TIKTOK)


def get_tiktok_profile_url(handle: str) -> str:
    clean_user = handle.lstrip("@")
    return f"https://www.tiktok.com/@{clean_user}" if clean_user else ""


def sanitize_player_names(raw_names) -> list[str]:
    """Strip color/formatting prefixes from Essentials/tab entries and keep valid nicknames."""
    cleaned_players = []
    seen_lower = set()

    for raw_name in raw_names:
        if not raw_name:
            continue

        stripped = MC_FORMATTING_RE.sub("", str(raw_name)).strip()
        if not stripped or MC_COUNTER_RE.match(stripped):
            continue

        candidate = stripped if (MC_USERNAME_RE.match(stripped) and not stripped.isdigit()) else ""
        if not candidate:
            for token in reversed(re.split(r"[^A-Za-z0-9_]+", stripped)):
                if MC_USERNAME_RE.match(token) and not token.isdigit() and not MC_COUNTER_RE.match(token):
                    candidate = token
                    break

        if not candidate or MC_COUNTER_RE.match(candidate):
            continue

        lower_nick = candidate.lower()
        if lower_nick not in seen_lower:
            seen_lower.add(lower_nick)
            cleaned_players.append(candidate)

    return cleaned_players


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
            key = f"tg_{val}" if val.isdigit() else val
            if not is_blacklisted(user_key=key):
                users.add(key)
        return users


def save_users(users: set[str]):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        for uid in sorted(users):
            if not is_blacklisted(user_key=uid):
                f.write(f"{uid}\n")


def default_user_settings() -> dict:
    return {
        "timezone_offset": 0,
        "notify_hourly": True,
        "notify_prelim": True,
        "show_owner": True,
        "show_moders": True,
        "show_players": True,
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
                if not is_blacklisted(user_key=key):
                    migrated[key] = v
            return migrated
    except Exception:
        return {}


def save_all_user_settings(data: dict):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


# ==========================================
# STATS & PLAYER TRACKING SYSTEM (WITH 7-DAY ROTATION)
# ==========================================

def load_player_stats() -> dict:
    default_struct = {
        "dates": {},
        "peak_today": {"count": 0, "time": "", "date": ""},
        "stream_history": {
            "handle": OWNER_TIKTOK_HANDLE,
            "is_live": False,
            "last_stream_utc": None,
        },
    }
    if not os.path.exists(STATS_FILE):
        return default_struct
    try:
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "dates" not in data:
                return default_struct
            data.setdefault("peak_today", {"count": 0, "time": "", "date": ""})
            data.setdefault("stream_history", {
                "handle": OWNER_TIKTOK_HANDLE,
                "is_live": False,
                "last_stream_utc": None,
            })
            return data
    except Exception:
        return default_struct


def save_player_stats(data: dict):
    try:
        dates_keys = sorted(data.get("dates", {}).keys())
        if len(dates_keys) > 7:
            for old_date in dates_keys[:-7]:
                del data["dates"][old_date]
    except Exception:
        pass

    tmp_file = f"{STATS_FILE}.tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
    os.replace(tmp_file, STATS_FILE)


def sync_stream_state_to_stats(is_live: bool, seen_at_utc: datetime):
    iso_str = seen_at_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    stats = load_player_stats()
    sh = stats.setdefault("stream_history", {
        "handle": OWNER_TIKTOK_HANDLE,
        "is_live": False,
        "last_stream_utc": None,
    })
    sh["handle"] = OWNER_TIKTOK_HANDLE
    sh["is_live"] = is_live
    if is_live:
        sh["last_stream_utc"] = iso_str
        current_status_cache["last_stream_utc"] = iso_str
    elif current_status_cache.get("last_stream_utc") is None and sh.get("last_stream_utc"):
        current_status_cache["last_stream_utc"] = sh["last_stream_utc"]
    current_status_cache["owner_streaming"] = is_live
    save_player_stats(stats)


def update_player_activity(online_players: list[str], total_count: int):
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    stats = load_player_stats()
    dates = stats.setdefault("dates", {})
    day_data = dates.setdefault(date_str, {"players": {}, "peak": 0, "peak_time": time_str})

    if total_count > day_data.get("peak", 0):
        day_data["peak"] = total_count
        day_data["peak_time"] = time_str

    peak_today_dict = stats.setdefault("peak_today", {"count": 0, "time": "", "date": date_str})
    if peak_today_dict.get("date") != date_str:
        peak_today_dict["count"] = total_count
        peak_today_dict["time"] = time_str
        peak_today_dict["date"] = date_str
    elif total_count > peak_today_dict.get("count", 0):
        peak_today_dict["count"] = total_count
        peak_today_dict["time"] = time_str

    current_status_cache["peak_today"] = peak_today_dict["count"]
    current_status_cache["peak_time"] = peak_today_dict["time"]

    increment_minutes = CHECK_INTERVAL / 60.0
    players_dict = day_data.setdefault("players", {})

    for name in online_players:
        p_lower = name.lower()
        if p_lower not in players_dict:
            players_dict[p_lower] = {
                "real_name": name,
                "minutes": 0.0,
                "last_seen": time_str,
            }
        players_dict[p_lower]["real_name"] = name
        players_dict[p_lower]["minutes"] += increment_minutes
        players_dict[p_lower]["last_seen"] = time_str

    save_player_stats(stats)


def register_user_if_new(user_key: str) -> bool:
    if is_blacklisted(user_key=user_key):
        return False
    users = load_users()
    if user_key not in users:
        users.add(user_key)
        save_users(users)
        settings_data = load_all_user_settings()
        if user_key not in settings_data:
            settings_data[user_key] = default_user_settings()
            save_all_user_settings(settings_data)
    return True


def get_user_settings(user_key: str) -> dict:
    all_settings = load_all_user_settings()
    cfg = all_settings.get(user_key, default_user_settings())
    defaults = default_user_settings()
    for k, v in defaults.items():
        if k not in cfg:
            cfg[k] = v
    return cfg


def get_user_tz(user_key: str) -> timezone:
    offset_hours = get_user_settings(user_key).get("timezone_offset", 0)
    return timezone(timedelta(hours=offset_hours))


def get_user_time_str(user_key: str, dt: datetime = None) -> str:
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.astimezone(get_user_tz(user_key)).strftime("%Y-%m-%d %H:%M:%S")


def convert_hhmm_to_user_time(user_key: str, time_hhmm: str) -> str:
    """Converts a time string 'HH:MM' (saved in UTC) to the user's timezone."""
    if not time_hhmm or ":" not in time_hhmm:
        return time_hhmm
    try:
        parts = time_hhmm.split(":")
        utc_now = datetime.now(timezone.utc)
        dt_utc = utc_now.replace(hour=int(parts[0]), minute=int(parts[1]), second=0, microsecond=0)
        return dt_utc.astimezone(get_user_tz(user_key)).strftime("%H:%M")
    except Exception:
        return time_hhmm


def format_last_stream_for_user(user_key: str, stats_data: dict = None) -> str:
    if stats_data is None:
        stats_data = load_player_stats()
    sh = stats_data.get("stream_history", {})
    is_live = bool(current_status_cache.get("owner_streaming"))
    last_utc_str = current_status_cache.get("last_stream_utc") or sh.get("last_stream_utc")
    handle_display = OWNER_TIKTOK_HANDLE or sh.get("handle") or "@teamcrish_draft"

    if is_live:
        return f"🔴 <b>LIVE now</b> ({handle_display})"

    if not last_utc_str:
        return f"<i>No stream recorded yet ({handle_display})</i>"

    try:
        dt_utc = datetime.fromisoformat(last_utc_str.replace("Z", "+00:00"))
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        local_dt = dt_utc.astimezone(get_user_tz(user_key))
        return f"<code>{local_dt.strftime('%Y-%m-%d %H:%M')}</code> ({handle_display})"
    except Exception:
        return f"<code>{last_utc_str}</code> ({handle_display})"


def get_owner_stream_line_html() -> str:
    if not OWNER_TIKTOK_HANDLE:
        return ""
    profile_url = get_tiktok_profile_url(OWNER_TIKTOK_HANDLE)
    if current_status_cache.get("owner_streaming"):
        return f'🎥 <b>Stream:</b> <code>{OWNER_NICKNAME}</code> is <b>LIVE on TikTok</b> (<a href="{profile_url}">{OWNER_TIKTOK_HANDLE}</a>)'
    return f'🎥 <b>Stream:</b> <code>{OWNER_NICKNAME}</code> is not streaming right now (<code>{OWNER_TIKTOK_HANDLE}</code>)'


def get_player_check_status_label(target_lower: str) -> str:
    if current_status_cache.get("total_players", 0) <= 0:
        return "🔴 Offline"
    is_currently_online = target_lower in {p.lower() for p in current_status_cache.get("all_players", [])}
    if is_currently_online:
        return "🟢 Online right now"
    if not current_status_cache.get("all_players_complete", True):
        return "🟡 Possibly offline (partial list)"
    if target_lower == OWNER_NICKNAME.lower() and current_status_cache.get("owner_completely_offline", False):
        return "🔴 Completely offline"
    return "🔴 Offline"


def format_staff_status_lines(
    owner_online: bool,
    owner_completely_offline: bool,
    online_moders: list[str],
    players_list_complete: bool
) -> tuple[str, str]:
    """Formats owner and moderator status blocks accounting for partial player lists."""
    if owner_online:
        owner_status = "🟢 <b>Online</b>"
    elif not players_list_complete:
        owner_status = "🟡 <b>Possibly offline</b> (<i>partial list</i>)"
    elif owner_completely_offline:
        owner_status = "🔴 <b>Completely offline</b>"
    else:
        owner_status = "🔴 <b>Offline</b>"

    owner_str = f"👑 <b>Owner:</b> <code>{OWNER_NICKNAME}</code> — {owner_status}"

    if online_moders:
        moders_str = "🛡️ <b>Moderators:</b>\n" + "\n".join(f"   ▫️ <code>{m}</code>" for m in online_moders)
        if not players_list_complete and len(online_moders) < len(MODERATORS):
            moders_str += "\n   <i>(Others possibly offline — partial list)</i>"
    else:
        if not players_list_complete and MODERATORS:
            moders_str = "🛡️ <b>Moderators:</b> <i>Possibly offline (partial list)</i>"
        else:
            moders_str = "🛡️ <b>Moderators:</b> <i>None online</i>"

    return owner_str, moders_str


def html_to_discord_md(text: str) -> str:
    text = re.sub(r'<a\s+href="([^"]+)">(.*?)</a>', r"[\2](\1)", text, flags=re.DOTALL)
    text = re.sub(r"<b>(.*?)</b>", r"**\1**", text, flags=re.DOTALL)
    text = re.sub(r"<i>(.*?)</i>", r"*\1*", text, flags=re.DOTALL)
    text = re.sub(r"<code>(.*?)</code>", r"`\1`", text, flags=re.DOTALL)
    return text


async def broadcast(text_template: str, setting_key: str, is_hourly: bool = False):
    settings_data = load_all_user_settings()
    users = load_users()
    utc_now = datetime.now(timezone.utc)

    for user_key in users:
        if is_blacklisted(user_key=user_key):
            continue

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
                await tg_bot.send_message(
                    chat_id=tg_id,
                    text=text_to_send,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
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

    players_list_complete = st.get("all_players_complete", True)
    owner_str, moders_str = format_staff_status_lines(
        owner_online=st["owner_online"],
        owner_completely_offline=st.get("owner_completely_offline", False),
        online_moders=st["online_moders"],
        players_list_complete=players_list_complete,
    )

    all_players = st.get("all_players", []) if st.get("total_players", 0) > 0 else []
    players_count = str(st["total_players"])
    if st["total_players"] > 0 and not players_list_complete:
        players_count += ", partial list"
    if all_players:
        players_str = f"👥 <b>Players online ({players_count}):</b>\n" + "\n".join(f"   ▪️ <code>{p}</code>" for p in all_players)
    else:
        players_str = f"👥 <b>Players online:</b> <code>{st['total_players']}</code>"

    has_content = False
    if show_owner:
        lines.append(owner_str)
        stream_line = get_owner_stream_line_html()
        if stream_line:
            lines.append(stream_line)
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
        " /check &lt;nickname&gt; — check player online stats & info\n"
        " /stats — general session statistics, peak online & last stream\n"
        " /settings — configure display toggles & notifications\n"
        " /stop — disable all auto notifications"
    )


async def check_tiktok_live_status() -> bool | None:
    """Returns True if live, False if offline, or None if check was inconclusive."""
    if not OWNER_TIKTOK_HANDLE:
        return None
    url = get_tiktok_profile_url(OWNER_TIKTOK_HANDLE)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
        "Cache-Control": "no-cache",
    }
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url, allow_redirects=True) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text(errors="ignore")
                if not html:
                    return None

                has_live_true = bool(TT_LIVE_TRUE_RE.search(html))
                has_live_false = bool(TT_LIVE_FALSE_RE.search(html))

                if has_live_true and not has_live_false:
                    return True
                if has_live_false and not has_live_true:
                    return False

                # If both appear in SSR payload, prefer explicit liveRoomId/roomId only if isLive is not false
                if has_live_true and has_live_false:
                    if re.search(r'"isLive"\s*:\s*true', html, re.IGNORECASE):
                        return True
                    return False

                # Valid profile HTML loaded without active live markers
                if "webapp.user-detail" in html or '"userInfo"' in html or '"uniqueId"' in html:
                    return False

                return None
    except Exception as e:
        print(f"[TikTok stream check warning]: {e}")
        return None


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
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")],
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
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_tg_stop_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")]
    ])


async def tg_ensure_allowed(message_or_cb: Message | CallbackQuery) -> bool:
    user = message_or_cb.from_user
    user_key = f"tg_{user.id}" if user else None
    if is_blacklisted(user_key=user_key, raw_id=user.id if user else None):
        notice_html = format_ban_notice_html(user_key=user_key, raw_id=user.id if user else None)
        notice_plain = format_ban_notice_plain(user_key=user_key, raw_id=user.id if user else None)
        if isinstance(message_or_cb, CallbackQuery):
            await message_or_cb.answer(notice_plain, show_alert=True)
        elif isinstance(message_or_cb, Message):
            await message_or_cb.answer(notice_html, parse_mode="HTML")
        return False
    if user_key:
        register_user_if_new(user_key)
    return True


@dp.message(Command("start"))
async def tg_cmd_start(message: Message):
    if not await tg_ensure_allowed(message):
        return
    await message.answer(get_main_menu_text(), parse_mode="HTML")


@dp.message(Command("settings"))
async def tg_cmd_settings(message: Message):
    if not await tg_ensure_allowed(message):
        return
    user_key = f"tg_{message.from_user.id}"

    await message.answer(
        "⚙️ <b>Bot Settings & Preferences</b>\n\n"
        "Use the toggle buttons below to choose what information you want to see, manage notifications, and set your timezone.",
        reply_markup=get_tg_settings_keyboard(user_key),
        parse_mode="HTML",
    )


@dp.message(Command("status"))
async def tg_cmd_status(message: Message):
    if not await tg_ensure_allowed(message):
        return
    user_key = f"tg_{message.from_user.id}"

    if current_status_cache["is_down"]:
        err_msg = current_status_cache.get("last_error")
        err_details = f"\n<code>{err_msg}</code>" if err_msg else ""
        await message.answer(
            f"⚠️ <b>Server is currently unavailable.</b>{err_details}",
            reply_markup=get_tg_status_keyboard(),
            parse_mode="HTML",
        )
        return

    await message.answer(
        get_status_text_for_user(user_key),
        reply_markup=get_tg_status_keyboard(),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@dp.message(Command("stats"))
async def tg_cmd_stats(message: Message):
    if not await tg_ensure_allowed(message):
        return
    user_key = f"tg_{message.from_user.id}"

    stats = load_player_stats()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    day_data = stats.get("dates", {}).get(today_str, {"players": {}, "peak": 0, "peak_time": "N/A"})
    players = day_data.get("players", {})

    peak = day_data.get("peak", 0)
    peak_time_utc = day_data.get("peak_time", "N/A")
    peak_time_local = convert_hhmm_to_user_time(user_key, peak_time_utc)
    last_stream_str = format_last_stream_for_user(user_key, stats)

    text = [
        f"📊 <b>Server Statistics for Today ({today_str})</b>\n",
        f"📈 <b>Peak Online:</b> <code>{peak}</code> players (at {peak_time_local})",
        f"👥 <b>Unique players tracked today:</b> <code>{len(players)}</code>",
        f"🎥 <b>Last stream ({OWNER_NICKNAME}):</b> {last_stream_str}\n",
    ]

    if players:
        sorted_players = sorted(players.values(), key=lambda x: x["minutes"], reverse=True)[:10]
        text.append("🏆 <b>Top active players today:</b>")
        for idx, p in enumerate(sorted_players, 1):
            mins = int(p["minutes"])
            hours = mins // 60
            rem_mins = mins % 60
            time_formatted = f"{hours}h {rem_mins}m" if hours > 0 else f"{rem_mins}m"
            last_seen_local = convert_hhmm_to_user_time(user_key, p["last_seen"])
            text.append(f"   {idx}. <code>{p['real_name']}</code> — <b>{time_formatted}</b> (last seen: {last_seen_local})")

    await message.answer("\n".join(text), parse_mode="HTML", disable_web_page_preview=True)


@dp.message(Command("check"))
async def tg_cmd_check(message: Message):
    if not await tg_ensure_allowed(message):
        return
    user_key = f"tg_{message.from_user.id}"

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("⚠️ Please specify a player nickname. Example: <code>/check alexcrish</code>", parse_mode="HTML")
        return

    target_nick = args[1].strip()
    target_lower = target_nick.lower()

    stats = load_player_stats()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    day_data = stats.get("dates", {}).get(today_str, {"players": {}})
    players = day_data.get("players", {})

    player_info = players.get(target_lower)

    role_info = "Player"
    if target_lower == OWNER_NICKNAME.lower():
        role_info = "👑 Server Owner"
    elif target_lower in [m.lower() for m in MODERATORS]:
        role_info = "🛡️ Moderator"

    online_status_str = get_player_check_status_label(target_lower)
    extra_stream_line = ""
    if target_lower == OWNER_NICKNAME.lower():
        extra_stream_line = f"\n🎥 <b>Last stream:</b> {format_last_stream_for_user(user_key, stats)}"

    if not player_info:
        await message.answer(
            f"🔍 <b>Player Info:</b> <code>{target_nick}</code>\n\n"
            f"🏷️ Role: <b>{role_info}</b>\n"
            f"📌 Status: <code>{online_status_str}</code>{extra_stream_line}\n\n"
            f"<i>No recorded activity for today ({today_str}).</i>",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return

    mins = int(player_info["minutes"])
    hours = mins // 60
    rem_mins = mins % 60
    time_formatted = f"{hours}h {rem_mins}m" if hours > 0 else f"{rem_mins}m"
    last_seen_local = convert_hhmm_to_user_time(user_key, player_info["last_seen"])

    await message.answer(
        f"🔍 <b>Player Info:</b> <code>{player_info['real_name']}</code>\n\n"
        f"🏷️ Role: <b>{role_info}</b>\n"
        f"📌 Status: <code>{online_status_str}</code>{extra_stream_line}\n"
        f"⏱️ Online today: <b>{time_formatted}</b>\n"
        f"🕒 Last seen today: <code>{last_seen_local}</code>",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@dp.callback_query(lambda c: c.data in [
    "toggle_owner", "toggle_moders", "toggle_players",
    "toggle_hourly", "toggle_prelim", "open_tz_menu",
    "refresh_settings_status", "refresh_status", "open_settings", "main_menu"
] or c.data.startswith("set_tz_"))
async def tg_process_callback(callback: CallbackQuery):
    if not await tg_ensure_allowed(callback):
        return
    user_key = f"tg_{callback.from_user.id}"

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
                parse_mode="HTML",
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
                parse_mode="HTML",
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
                parse_mode="HTML",
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
                parse_mode="HTML",
                disable_web_page_preview=True,
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
                parse_mode="HTML",
                disable_web_page_preview=True,
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
    if not await tg_ensure_allowed(message):
        return
    user_key = f"tg_{message.from_user.id}"

    settings_data = load_all_user_settings()
    user_cfg = get_user_settings(user_key)
    user_cfg["notify_hourly"] = False
    user_cfg["notify_prelim"] = False
    settings_data[user_key] = user_cfg
    save_all_user_settings(settings_data)

    await message.answer(
        "🔕 <b>All notifications disabled.</b> You can turn them back on in /settings.",
        reply_markup=get_tg_stop_keyboard(),
        parse_mode="HTML",
    )


# ==========================================
# DISCORD UI & SLASH COMMANDS
# ==========================================

async def dc_ensure_allowed(interaction: discord.Interaction) -> bool:
    user_id = interaction.user.id if interaction.user else None
    user_key = f"dc_{user_id}" if user_id is not None else None
    if is_blacklisted(user_key=user_key, raw_id=user_id):
        msg = format_ban_notice_plain(user_key=user_key, raw_id=user_id)
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
        return False
    if user_key:
        register_user_if_new(user_key)
    return True


class DiscordTimezoneSelect(discord.ui.Select):
    def __init__(self, user_key: str):
        self.user_key = user_key
        current_offset = get_user_settings(user_key).get("timezone_offset", 0)
        options = []
        for offset in range(-11, 14):
            sign = "+" if offset >= 0 else ""
            label = f"UTC {sign}{offset}"
            options.append(discord.SelectOption(
                label=label,
                value=str(offset),
                default=(offset == current_offset),
            ))
        super().__init__(placeholder="Select your UTC timezone...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if not await dc_ensure_allowed(interaction):
            return

        offset_val = int(self.values[0])
        settings_data = load_all_user_settings()
        user_cfg = get_user_settings(self.user_key)
        user_cfg["timezone_offset"] = offset_val
        settings_data[self.user_key] = user_cfg
        save_all_user_settings(settings_data)

        sign = "+" if offset_val >= 0 else ""
        await interaction.response.edit_message(
            content=f"⚙️ **Bot Settings & Preferences**\n\nTimezone updated to **UTC {sign}{offset_val}**!",
            view=DiscordSettingsView(self.user_key),
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
            if not await dc_ensure_allowed(interaction):
                return

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
        if not await dc_ensure_allowed(interaction):
            return

        text = html_to_discord_md(get_status_text_for_user(self.user_key))
        await interaction.response.edit_message(content=text, view=self)


@dc_tree.command(name="start", description="Welcome message and available commands")
async def dc_cmd_start(interaction: discord.Interaction):
    if not await dc_ensure_allowed(interaction):
        return
    await interaction.response.send_message(html_to_discord_md(get_main_menu_text()), ephemeral=True)


@dc_tree.command(name="status", description="Get current Minecraft server status")
async def dc_cmd_status(interaction: discord.Interaction):
    if not await dc_ensure_allowed(interaction):
        return
    user_key = f"dc_{interaction.user.id}"
    text = html_to_discord_md(get_status_text_for_user(user_key))
    await interaction.response.send_message(text, view=DiscordStatusView(user_key), ephemeral=True)


@dc_tree.command(name="check", description="Check player online stats & info")
@app_commands.describe(nickname="Minecraft player nickname")
async def dc_cmd_check(interaction: discord.Interaction, nickname: str):
    if not await dc_ensure_allowed(interaction):
        return
    user_key = f"dc_{interaction.user.id}"

    target_nick = nickname.strip()
    target_lower = target_nick.lower()

    stats = load_player_stats()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    day_data = stats.get("dates", {}).get(today_str, {"players": {}})
    players = day_data.get("players", {})

    player_info = players.get(target_lower)

    role_info = "Player"
    if target_lower == OWNER_NICKNAME.lower():
        role_info = "👑 Server Owner"
    elif target_lower in [m.lower() for m in MODERATORS]:
        role_info = "🛡️ Moderator"

    online_status_str = get_player_check_status_label(target_lower)
    extra_stream_line = ""
    if target_lower == OWNER_NICKNAME.lower():
        extra_stream_line = f"\n🎥 **Last stream:** {html_to_discord_md(format_last_stream_for_user(user_key, stats))}"

    if not player_info:
        msg = (
            f"🔍 **Player Info:** `{target_nick}`\n\n"
            f"🏷️ Role: **{role_info}**\n"
            f"📌 Status: `{online_status_str}`{extra_stream_line}\n\n"
            f"*No recorded activity for today ({today_str}).*"
        )
        await interaction.response.send_message(msg, ephemeral=True)
        return

    mins = int(player_info["minutes"])
    hours = mins // 60
    rem_mins = mins % 60
    time_formatted = f"{hours}h {rem_mins}m" if hours > 0 else f"{rem_mins}m"
    last_seen_local = convert_hhmm_to_user_time(user_key, player_info["last_seen"])

    msg = (
        f"🔍 **Player Info:** `{player_info['real_name']}`\n\n"
        f"🏷️ Role: **{role_info}**\n"
        f"📌 Status: `{online_status_str}`{extra_stream_line}\n"
        f"⏱️ Online today: **{time_formatted}**\n"
        f"🕒 Last seen today: `{last_seen_local}`"
    )
    await interaction.response.send_message(msg, ephemeral=True)


@dc_tree.command(name="stats", description="General session statistics, peak online and last stream")
async def dc_cmd_stats(interaction: discord.Interaction):
    if not await dc_ensure_allowed(interaction):
        return
    user_key = f"dc_{interaction.user.id}"

    stats = load_player_stats()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    day_data = stats.get("dates", {}).get(today_str, {"players": {}, "peak": 0, "peak_time": "N/A"})
    players = day_data.get("players", {})

    peak = day_data.get("peak", 0)
    peak_time_utc = day_data.get("peak_time", "N/A")
    peak_time_local = convert_hhmm_to_user_time(user_key, peak_time_utc)
    last_stream_str = html_to_discord_md(format_last_stream_for_user(user_key, stats))

    text = [
        f"📊 **Server Statistics for Today ({today_str})**\n",
        f"📈 **Peak Online:** `{peak}` players (at {peak_time_local})",
        f"👥 **Unique players tracked today:** `{len(players)}`",
        f"🎥 **Last stream ({OWNER_NICKNAME}):** {last_stream_str}\n",
    ]

    if players:
        sorted_players = sorted(players.values(), key=lambda x: x["minutes"], reverse=True)[:10]
        text.append("🏆 **Top active players today:**")
        for idx, p in enumerate(sorted_players, 1):
            mins = int(p["minutes"])
            hours = mins // 60
            rem_mins = mins % 60
            time_formatted = f"{hours}h {rem_mins}m" if hours > 0 else f"{rem_mins}m"
            last_seen_local = convert_hhmm_to_user_time(user_key, p["last_seen"])
            text.append(f"   {idx}. `{p['real_name']}` — **{time_formatted}** (last seen: {last_seen_local})")

    await interaction.response.send_message("\n".join(text), ephemeral=True)


@dc_tree.command(name="settings", description="Configure display toggles, notifications, and timezone")
async def dc_cmd_settings(interaction: discord.Interaction):
    if not await dc_ensure_allowed(interaction):
        return
    user_key = f"dc_{interaction.user.id}"
    await interaction.response.send_message(
        "⚙️ **Bot Settings & Preferences**\n\n"
        "Use the buttons and dropdown below to customize your notifications and timezone:",
        view=DiscordSettingsView(user_key),
        ephemeral=True,
    )


@dc_tree.command(name="stop", description="Disable all automatic notifications")
async def dc_cmd_stop(interaction: discord.Interaction):
    if not await dc_ensure_allowed(interaction):
        return
    user_key = f"dc_{interaction.user.id}"

    settings_data = load_all_user_settings()
    user_cfg = get_user_settings(user_key)
    user_cfg["notify_hourly"] = False
    user_cfg["notify_prelim"] = False
    settings_data[user_key] = user_cfg
    save_all_user_settings(settings_data)

    await interaction.response.send_message(
        "🔕 **All notifications disabled.** You can turn them back on in `/settings`.",
        ephemeral=True,
    )


@dc_client.event
async def on_ready():
    await dc_tree.sync()
    print(f"Discord bot logged in as {dc_client.user} (ID: {dc_client.user.id})")


# ==========================================
# STREAM MONITOR LOOP (TIKTOK)
# ==========================================

async def stream_monitor_loop():
    initial_stats = load_player_stats()
    sh = initial_stats.get("stream_history", {})
    current_status_cache["last_stream_utc"] = sh.get("last_stream_utc")
    # Always start offline until confirmed live; avoids stale "LIVE" after restart
    current_status_cache["owner_streaming"] = False
    if sh.get("is_live"):
        sync_stream_state_to_stats(False, datetime.now(timezone.utc))

    prev_live: bool = False
    offline_streak: int = 0

    while True:
        live_state = await check_tiktok_live_status()
        now_utc = datetime.now(timezone.utc)

        if live_state is True:
            offline_streak = 0
            sync_stream_state_to_stats(True, now_utc)
            if not prev_live:
                profile_url = get_tiktok_profile_url(OWNER_TIKTOK_HANDLE)
                await broadcast(
                    f"🎥 <b>STREAM STARTED</b>\n\n"
                    f"👑 <code>{OWNER_NICKNAME}</code> is now <b>LIVE on TikTok</b>!\n"
                    f"🔗 <a href=\"{profile_url}\">{OWNER_TIKTOK_HANDLE}</a>",
                    "notify_prelim",
                )
            prev_live = True

        elif live_state is False:
            if prev_live:
                offline_streak += 1
                if offline_streak >= STREAM_OFFLINE_CONFIRMATIONS:
                    sync_stream_state_to_stats(False, now_utc)
                    await broadcast(
                        f"🎥 <b>STREAM ENDED</b>\n\n"
                        f"👑 <code>{OWNER_NICKNAME}</code> finished streaming on <code>{OWNER_TIKTOK_HANDLE}</code>.",
                        "notify_prelim",
                    )
                    prev_live = False
                    offline_streak = 0
            else:
                offline_streak = 0
                sync_stream_state_to_stats(False, now_utc)

        await asyncio.sleep(STREAM_CHECK_INTERVAL)


# ==========================================
# SHARED MONITORING LOOP (WITH TIMEOUT FILTERING)
# ==========================================

async def monitor_loop():
    owner_online = None
    owner_last_seen = None
    owner_45_notified = False

    moders_count = None
    moders_last_seen = None
    moders_45_notified = False

    server_down_notified = False
    consecutive_errors = 0

    last_reported_hour = -1
    owner_lower = OWNER_NICKNAME.lower()
    query_retry_after = 0.0

    while True:
        now_time_utc = datetime.now(timezone.utc)
        current_hour = now_time_utc.hour
        current_minute = now_time_utc.minute

        try:
            status = await server.async_status()

            consecutive_errors = 0
            current_status_cache["is_down"] = False
            current_status_cache["last_error"] = None
            current_status_cache["ping"] = round(status.latency)
            server_down_notified = False

            total_players = max(0, int(status.players.online or 0))
            sample_players = status.players.sample if (status.players.sample and total_players > 0) else []
            all_player_names = sanitize_player_names([p.name for p in sample_players])
            if total_players == 0:
                all_player_names = []
            players_list_complete = True if total_players == 0 else (len(all_player_names) >= total_players)

            if total_players > 0 and not players_list_complete and time.monotonic() >= query_retry_after:
                try:
                    query_status = await server.async_query(tries=1)
                    query_total = max(0, int(query_status.players.online or 0))
                    query_players = query_status.players
                    query_names = getattr(query_players, "list", None)
                    if query_names is None:
                        query_names = getattr(query_players, "names", [])
                    query_names = sanitize_player_names(query_names) if query_total > 0 else []

                    if query_total == 0 or query_names:
                        all_player_names = query_names
                        total_players = query_total
                        players_list_complete = True if total_players == 0 else (len(all_player_names) >= total_players)
                        query_retry_after = (
                            0.0 if players_list_complete
                            else time.monotonic() + QUERY_RETRY_INTERVAL
                        )
                    else:
                        query_retry_after = time.monotonic() + QUERY_RETRY_INTERVAL
                except (OSError, asyncio.TimeoutError):
                    query_retry_after = time.monotonic() + QUERY_RETRY_INTERVAL

            if total_players == 0:
                all_player_names = []
                players_list_complete = True

            online_names_lower = {name.lower() for name in all_player_names}

            curr_owner = (total_players > 0) and (owner_lower in online_names_lower)
            curr_moders_list = [m for m in MODERATORS if m.lower() in online_names_lower] if total_players > 0 else []
            curr_moders_count = len(curr_moders_list)

            current_status_cache["total_players"] = total_players
            current_status_cache["owner_online"] = curr_owner
            current_status_cache["online_moders"] = curr_moders_list
            current_status_cache["all_players"] = all_player_names
            current_status_cache["all_players_complete"] = players_list_complete

            try:
                update_player_activity(all_player_names, total_players)
            except Exception as stats_err:
                print(f"[Stats update error]: {stats_err}")

            # Hourly report at exact 00 minutes
            if owner_online is not None and current_minute == 0 and last_reported_hour != current_hour:
                owner_line, moders_line = format_staff_status_lines(
                    owner_online=curr_owner,
                    owner_completely_offline=current_status_cache.get("owner_completely_offline", False),
                    online_moders=curr_moders_list,
                    players_list_complete=players_list_complete,
                )

                stream_line = get_owner_stream_line_html()
                stream_block = f"\n{stream_line}" if stream_line else ""

                if all_player_names:
                    players_count = str(total_players)
                    if not players_list_complete:
                        players_count += ", partial list"
                    players_line = f"👥 <b>Players online ({players_count}):</b>\n" + "\n".join(f"   ▪️ <code>{p}</code>" for p in all_player_names)
                else:
                    players_line = f"👥 <b>Players online:</b> <code>{total_players}</code>"

                ping_val = current_status_cache.get("ping")
                ping_str = f" | 🏓 <code>{ping_val}ms</code>" if ping_val is not None else ""

                hourly_text_template = (
                    f"📈 <b>Hourly update</b> ({{TIME_PLACEHOLDER}}){ping_str} — Players online: <code>{total_players}</code>\n\n"
                    f"{owner_line}{stream_block}\n\n"
                    f"{moders_line}\n\n"
                    f"{players_line}"
                )

                await broadcast(hourly_text_template, "notify_hourly", is_hourly=True)
                last_reported_hour = current_hour
            elif current_minute != 0:
                last_reported_hour = -1

            if owner_online is None:
                owner_online = curr_owner
                moders_count = curr_moders_count
                if not curr_owner and players_list_complete:
                    owner_last_seen = time.time()
                if curr_moders_count == 0 and players_list_complete:
                    moders_last_seen = time.time()
                await asyncio.sleep(CHECK_INTERVAL)
                continue

            current_timestamp = time.time()

            if curr_owner:
                if not owner_online:
                    owner_45_notified = False
                    current_status_cache["owner_completely_offline"] = False
                owner_last_seen = None
            elif players_list_complete:
                if owner_online or owner_last_seen is None:
                    owner_last_seen = current_timestamp
                    owner_45_notified = False
                    current_status_cache["owner_completely_offline"] = False
            else:
                owner_last_seen = None
                current_status_cache["owner_completely_offline"] = False

            if curr_moders_count > 0:
                if moders_count == 0:
                    moders_45_notified = False
                moders_last_seen = None
            elif players_list_complete:
                if moders_count > 0 or moders_last_seen is None:
                    moders_last_seen = current_timestamp
                    moders_45_notified = False
            else:
                moders_last_seen = None

            owner_45_ready = (
                players_list_complete
                and not curr_owner
                and owner_last_seen is not None
                and (current_timestamp - owner_last_seen >= OFFLINE_TIMEOUT)
            )
            moders_45_ready = (
                players_list_complete
                and curr_moders_count == 0
                and moders_last_seen is not None
                and (current_timestamp - moders_last_seen >= OFFLINE_TIMEOUT)
            )

            if owner_45_ready:
                current_status_cache["owner_completely_offline"] = True

            owner_online = curr_owner
            moders_count = curr_moders_count

            if owner_45_ready and moders_45_ready and not (owner_45_notified and moders_45_notified):
                await broadcast(
                    f"🚨 <b>CRITICAL STATUS UPDATE</b>\n\n"
                    f"❌ <code>{OWNER_NICKNAME}</code> is <b>completely offline</b> (>45m).\n"
                    f"❌ <b>All Moderators</b> are <b>completely offline</b> (>45m).",
                    "notify_prelim",
                )
                owner_45_notified = True
                moders_45_notified = True

            elif owner_45_ready and not owner_45_notified:
                await broadcast(
                    f"⚠️ <b>STATUS UPDATE</b>\n\n"
                    f"👑 <code>{OWNER_NICKNAME}</code> is now <b>completely offline</b> (>45m).",
                    "notify_prelim",
                )
                owner_45_notified = True

        except Exception as e:
            consecutive_errors += 1
            err_text = type(e).__name__ if not str(e).strip() else f"{type(e).__name__}: {e}"
            err_text = err_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            current_status_cache["last_error"] = err_text
            print(f"[Server warning / attempt {consecutive_errors}]: {e}")

            if consecutive_errors >= SERVER_DOWN_THRESHOLD:
                current_status_cache["is_down"] = True

                if not server_down_notified:
                    await broadcast(
                        f"🚨 <b>CRITICAL STATUS UPDATE</b>\n\n"
                        f"⚠️ <b>Server is down!</b>\n"
                        f"Error: <code>{err_text}</code>",
                        "notify_prelim",
                    )
                    server_down_notified = True

        await asyncio.sleep(CHECK_INTERVAL)


async def main():
    print("MC Watchdog (Telegram + Discord + TikTok Stream) is running...")
    monitor_task = asyncio.create_task(monitor_loop())
    stream_task = asyncio.create_task(stream_monitor_loop())
    service_tasks = [
        asyncio.create_task(dp.start_polling(tg_bot)),
        asyncio.create_task(dc_client.start(DISCORD_TOKEN)),
    ]

    try:
        done, _ = await asyncio.wait(
            service_tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in done:
            task.result()
    finally:
        for task in [*service_tasks, monitor_task, stream_task]:
            task.cancel()
        await asyncio.gather(*service_tasks, monitor_task, stream_task, return_exceptions=True)
        await tg_bot.session.close()
        await dc_client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)