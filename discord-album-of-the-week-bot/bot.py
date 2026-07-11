import datetime
import json
import os
from urllib.parse import unquote

import aiohttp
import discord
import yaml
from discord.ext import commands, tasks
from dotenv import load_dotenv

from album_service import album_data_to_preview, artist_name
from queue_store import QueueStore
from web_server import start_web_server

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID"))
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID"))
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
AOTW_ROLE_ID = os.getenv("AOTW_ROLE_ID")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
WEB_UI_HOST = os.getenv("WEB_UI_HOST", "127.0.0.1")
WEB_UI_PORT = int(os.getenv("WEB_UI_PORT", "8080"))

intents = discord.Intents.default()
intents.message_content = True

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(ROOT_DIR, "config.yaml")
DATA_DIR = "data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)
QUEUE_FILE = f"{DATA_DIR}/queue.json"
QUOTES_FILE = f"{DATA_DIR}/quotes.json"

LASTFM_ALBUM_URL_PREFIXES = (
    "https://www.last.fm/music/",
    "http://www.last.fm/music/",
    "https://last.fm/music/",
    "http://last.fm/music/",
)

DEFAULT_CONFIG = {
    "normal": {"weekday": 2, "post_hour": 12, "post_minute": 0},
    "bonus": {"weekday": 5, "post_hour": 12, "post_minute": 0},
}


def is_lastfm_album_url(text: str) -> bool:
    return any(text.startswith(prefix) for prefix in LASTFM_ALBUM_URL_PREFIXES)


def parse_lastfm_album_url(url: str):
    prefix = next((p for p in LASTFM_ALBUM_URL_PREFIXES if url.startswith(p)), None)
    if not prefix:
        return None

    path = url[len(prefix) :].split("?")[0].rstrip("/")
    if "/+/" in path:
        artist_part, album_part = path.split("/+/", 1)
    else:
        slash_idx = path.find("/")
        if slash_idx == -1:
            return None
        artist_part = path[:slash_idx]
        album_part = path[slash_idx + 1 :]

    artist = unquote(artist_part.replace("+", " "))
    album = unquote(album_part.replace("+", " "))
    return artist, album


class AlbumBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.store = QueueStore(QUEUE_FILE)
        self.config = self.load_config()

    @property
    def main_queue(self):
        return self.store.main

    @property
    def bonus_queue(self):
        return self.store.bonus

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                if os.path.getsize(CONFIG_FILE) == 0:
                    return DEFAULT_CONFIG

                with open(CONFIG_FILE, "r") as f:
                    data = yaml.safe_load(f)
                    return data if data else DEFAULT_CONFIG
            except (yaml.YAMLError, IOError) as e:
                print(
                    f"⚠️ Warning: Could not parse {CONFIG_FILE}. Resetting to default. Error: {e}"
                )
                return DEFAULT_CONFIG
        return DEFAULT_CONFIG

    def load_data(self, filename, default_val={}):
        if os.path.exists(filename):
            try:
                if os.path.getsize(filename) == 0:
                    return default_val

                with open(filename, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(
                    f"⚠️ Warning: Could not parse {filename}. Resetting to default. Error: {e}"
                )
                return default_val
        return default_val

    def save_queues(self):
        self.store.save()

    async def get_next_count(self, channel, is_bonus=False):
        """Calculates the next AOTW number by scanning existing threads."""
        normal_prefix = "album of the week"
        bonus_prefix = "bonus"
        count = 1
        # Search through archived and active threads
        async for thread in channel.archived_threads(limit=100):
            name = thread.name.lower()
            if is_bonus and "bonus" in name:
                count += 1
            elif not is_bonus and normal_prefix in name and bonus_prefix not in name:
                count += 1

        for thread in channel.threads:
            name = thread.name.lower()
            if is_bonus and "bonus" in name:
                count += 1
            elif not is_bonus and normal_prefix in name and bonus_prefix not in name:
                count += 1
        return count

    def _post_allowed_mentions(self, entry):
        roles = []
        if AOTW_ROLE_ID:
            try:
                roles.append(discord.Object(id=int(AOTW_ROLE_ID)))
            except (TypeError, ValueError):
                pass

        user_id = entry.get("user_id")
        users = [discord.Object(id=int(user_id))] if user_id else False

        return discord.AllowedMentions(
            roles=roles or False,
            users=users,
            everyone=False,
        )

    def _queue_schedule(self, queue_name):
        queue_config = self.config.get(queue_name, DEFAULT_CONFIG[queue_name])
        return (
            queue_config.get("weekday", DEFAULT_CONFIG[queue_name]["weekday"]),
            queue_config.get("post_hour", DEFAULT_CONFIG[queue_name]["post_hour"]),
            queue_config.get("post_minute", DEFAULT_CONFIG[queue_name]["post_minute"]),
        )

    async def setup_hook(self):
        await start_web_server(
            self, WEB_UI_HOST, WEB_UI_PORT, ADMIN_TOKEN
        )
        _, normal_hour, normal_minute = self._queue_schedule("normal")
        _, bonus_hour, bonus_minute = self._queue_schedule("bonus")
        self.normal_weekly_post.change_interval(
            time=datetime.time(hour=normal_hour, minute=normal_minute)
        )
        self.bonus_weekly_post.change_interval(
            time=datetime.time(hour=bonus_hour, minute=bonus_minute)
        )
        self.normal_weekly_post.start()
        self.bonus_weekly_post.start()

    async def on_ready(self):
        # Print online status and which guild/role/channel the bot will use
        guild = self.get_guild(GUILD_ID)
        guild_name = guild.name if guild else "Unknown"

        # Prepare role display (try to resolve a role name if possible)
        role_display = "None"
        if AOTW_ROLE_ID:
            try:
                role_id_int = int(AOTW_ROLE_ID)
            except Exception:
                role_id_int = None
            if role_id_int:
                role_obj = guild.get_role(role_id_int) if guild else None
                if role_obj:
                    role_display = f"{role_obj.name} (<@&{role_id_int}>)"
                else:
                    role_display = f"<@&{role_id_int}>"

        # Resolve target channel name
        channel = self.get_channel(TARGET_CHANNEL_ID)
        channel_name = channel.name if channel else "Unknown"

        print(
            f"{self.user} is online. Connected to guild: {guild_name}; Ping role: {role_display}; Target channel: {channel_name}"
        )

    async def _fetch_album_info(self, session, artist_name, album_name):
        search_url = "http://ws.audioscrobbler.com/2.0/"
        info_params = {
            "method": "album.getInfo",
            "api_key": LASTFM_API_KEY,
            "artist": artist_name,
            "album": album_name,
            "format": "json",
        }
        async with session.get(search_url, params=info_params) as resp:
            full_data = await resp.json()
            return full_data.get("album")

    async def fetch_album_from_url(self, url):
        """Fetches album info directly from a Last.fm album URL."""
        parsed = parse_lastfm_album_url(url)
        if not parsed:
            return None

        artist_name, album_name = parsed
        async with aiohttp.ClientSession() as session:
            return await self._fetch_album_info(session, artist_name, album_name)

    async def fetch_fuzzy_album(self, query):
        """Searches Last.fm for the best match and returns full album info."""
        search_url = "http://ws.audioscrobbler.com/2.0/"
        search_params = {
            "method": "album.search",
            "album": query,
            "api_key": LASTFM_API_KEY,
            "format": "json",
            "limit": 5,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(search_url, params=search_params) as resp:
                data = await resp.json()
                results = (
                    data.get("results", {}).get("albummatches", {}).get("album", [])
                )

                if not results:
                    return None

                artist_name = None
                album_name = None

                for match in results:
                    images = match.get("image", [])
                    if any(img.get("#text") for img in images):
                        artist_name = match["artist"]
                        album_name = match["name"]
                        break

                if not artist_name:
                    artist_name = results[0]["artist"]
                    album_name = results[0]["name"]

            album_data = await self._fetch_album_info(session, artist_name, album_name)
            return album_data if album_data else results[0]

    async def fetch_album_info(self, artist_name: str, album_name: str):
        async with aiohttp.ClientSession() as session:
            return await self._fetch_album_info(session, artist_name, album_name)

    async def search_albums(self, query: str, limit: int = 8) -> list[dict]:
        query = query.strip()
        if not query:
            return []

        if is_lastfm_album_url(query):
            data = await self.fetch_album_from_url(query)
            return [album_data_to_preview(data)] if data else []

        search_url = "http://ws.audioscrobbler.com/2.0/"
        search_params = {
            "method": "album.search",
            "album": query,
            "api_key": LASTFM_API_KEY,
            "format": "json",
            "limit": limit,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(search_url, params=search_params) as resp:
                data = await resp.json()
                results = (
                    data.get("results", {}).get("albummatches", {}).get("album", [])
                )
                if not results:
                    return []
                if isinstance(results, dict):
                    results = [results]

            previews = []
            for match in results[:limit]:
                match_artist = artist_name(match.get("artist"))
                match_album = match.get("name", "")
                album_data = await self._fetch_album_info(
                    session, match_artist, match_album
                )
                if album_data:
                    previews.append(album_data_to_preview(album_data))
                else:
                    previews.append(
                        {
                            "artist": match_artist,
                            "title": match_album,
                            "url": match.get("url", ""),
                            "image": "",
                        }
                    )
            return previews

    async def post_album(self, queue):
        if not queue:
            return None

        is_bonus = queue == self.bonus_queue

        entry = queue.pop(0)
        self.save_queues()

        channel = self.get_channel(TARGET_CHANNEL_ID)
        if channel:
            # Create the Thread
            prefix = "Bonus Album" if is_bonus else "Album of the week"
            current_count = await self.get_next_count(channel, is_bonus=is_bonus)

            thread = await channel.create_thread(
                name=f"{prefix} {current_count}",
                type=discord.ChannelType.public_thread,
            )

            user_mention = f"<@{entry['user_id']}>"
            image_url = entry.get("image", "")

            # Use role mention format for roles (<@&id>) so it pings correctly
            role_mention = f"<@&{AOTW_ROLE_ID}>" if AOTW_ROLE_ID else ""
            message_content = (
                f"{role_mention}\n"
                f"**{prefix} #{current_count}**\n"
                f"{entry['artist']} - {entry['title']}\n"
                f"PROPOZYCJA: {user_mention}\n"
            )
            allowed_mentions = self._post_allowed_mentions(entry)

            # Send the message; include image in an embed if available
            if image_url:
                embed = discord.Embed()
                embed.set_image(url=image_url)
                await thread.send(
                    content=message_content,
                    embed=embed,
                    allowed_mentions=allowed_mentions,
                )
            else:
                await thread.send(
                    content=message_content,
                    allowed_mentions=allowed_mentions,
                )

            return entry["title"]
        return "Channel not found."

    @tasks.loop()
    async def normal_weekly_post(self):
        weekday, _, _ = self._queue_schedule("normal")
        if datetime.datetime.now().weekday() == weekday:
            await self.post_album(queue=self.main_queue)

    @tasks.loop()
    async def bonus_weekly_post(self):
        weekday, _, _ = self._queue_schedule("bonus")
        if datetime.datetime.now().weekday() == weekday:
            await self.post_album(queue=self.bonus_queue)

    @normal_weekly_post.before_loop
    async def _before_normal_weekly_post(self):
        await self.wait_until_ready()

    @bonus_weekly_post.before_loop
    async def _before_bonus_weekly_post(self):
        await self.wait_until_ready()
