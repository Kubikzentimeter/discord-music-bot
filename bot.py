import discord
from discord.ext import commands
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_disconnect():
    print("[Gateway] Disconnect — räume Voice-Clients auf...")
    for vc in list(bot.voice_clients):
        try:
            await vc.disconnect(force=True)
        except Exception:
            pass


@bot.event
async def on_ready():
    # Stale Voice-Sessions sofort leeren damit der 4006-Loop sich legt
    for guild in bot.guilds:
        try:
            if guild.voice_client:
                await guild.voice_client.disconnect(force=True)
            await guild.change_voice_state(channel=None)
            print(f"[Voice] Stale state für '{guild.name}' geleert")
        except Exception:
            pass

    if not hasattr(bot, "_extensions_loaded"):
        await asyncio.sleep(8)  # Warten bis 4006-Storm sich legt
        await bot.load_extension("cogs.music")
        bot._extensions_loaded = True

    try:
        guild = discord.Object(id=1122303908149219380)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"Slash Commands synchronisiert: {len(synced)}")
    except Exception as e:
        print(f"Fehler beim Synchronisieren: {e}")

    print(f"Bot online als {bot.user} (ID: {bot.user.id})")


bot.run(TOKEN)
