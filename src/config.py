import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()

TZ = ZoneInfo(os.environ["TIMEZONE"])
WORDLE_CHANNEL_ID = int(os.environ["WORDLE_CHANNEL_ID"])
GUILD_ID = int(os.environ["GUILD_ID"])
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
