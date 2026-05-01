import os
import json
import random
import datetime
import aiohttp
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

COUNT = int(5)

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID"))
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID"))
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
AOTW_ROLE_ID = os.getenv("AOTW_ROLE_ID")

intents = discord.Intents.default()
intents.message_content = True

DATA_DIR = "data"
QUEUE_FILE = f"{DATA_DIR}/queue.json"
QUOTES_FILE = f"{DATA_DIR}/quotes.json"


class AlbumBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        data = self.load_data(QUEUE_FILE, {"main": [], "bonus": []})
        self.main_queue = data.get("main", [])
        self.bonus_queue = data.get("bonus", [])
        # self.quotes = self.load_data(QUOTES_FILE, ["no quotes"])

    def load_data(self, filename, default_val):
        if os.path.exists(filename):
            with open(filename, "r") as f:
                return json.load(f)
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

    async def post_album(self, queue):
        if not queue:
            return None

        is_bonus = queue == bot.bonus_queue

        entry = queue.pop(0)
        self.save_queues()

        channel = self.get_channel(TARGET_CHANNEL_ID)
        if channel:
            # Create the Thread
            prefix = "BONUS AOTW" if is_bonus else "AOTW"
            current_count = await self.get_next_count(channel, is_bonus=is_bonus)

            thread = await channel.create_thread(
                name=f"{prefix} #{current_count}", type=discord.ChannelType.public_thread
            )

            message_content = (
                "<@503275690137878548>\n"
                f"{prefix} #{current_count}\n"
                f"**{entry['artist']} - {entry['title']}**\n"
                f"PROPOZYCJA: {f"<@{entry['user_id']}>"}\n"
                f"{entry['image']}"
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


@bot.group(name="album", invoke_without_command=True)
async def album(ctx):
    await ctx.send("`!album add`, `!album queue`")


@bot.group(name="bonus", invoke_without_command=True)
async def bonus(ctx):
    await ctx.send("`!bonus add`, `!bonus queue`")


# Add album to queue
async def add_album(ctx, queue, query: str):
    async with ctx.typing():
        data = await bot.fetch_fuzzy_album(query)
        if data:
            images = data.get("image", [])
            img = ""
            # Loop backwards from 'extralarge' to 'small' to find the first non-empty URL
            for image in reversed(images):
                if image.get("#text"):
                    img = image["#text"]
                    break
            queue.append(
                {
                    "artist": data["artist"],
                    "title": data["name"],
                    "image": img,
                    "user_name": ctx.author.display_name,
                    "user_id": ctx.author.id,
                }
            )
            bot.save_queues()
            await ctx.send(f"✅ Added **{data['name']}** to queue.")
        else:
            await ctx.send("❌ Not found.")


@album.command(name="add")
async def album_add(ctx, *, query: str):
    await add_album(ctx, bot.main_queue, query)


@bonus.command(name="add")
async def bonus_add(ctx, *, query: str):
    await add_album(ctx, bot.bonus_queue, query)


# Show selected queue
async def show_queue(ctx, queue):
    if not queue:
        return await ctx.send("Empty.")
    embed = discord.Embed(
        title="Upcoming Album Queue",
        description=f"There are **{len(queue)}** albums waiting.",
        color=0xE74C3C,
    )
    for i, item in enumerate(queue[:10], 1):
        embed.add_field(
            name=f"{i}. {item['title']}",
            value=f"Artist: {item["artist"]}\nSubmitted by: {item['user_name']}",
            inline=False,
        )

    first_img = queue[0]["image"]
    if first_img:
        embed.set_thumbnail(url=first_img)

    await ctx.send(embed=embed)


@album.command(name="queue")
async def album_queue(ctx):
    await show_queue(ctx, bot.main_queue)


@bonus.command(name="queue")
async def bonus_queue(ctx):
    await show_queue(ctx, bot.bonus_queue)


# Manually pop queue (bot owner only)
@commands.is_owner()
async def pop_manual(ctx):
    """Manually trigger the weekly post logic."""
    result = await bot.post_album()
    if result:
        await ctx.send(f"Manually triggered post for: **{result}**")
    else:
        await ctx.send("Queue is empty.")


@album.command(name="pop")
async def album_pop(ctx):
    await bot.post_album(bot.main_queue)


@bonus.command(name="pop")
async def bonus_pop(ctx):
    await bot.post_album(bot.bonus_queue)


bot.run(TOKEN)
