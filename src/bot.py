import os
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

import db
import wordle_service

load_dotenv()

TZ = ZoneInfo(os.environ["TIMEZONE"])
WORDLE_CHANNEL_ID = int(os.environ["WORDLE_CHANNEL_ID"])

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


# ── Events ────────────────────────────────────────────────────────────────────

@client.event
async def on_message(message):
    if message.channel.id != WORDLE_CHANNEL_ID:
        return

    counted = wordle_service.process_message(message)
    if counted:
        await message.add_reaction("✅")

    db.set_last_message_id(message.id)


@client.event
async def on_ready():
    db.init_db()

    for guild in client.guilds:
        await tree.sync(guild=guild)
    print(f"Logged in as {client.user} — slash commands synced.")

    channel = client.get_channel(WORDLE_CHANNEL_ID)
    if channel is None:
        print(f"ERROR: channel {WORDLE_CHANNEL_ID} not found — check WORDLE_CHANNEL_ID in .env")
        return

    last_id = db.get_last_message_id()
    after = discord.Object(id=last_id) if last_id else None
    label = "incremental" if last_id else "full"
    print(f"Scanning channel history ({label})...")

    newest_id = last_id or 0
    stored = 0
    async for message in channel.history(limit=None, after=after, oldest_first=True):
        if wordle_service.process_message(message):
            stored += 1
        if message.id > newest_id:
            newest_id = message.id

    if newest_id != (last_id or 0):
        db.set_last_message_id(newest_id)

    print(f"Scan complete — {stored} new Wordle result(s) stored.")
    streak_warning.start()


# ── Commands ──────────────────────────────────────────────────────────────────

@tree.command(name="ranking", description="Show the Wordle streak leaderboard")
async def ranking(interaction: discord.Interaction):
    await interaction.response.defer()

    rows = wordle_service.get_rankings()

    if not rows:
        await interaction.followup.send("No Wordle results found yet.")
        return

    lines = ["**Wordle Streak Leaderboard**", ""]
    for i, (username, streak) in enumerate(rows, 1):
        suffix = "day" if streak == 1 else "days"
        lines.append(f"{i}. **{username}** — {streak} {suffix}")

    await interaction.followup.send("\n".join(lines))


# ── Scheduled tasks ───────────────────────────────────────────────────────────

@tasks.loop(minutes=1)
async def streak_warning():
    now = datetime.now(TZ)
    if now.hour != 23 or now.minute != 0:
        return

    today_str = now.date().isoformat()
    if db.get_meta("warning_sent_date") == today_str:
        return  # Already sent today

    channel = client.get_channel(WORDLE_CHANNEL_ID)
    if channel is None:
        return

    at_risk = wordle_service.get_at_risk_users()

    db.set_meta("warning_sent_date", today_str)  # Mark before posting to avoid duplicates on restart

    if not at_risk:
        return

    mentions = " ".join(f"<@{uid}>" for uid, _ in at_risk)
    await channel.send(
        f"⏰ **1 hour left to complete today's Wordle!**\n"
        f"{mentions}\n"
        f"Your streak is at risk — don't break the chain!"
    )


client.run(os.environ["DISCORD_TOKEN"])
