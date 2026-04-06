import os
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

import db
import games
import game_service

load_dotenv()

TZ = ZoneInfo(os.environ["TIMEZONE"])
WORDLE_CHANNEL_ID = int(os.environ["WORDLE_CHANNEL_ID"])
GUILD_ID = int(os.environ["GUILD_ID"])

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

ATTEMPT_EMOJI = {
    1: "😱",  # lucky/shocked
    2: "🧠",  # big brain
    3: "😎",  # smooth
    4: "😐",  # mid
    5: "😬",  # sweaty
    6: "💀",  # that was close
}


# ── Events ────────────────────────────────────────────────────────────────────

@client.event
async def on_message(message):
    if message.channel.id == WORDLE_CHANNEL_ID and message.author.name == "mihneainatorul":
        await message.add_reaction("🖕")
        return

    if message.author.bot:
        return

    if message.channel.id != WORDLE_CHANNEL_ID:
        return

    results = game_service.process_message(message)

    any_stored = False
    any_duplicate = False
    for result, game_key, attempts in results:
        if result == game_service.ProcessResult.STORED:
            any_stored = True
            emoji = ATTEMPT_EMOJI.get(attempts, "🪦") if attempts is not None else "🪦"
            await message.add_reaction(emoji)
        elif result == game_service.ProcessResult.DUPLICATE:
            any_duplicate = True

    if any_stored:
        await message.add_reaction("✅")
    if any_duplicate:
        await message.add_reaction("❌")

    db.set_last_message_id(message.id)


@client.event
async def on_ready():
    db.init_db()

    guild = discord.Object(id=GUILD_ID)
    tree.copy_global_to(guild=guild)
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
        for result, _, _ in game_service.process_message(message):
            if result == game_service.ProcessResult.STORED:
                stored += 1
        if message.id > newest_id:
            newest_id = message.id

    if newest_id != (last_id or 0):
        db.set_last_message_id(newest_id)

    print(f"Scan complete — {stored} new result(s) stored.")
    streak_warning.start()


# ── Commands ──────────────────────────────────────────────────────────────────

@tree.command(name="ranking", description="Show the streak leaderboard for a game")
@app_commands.describe(game="Which game to show rankings for")
@app_commands.choices(game=[
    app_commands.Choice(name="Wordle",   value="wordle"),
    app_commands.Choice(name="RoWordle", value="rowordle"),
    app_commands.Choice(name="Nerdle",   value="nerdle"),
])
async def ranking(interaction: discord.Interaction, game: app_commands.Choice[str]):
    if interaction.channel_id != WORDLE_CHANNEL_ID:
        await interaction.response.send_message("Use this command in the Wordle channel.", ephemeral=True)
        return

    await interaction.response.defer()

    config = games.GAMES_BY_KEY[game.value]
    rows = game_service.get_rankings(game.value)

    if not rows:
        await interaction.followup.send(f"No {config.display_name} results found yet.")
        return

    lines = [f"**{config.display_name} Streak Leaderboard**", ""]
    for i, (username, streak, avg) in enumerate(rows, 1):
        suffix = "day" if streak == 1 else "days"
        avg_str = f" · avg {avg:.2f}/6" if avg is not None else ""
        lines.append(f"{i}. **{username}** — {streak} {suffix}{avg_str}")

    await interaction.followup.send("\n".join(lines))


@tree.command(name="mystats", description="Show your personal stats across all games")
async def mystats(interaction: discord.Interaction):
    if interaction.channel_id != WORDLE_CHANNEL_ID:
        await interaction.response.send_message("Use this command in the Wordle channel.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    stats = game_service.get_user_stats(str(interaction.user.id))

    lines = ["**Your Stats**"]
    has_any = False

    for game_key, s in stats.items():
        if s["total"] == 0:
            continue
        has_any = True
        avg_str = f"{s['avg_attempts']:.2f}/6" if s["avg_attempts"] is not None else "N/A"
        lines += [
            "",
            f"**{s['display_name']}**",
            f"Streak: **{s['streak']}** days · Best: **{s['best_streak']}** days",
            f"Avg guesses: **{avg_str}** · Win rate: **{s['win_rate']:.1%}** ({s['wins']}/{s['total']})",
        ]

    if not has_any:
        await interaction.followup.send("No results found for you yet.", ephemeral=True)
        return

    await interaction.followup.send("\n".join(lines), ephemeral=True)


# ── Scheduled tasks ───────────────────────────────────────────────────────────

@tasks.loop(minutes=1)
async def streak_warning():
    now = datetime.now(TZ)
    if now.hour != 23 or now.minute != 0:
        return

    channel = client.get_channel(WORDLE_CHANNEL_ID)
    if channel is None:
        return

    today_str = now.date().isoformat()
    sections = []

    for config in games.ALL_GAMES:
        meta_key = f"warning_sent_{config.key}"
        if db.get_meta(meta_key) == today_str:
            continue
        db.set_meta(meta_key, today_str)

        at_risk = game_service.get_at_risk_users(config.key)
        if not at_risk:
            continue

        mentions = " ".join(f"<@{uid}>" for uid, _ in at_risk)
        sections.append(f"**{config.display_name}**: {mentions}")

    if not sections:
        return

    body = "\n".join(sections)
    await channel.send(
        f"⏰ **1 hour left to complete today's puzzles!**\n{body}\n"
        f"Your streak is at risk — don't break the chain!"
    )


client.run(os.environ["DISCORD_TOKEN"])
