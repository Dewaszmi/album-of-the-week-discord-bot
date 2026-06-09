import os
import sys
from dotenv import load_dotenv

HERE = os.path.dirname(__file__)
MODULE_PATH = os.path.join(HERE, "discord-album-of-the-week-bot")
if MODULE_PATH not in sys.path:
    sys.path.insert(0, MODULE_PATH)

load_dotenv()

from bot import AlbumBot
from bot_commands import register_commands

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is not set")

bot = AlbumBot()
register_commands(bot)

bot.run(TOKEN)
