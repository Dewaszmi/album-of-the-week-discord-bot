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

    async def fetch_album_data(self, artist, album_name):
        url = "http://ws.audioscrobbler.com/2.0/"
        params = {
            "method": "album.getInfo",
            "api_key": LASTFM_API_KEY,
            "artist": artist,
            "album": album_name,
            "format": "json",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("album")
                return None

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
async def add_album(ctx, artist: str, title: str):
    """Usage: !album add \"FKA Twigs\" \"LP1\" """
    async with ctx.typing():
        album_data = await bot.fetch_album_data(artist, title)

        if album_data and "image" in album_data:
            # Last.fm returns images in a list; index 3 is usually 'extralarge'
            image_url = album_data["image"][3]["#text"]

            bot.queue.append(
                {
                    "artist": album_data["artist"],
                    "title": album_data["name"],
                    "image": image_url,
                    "user": ctx.author.display_name,
                }
            )
            await ctx.send(f"✅ Added **{album_data['name']}** by **{album_data['artist']}** to the queue!")
        else:
            await ctx.send("❌ Could not find that album. Make sure to use quotes for names with spaces!")


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
