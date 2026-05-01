import os
import datetime
import aiohttp
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID"))
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID"))
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")

intents = discord.Intents.default()
intents.message_content = True


class AlbumBot(commands.Bot):
    def __init__(self):
        # Changed prefix to '!' so 'album' can be the command
        super().__init__(command_prefix="!", intents=intents)
        self.queue = []

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

    @tasks.loop(time=datetime.time(hour=10, minute=0))
    async def weekly_post(self):
        if datetime.datetime.now().weekday() != 0 or not self.queue:
            return

        entry = self.queue.pop(0)
        channel = self.get_channel(TARGET_CHANNEL_ID)
        if channel:
            thread = await channel.create_thread(
                name=f"Weekly Album: {entry['title']}", type=discord.ChannelType.public_thread
            )
            embed = discord.Embed(title=entry["title"], color=0x3498DB)
            embed.set_image(url=entry["image"])
            embed.add_field(name="Artist", value=entry["artist"])
            embed.set_footer(text=f"Submitted by {entry['user']}")
            await thread.send(content="@everyone New Album of the Week!", embed=embed)


bot = AlbumBot()


# --- Command Group ---
@bot.group(name="album", invoke_without_command=True)
async def album(ctx):
    """Main command. Use !album add or !album queue."""
    await ctx.send('Use `!album add "Artist" "Album"` or `!album queue`')


@album.command(name="add")
async def add_album(ctx, *, query: str):
    """Fuzzy search: !album add after hours weekend"""
    async with ctx.typing():
        album_data = await bot.fetch_fuzzy_album(query)

        if album_data:
            # Last.fm image sizes: small, medium, large, extralarge
            # We try to get 'extralarge' (index 3)
            images = album_data.get("image", [])
            image_url = images[3]["#text"] if len(images) > 3 else ""

            bot.queue.append(
                {
                    "artist": album_data["artist"],
                    "title": album_data["name"],
                    "image": image_url,
                    "user": ctx.author.display_name,
                    "url": album_data.get("url", ""),
                }
            )

            # Confirmation embed (like fmbot)
            embed = discord.Embed(
                title="Added to Queue",
                description=f"**{album_data['name']}** by **{album_data['artist']}**",
                color=0x00FF00,
            )
            if image_url:
                embed.set_thumbnail(url=image_url)
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ Could not find any albums matching `{query}`")


@album.command(name="queue")
async def show_queue(ctx):
    """Displays the current album queue."""
    if not bot.queue:
        return await ctx.send("The queue is currently empty!")

    embed = discord.Embed(
        title="Upcoming Album Queue",
        description=f"There are **{len(bot.queue)}** albums waiting.",
        color=0xE74C3C,
    )

    for i, item in enumerate(bot.queue, 1):
        embed.add_field(
            name=f"{i}. {item['title']}",
            value=f"Artist: {item['artist']}\nSubmitted by: {item['user']}",
            inline=False,
        )

    # Optional: show the cover of the next one up
    embed.set_thumbnail(url=bot.queue[0]["image"])

    await ctx.send(embed=embed)


bot.run(TOKEN)
