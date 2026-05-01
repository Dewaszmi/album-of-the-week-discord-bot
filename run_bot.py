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

intents = discord.Intents.default()
intents.message_content = True

DATA_DIR = "data"
QUEUE_FILE = f"{DATA_DIR}/queue.json"
QUOTES_FILE = f"{DATA_DIR}/quotes.json"


class AlbumBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.queue = self.load_data(QUEUE_FILE, [])
        self.quotes = self.load_data(QUOTES_FILE, ["no quotes"])

    def load_data(self, filename, default_val):
        if os.path.exists(filename):
            with open(filename, "r") as f:
                return json.load(f)
        return default_val

    def save_queue(self):
        with open(QUEUE_FILE, "w") as f:
            json.dump(self.queue, f, indent=4)

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
            "limit": 1,
        }

        async with aiohttp.ClientSession() as session:
            # Search last.fm for the album
            async with session.get(search_url, params=search_params) as resp:
                data = await resp.json()
                results = data.get("results", {}).get("albummatches", {}).get("album", [])

                if not results:
                    return None

                # Get the top match's name and artist
                best_match = results[0]
                artist_name = best_match["artist"]
                album_name = best_match["name"]

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
                return full_data.get("album")

    async def post_next_album(self):
        """Logic for popping the queue and posting the embed."""
        if not self.queue:
            return None

        entry = self.queue.pop(0)
        self.save_queue()  # Update file after popping

        channel = self.get_channel(TARGET_CHANNEL_ID)
        if channel:
            # Create the Thread
            thread = await channel.create_thread(
                name=f"AOTW #{COUNT}", type=discord.ChannelType.public_thread
            )

            # Build Embed
            embed = discord.Embed(title=entry["title"], color=0x3498DB)
            embed.set_image(url=entry["image"])
            embed.add_field(name="ALBUM", value=f"{entry["artist"]} - {entry["title"]}")
            embed.add_field(name="OD:", value=entry["user"])

            # Random Footer
            random_quote = random.choice(self.quotes)
            lyric = random_quote.get("lyric", "").replace("\\n", "\n")
            track = random_quote.get("track", "")
            artist = random_quote.get("artist", "")
            embed.set_footer(text=f"{lyric} - {track}, {artist}")

            await thread.send(content="Album of the Week", embed=embed)
            return entry["title"]
        return "Channel not found."

    @tasks.loop(time=datetime.time(hour=18, minute=0))
    async def weekly_post(self):
        if datetime.datetime.now().weekday() == 2:  # Wednesday
            await self.post_next_album()


bot = AlbumBot()


# --- Command Group ---
@bot.group(name="album", invoke_without_command=True)
async def album(ctx):
    """Main command. Use !album add or !album queue."""
    await ctx.send('Use `!album add "Artist" "Album"` or `!album queue`')


@album.command(name="add")
async def add_album(ctx, *, query: str):
    async with ctx.typing():
        data = await bot.fetch_fuzzy_album(query)
        if data:
            images = data.get("image", [])
            img = images[3]["#text"] if len(images) > 3 else ""

            bot.queue.append(
                {
                    "artist": data["artist"],
                    "title": data["name"],
                    "image": img,
                    "user": ctx.author.display_name,
                }
            )
            bot.save_queue()  # Persistence!
            await ctx.send(f"✅ Added **{data['name']}** to queue.")
        else:
            await ctx.send("❌ Not found.")


@album.command(name="queue")
async def show_queue(ctx):
    if not bot.queue:
        return await ctx.send("Empty.")
    embed = discord.Embed(
        title="Upcoming Album Queue",
        description=f"There are **{len(bot.queue)}** albums waiting.",
        color=0xE74C3C,
    )
    for i, item in enumerate(bot.queue[:10], 1):  # Show first 10
        embed.add_field(
            name=f"{i}. {item['title']}",
            value=f"Artist: {item["artist"]}\nSubmitted by: {item['user']}",
            inline=False,
        )
    embed.set_thumbnail(url=bot.queue[0]["image"])
    await ctx.send(embed=embed)


# @album.command(name="queue")
# async def show_queue(ctx):
#     """Displays the current album queue."""
#     if not bot.queue:
#         return await ctx.send("The queue is currently empty!")

#     embed = discord.Embed(
#         title="Upcoming Album Queue",
#         description=f"There are **{len(bot.queue)}** albums waiting.",
#         color=0xE74C3C,
#     )

#     for i, item in enumerate(bot.queue, 1):
#         embed.add_field(
#             name=f"{i}. {item['title']}",
#             value=f"Artist: {item['artist']}\nSubmitted by: {item['user']}",
#             inline=False,
#         )

#     # Optional: show the cover of the next one up
#     embed.set_thumbnail(url=bot.queue[0]["image"])

#     await ctx.send(embed=embed)


@album.command(name="pop")
@commands.is_owner()
async def pop_manual(ctx):
    """Manually trigger the weekly post logic."""
    result = await bot.post_next_album()
    if result:
        await ctx.send(f"Manually triggered post for: **{result}**")
    else:
        await ctx.send("Queue is empty.")


bot.run(TOKEN)
