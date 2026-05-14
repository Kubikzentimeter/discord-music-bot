import discord
from discord.ext import commands
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

# Startup phase: block automatic voice reconnects until bot is fully ready
_startup_complete = False


@bot.event
async def on_voice_state_update(member, before, after):
    """Block discord.py from auto-reconnecting to voice during startup."""
    if _startup_complete:
        return
    if member.id != bot.user.id:
        return
    if after.channel is not None:
        print(f"[Startup] Blockiere Auto-Reconnect in {after.channel.name}")
        await member.guild.change_voice_state(channel=None)
        if member.guild.voice_client:
            try:
                await member.guild.voice_client.disconnect(force=True)
            except Exception:
                pass


@bot.event
async def on_ready():
    global _startup_complete

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

    # Final cleanup of any stray voice clients
    for vc in list(bot.voice_clients):
        try:
            await vc.disconnect(force=True)
        except Exception:
            pass
    bot._connection._voice_clients.clear()

    _startup_complete = True
    print("[Startup] Startup abgeschlossen, Voice-Sperre aufgehoben.")

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

    if guild.voice_client:
        await guild.voice_client.disconnect()

    voice_client = await channel.connect()

    music_cog = bot.cogs.get("MusicCog")
    if music_cog:
        await music_cog.start_radio(guild, voice_client, AUTO_RADIO)
        print(f"[Auto-Radio] Starte '{AUTO_RADIO}' in #{channel.name}")


bot.run(TOKEN)
