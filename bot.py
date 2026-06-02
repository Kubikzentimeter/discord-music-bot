import discord
from discord.ext import commands
import asyncio
import signal
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# setup_hook läuft BEVOR der Bot sich mit dem Gateway verbindet
# → VOICE_SERVER_UPDATE ist blockiert bevor das erste Event ankommt
_original_setup_hook = bot.setup_hook

async def _patched_setup_hook():
    await _original_setup_hook()
    conn = bot._connection
    original_vsup = conn.parsers.get("VOICE_SERVER_UPDATE")
    bot._original_vsup_handler = original_vsup
    conn.parsers["VOICE_SERVER_UPDATE"] = lambda data: print("[Startup] VOICE_SERVER_UPDATE blockiert (pre-connect)")
    print("[Startup] VOICE_SERVER_UPDATE vor Gateway-Verbindung blockiert")

bot.setup_hook = _patched_setup_hook


async def graceful_shutdown():
    print("[Shutdown] Verlasse alle Voice-Channels...")
    for guild in bot.guilds:
        try:
            if guild.voice_client:
                await guild.voice_client.disconnect()
            await guild.change_voice_state(channel=None)
        except Exception:
            pass
    await asyncio.sleep(1)
    await bot.close()


@bot.event
async def on_ready():
    if not hasattr(bot, "_extensions_loaded"):
        conn = bot._connection

        # Discord-seitig aus allen Channels austreten (kein VoiceClient existiert → kein 4006-Loop)
        for guild in bot.guilds:
            try:
                await guild.change_voice_state(channel=None)
                print(f"[Startup] LEAVE gesendet: {guild.name}")
            except Exception:
                pass

        await asyncio.sleep(3)

        # VOICE_SERVER_UPDATE wiederherstellen — jetzt ohne stale Session
        original_handler = getattr(bot, "_original_vsup_handler", None)
        if original_handler:
            conn.parsers["VOICE_SERVER_UPDATE"] = original_handler
        print("[Startup] VOICE_SERVER_UPDATE wiederhergestellt — kein 4006-Loop möglich")

        await bot.load_extension("cogs.music")
        await bot.load_extension("cogs.freegames")
        await bot.load_extension("cogs.logger")
        await bot.load_extension("cogs.invitetracker")
        await bot.load_extension("cogs.halloffame")
        bot._extensions_loaded = True

    try:
        guild = discord.Object(id=1122303908149219380)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"Slash Commands synchronisiert: {len(synced)}")
    except Exception as e:
        print(f"Fehler beim Synchronisieren: {e}")

    print(f"Bot bereit: {bot.user}")


async def main():
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, lambda: asyncio.ensure_future(graceful_shutdown()))
    loop.add_signal_handler(signal.SIGINT, lambda: asyncio.ensure_future(graceful_shutdown()))
    async with bot:
        await bot.start(TOKEN)


asyncio.run(main())
