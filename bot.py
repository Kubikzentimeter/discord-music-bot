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


async def _kill_stale_voice(guild):
    """Killt stale VoiceClient komplett ohne Gateway-Nachrichten zu senden."""
    vc = guild.voice_client
    if not vc:
        return
    try:
        vc_conn = getattr(vc, "_connection", None)
        runner = getattr(vc_conn, "_runner", None)
        if runner and not runner.done():
            runner.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(runner), timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            print(f"[Startup] Runner gecancelt: {guild.name}")
    except Exception as e:
        print(f"[Startup] Runner-Fehler: {e}")
    try:
        vc_conn = getattr(vc, "_connection", None)
        ws = getattr(vc_conn, "ws", None)
        if ws:
            await ws.close(1000)
    except Exception:
        pass
    try:
        bot._connection._voice_clients.pop(guild.id, None)
        print(f"[Startup] VoiceClient entfernt: {guild.name}")
    except Exception as e:
        print(f"[Startup] Registry-Fehler: {e}")


@bot.event
async def on_ready():
    if not hasattr(bot, "_extensions_loaded"):
        # Stale VoiceClients killen
        for guild in bot.guilds:
            await _kill_stale_voice(guild)

        # Discord-seitig aus allen Channels austreten
        for guild in bot.guilds:
            try:
                await guild.change_voice_state(channel=None)
            except Exception:
                pass

        await asyncio.sleep(3)
        print("[Startup] Voice-Cleanup abgeschlossen")

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
