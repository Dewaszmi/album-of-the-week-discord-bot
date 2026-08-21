import argparse
import os
import sys
from dotenv import load_dotenv

HERE = os.path.dirname(__file__)
MODULE_PATH = os.path.join(HERE, "discord-album-of-the-week-bot")
if MODULE_PATH not in sys.path:
    sys.path.insert(0, MODULE_PATH)

parser = argparse.ArgumentParser(description="Album of the Week Discord bot")
parser.add_argument(
    "--web",
    action="store_true",
    help="also start the web UI queue manager",
)
args = parser.parse_args()

load_dotenv()

from bot import AlbumBot
from bot_commands import register_commands

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is not set")

bot = AlbumBot(enable_web_ui=args.web)
register_commands(bot)

bot.run(TOKEN)
