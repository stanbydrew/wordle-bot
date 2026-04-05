import asyncio
import os

from dotenv import load_dotenv
import discord

load_dotenv()

client = discord.Client(intents=discord.Intents.default())
tree = discord.app_commands.CommandTree(client)


async def clear():
    await client.login(os.environ["DISCORD_TOKEN"])
    await tree.sync()
    print("Global commands cleared")
    await client.close()


asyncio.run(clear())
