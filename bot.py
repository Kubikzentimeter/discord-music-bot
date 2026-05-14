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

bot = commands.Bot(command_prefix="!", intents=intents)


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
        # Block VOICE_SERVER_UPDATE so the 4006 reconnect loop can never complete
        conn = bot._connection
        original_handler = conn.parsers.get("VOICE_SERVER_UPDATE")
        conn.parsers["VOICE_SERVER_UPDATE"] = lambda data: print("[Voice] VOICE_SERVER_UPDATE blockiert (Startup)")

        # Clear any stale voice sessions
        for guild in bot.guilds:
            try:
                if guild.voice_client:
                    await guild.voice_client.disconnect(force=True)
                await guild.change_voice_state(channel=None)
            except Exception:
                pass

        print("[Startup] Warte 35s bis 4006-Storm abklingt...")
        await asyncio.sleep(35)

        # Restore handler and load cog
        if original_handler:
            conn.parsers["VOICE_SERVER_UPDATE"] = original_handler
        print("[Startup] VOICE_SERVER_UPDATE wiederhergestellt")

        await bot.load_extension("cogs.music")
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
