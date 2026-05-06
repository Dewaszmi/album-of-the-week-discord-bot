import datetime
import json
import os

import aiohttp
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID"))
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID"))
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
AOTW_ROLE_ID = os.getenv("AOTW_ROLE_ID")

intents = discord.Intents.default()
intents.message_content = True

DATA_DIR = "data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)
QUEUE_FILE = f"{DATA_DIR}/queue.json"
QUOTES_FILE = f"{DATA_DIR}/quotes.json"


class AlbumBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        data = self.load_data(QUEUE_FILE, {"main": [], "bonus": []})
        self.main_queue = data.get("main", [])
        self.bonus_queue = data.get("bonus", [])

    def load_data(self, filename, default_val={}):
        if os.path.exists(filename):
            try:
                if os.path.getsize(filename) == 0:
                    return default_val

                with open(filename, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"⚠️ Warning: Could not parse {filename}. Resetting to default. Error: {e}")
                return default_val
        return default_val

    def save_queues(self):
        with open(QUEUE_FILE, "w") as f:
            json.dump({"main": self.main_queue, "bonus": self.bonus_queue}, f, indent=4)

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

    async def setup_hook(self):
        self.weekly_post.start()

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
            # Search last.fm for the album
            async with session.get(search_url, params=search_params) as resp:
                data = await resp.json()
                results = data.get("results", {}).get("albummatches", {}).get("album", [])

                if not results:
                    return None

                # 1. FIND THE BEST CANDIDATE (First one with an image)
                artist_name = None
                album_name = None

                for match in results:
                    images = match.get("image", [])
                    # Check if at least one image entry has a URL
                    if any(img.get("#text") for img in images):
                        artist_name = match["artist"]
                        album_name = match["name"]
                        break

                # Fallback: if NONE have images, just take the first result anyway
                if not artist_name:
                    artist_name = results[0]["artist"]
                    album_name = results[0]["name"]

            # Get full info (including high-res images) for that specific match
            info_params = {
                "method": "album.getInfo",
                "api_key": LASTFM_API_KEY,
                "artist": artist_name,
                "album": album_name,
                "format": "json",
            }
            async with session.get(search_url, params=info_params) as resp:
                full_data = await resp.json()
                album_data = full_data.get("album")
                return album_data if album_data else results[0]

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

            # Send the message; include image in an embed if available
            if image_url:
                embed = discord.Embed()
                embed.set_image(url=image_url)
                await thread.send(content=message_content, embed=embed)
            else:
                await thread.send(content=message_content)

            return entry["title"]
        return "Channel not found."

    @tasks.loop(time=datetime.time(hour=12, minute=0))
    async def weekly_post(self):
        current_day = datetime.datetime.now().weekday()
        if current_day == 2:  # Wednesday
            await self.post_album(queue=self.main_queue)
        elif current_day == 5:  # Saturday
            await self.post_album(queue=self.bonus_queue)
