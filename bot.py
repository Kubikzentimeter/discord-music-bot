import discord
from discord.ext import commands
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
AUTO_GUILD_ID = int(os.getenv("AUTO_GUILD_ID", 0))
AUTO_VOICE_CHANNEL_ID = int(os.getenv("AUTO_VOICE_CHANNEL_ID", 0))
AUTO_RADIO = os.getenv("AUTO_RADIO", "ballermann")

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
    if not hasattr(bot, "_extensions_loaded"):
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

    if AUTO_GUILD_ID and AUTO_VOICE_CHANNEL_ID:
        await _auto_start_radio()


async def _auto_start_radio():
    guild = bot.get_guild(AUTO_GUILD_ID)
    if not guild:
        print(f"[Auto-Radio] Server {AUTO_GUILD_ID} nicht gefunden.")
        return

    channel = guild.get_channel(AUTO_VOICE_CHANNEL_ID)
    if not channel or not isinstance(channel, discord.VoiceChannel):
        print(f"[Auto-Radio] Voice-Channel {AUTO_VOICE_CHANNEL_ID} nicht gefunden.")
        return

    # Wait for discord.py's auto-reconnect to finish (it retries ~25s after restart)
    print("[Auto-Radio] Warte auf stabile Voice-Verbindung...")
    await asyncio.sleep(30)

    vc = guild.voice_client
    if vc is not None and vc.is_connected():
        # discord.py already reconnected — use that connection
        print(f"[Auto-Radio] Nutze bestehende Verbindung in #{vc.channel.name}")
        if vc.channel.id != channel.id:
            await vc.move_to(channel)
            vc = guild.voice_client
    else:
        # No connection yet — connect fresh
        print(f"[Auto-Radio] Verbinde mit #{channel.name}...")
        vc = await channel.connect()

    music_cog = bot.cogs.get("MusicCog")
    if music_cog:
        await music_cog.start_radio(guild, vc, AUTO_RADIO)
        print(f"[Auto-Radio] Starte '{AUTO_RADIO}' in #{channel.name}")
    else:
        print("[Auto-Radio] MusicCog nicht gefunden!")


bot.run(TOKEN)
