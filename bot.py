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

    # Tell Discord we are leaving any voice channel first to clear stale session
    print("[Auto-Radio] Lösche alte Voice-Session bei Discord...")
    await guild.change_voice_state(channel=None)
    await asyncio.sleep(2)

    if guild.voice_client:
        await guild.voice_client.disconnect(force=True)

    print(f"[Auto-Radio] Verbinde mit #{channel.name}...")
    voice_client = await channel.connect()

    music_cog = bot.cogs.get("MusicCog")
    if music_cog:
        await music_cog.start_radio(guild, voice_client, AUTO_RADIO)
        print(f"[Auto-Radio] Starte '{AUTO_RADIO}' in #{channel.name}")
    else:
        print("[Auto-Radio] MusicCog nicht gefunden!")


bot.run(TOKEN)
