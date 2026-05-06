import datetime
import json
import os
import asyncio

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
        count = 1
        # Search through archived and active threads
        async for thread in channel.archived_threads(limit=100):
            name = thread.name.lower()
            if is_bonus and "bonus" in name:
                count += 1
            elif not is_bonus and "aotw #" in name and "bonus" not in name:
                count += 1

        for thread in channel.threads:
            name = thread.name.lower()
            if is_bonus and "bonus" in name:
                count += 1
            elif not is_bonus and "aotw" in name and "bonus" not in name:
                count += 1
        return count

    async def setup_hook(self):
        self.weekly_post.start()

    async def on_ready(self):
        print(f"{self.user} is online.")

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

    async def search_albums(self, query, limit=5):
        """Search Last.fm and return a list of up to `limit` album matches."""
        search_url = "http://ws.audioscrobbler.com/2.0/"
        params = {
            "method": "album.search",
            "album": query,
            "api_key": LASTFM_API_KEY,
            "format": "json",
            "limit": limit,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(search_url, params=params) as resp:
                data = await resp.json()
                results = data.get("results", {}).get("albummatches", {}).get("album", [])
                return results

    async def get_album_info(self, artist_name, album_name):
        """Fetch full album info (including high-res images) for a given artist+album."""
        search_url = "http://ws.audioscrobbler.com/2.0/"
        params = {
            "method": "album.getInfo",
            "api_key": LASTFM_API_KEY,
            "artist": artist_name,
            "album": album_name,
            "format": "json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(search_url, params=params) as resp:
                data = await resp.json()
                return data.get("album")

    async def post_album(self, queue):
        if not queue:
            return None

        is_bonus = queue == self.bonus_queue

        entry = queue.pop(0)
        self.save_queues()

        channel = self.get_channel(TARGET_CHANNEL_ID)
        if channel:
            # Create the Thread
            prefix = "BONUS AOTW" if is_bonus else "AOTW"
            current_count = await self.get_next_count(channel, is_bonus=is_bonus)

            thread = await channel.create_thread(
                name=f"{prefix} #{current_count}",
                type=discord.ChannelType.public_thread,
            )

            user_mention = f"<@{entry['user_id']}>"
            image_url = entry.get("image", "")

            message_content = (
                f"<@{AOTW_ROLE_ID}>\n"
                f"{prefix} #{current_count}\n"
                f"{entry['artist']} - {entry['title']}\n"
                f"PROPOZYCJA: {user_mention}\n"
                f"{image_url}"
            )

            await thread.send(content=f"{message_content}")

            return entry["title"]
        return "Channel not found."

    @tasks.loop(time=datetime.time(hour=18, minute=0))
    async def weekly_post(self):
        current_day = datetime.datetime.now().weekday()
        if current_day == 2:  # Wednesday
            await self.post_album(queue=bot.main_queue)
        elif current_day == 5:  # Saturday
            await self.post_album(queue=bot.bonus_queue)


bot = AlbumBot()


# DISCORD COMMANDS
@bot.group(name="album", invoke_without_command=True)
async def album(ctx):
    await ctx.send("`!album add`, `!album queue`")


@bot.group(name="bonus", invoke_without_command=True)
async def bonus(ctx):
    await ctx.send("`!bonus add`, `!bonus queue`")


# Add album to queue (interactive search + selection)
async def add_album(ctx, queue, query: str):
    async with ctx.typing():
        results = await bot.search_albums(query)

        if not results:
            return await ctx.send("❌ Not found.")

        # If there's only one candidate, select it automatically
        if len(results) == 1:
            choice = results[0]
        else:
            # Build a prompt listing top results
            lines = []
            for i, r in enumerate(results, start=1):
                name = r.get("name") or r.get("title")
                artist = r.get("artist")
                lines.append(f"{i}. {artist} - {name}")

            prompt = "Please choose an album by number (1-{n}) or type 'cancel' within 30 seconds:\n".format(
                n=len(results)
            ) + "\n".join(lines)

            await ctx.send(prompt)

            def check(m):
                return (
                    m.author == ctx.author
                    and m.channel == ctx.channel
                    and (
                        m.content.lower() == "cancel"
                        or (m.content.isdigit() and 1 <= int(m.content) <= len(results))
                    )
                )

            try:
                reply = await bot.wait_for("message", timeout=30.0, check=check)
            except asyncio.TimeoutError:
                return await ctx.send("⏲️ Timed out. Please try again.")

            if reply.content.lower() == "cancel":
                return await ctx.send("Cancelled.")

            idx = int(reply.content) - 1
            choice = results[idx]

        # Fetch full album info (higher-res images, canonical names)
        album_info = await bot.get_album_info(choice.get("artist"), choice.get("name"))
        data = album_info if album_info else choice

        images = data.get("image", []) if isinstance(data, dict) else []
        img = ""
        for image in reversed(images):
            if image.get("#text"):
                img = image["#text"]
                break

        artist_name = data.get("artist") or choice.get("artist")
        album_name = data.get("name") or choice.get("name")

        queue.append(
            {
                "artist": artist_name,
                "title": album_name,
                "image": img,
                "user_name": ctx.author.display_name,
                "user_id": ctx.author.id,
            }
        )
        bot.save_queues()
        await ctx.send(f"✅ Added **{artist_name} - {album_name}** to queue.")


# Show selected queue
async def show_queue(ctx, queue):
    if not queue:
        return await ctx.send("Empty.")
    embed = discord.Embed(
        title="Upcoming Album Queue",
        description=f"There are **{len(queue)}** albums waiting.",
        color=0xE74C3C,  # lightish red
    )
    for i, item in enumerate(queue[:10], 1):
        embed.add_field(
            name=f"{i}. {item['title']}",
            value=f"Artist: {item['artist']}\nSubmitted by: {item['user_name']}",
            inline=False,
        )

    first_img = queue[0]["image"]
    if first_img:
        embed.set_thumbnail(url=first_img)

    await ctx.send(embed=embed)


# Remove album from queue by 1-based index
async def remove_album(ctx, queue, index: int):
    if index < 1:
        return await ctx.send("❌ Index must be 1 or greater.")
    if not queue:
        return await ctx.send("❌ Queue is empty.")
    if index > len(queue):
        return await ctx.send(f"❌ Index out of range. There are {len(queue)} items.")

    removed = queue.pop(index - 1)
    bot.save_queues()
    await ctx.send(f"✅ Removed **{removed.get('artist')} - {removed.get('title')}** from queue.")


# Manually pop queue (bot owner only)
async def pop_queue(ctx, queue):
    result = await bot.post_album(queue)
    if result:
        await ctx.send(f"Manually triggered post for: **{result}**")
    else:
        await ctx.send("Queue is empty.")


# Helper to create analogous commands for standard and bonus queues
def register_queue_commands(group, queue):
    @group.command(name="add")
    async def _add(ctx, *, query):
        await add_album(ctx, queue, query)

    @group.command(name="queue")
    async def _list(ctx):
        await show_queue(ctx, queue)

    @group.command(name="remove")
    async def _remove(ctx, index: int):
        await remove_album(ctx, queue, index)

    @group.command(name="pop")
    @commands.is_owner()
    async def _pop(ctx):
        await pop_queue(queue)


register_queue_commands(album, bot.main_queue)
register_queue_commands(bonus, bot.bonus_queue)

bot.run(TOKEN)
