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


class MusicBot(commands.Bot):
    async def setup_hook(self):
        # Block VOICE_SERVER_UPDATE processing before on_ready completes.
        # This prevents discord.py from auto-reconnecting to stale voice sessions.
        # on_ready deletes this instance override to restore normal behaviour.
        self._connection.parse_voice_server_update = lambda data: (
            print(f"[Startup] Blockiere VOICE_SERVER_UPDATE Guild {data.get('guild_id')}")
        )


bot = MusicBot(command_prefix="!", intents=intents)


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

    # Restore original voice server update handler
    try:
        del bot._connection.parse_voice_server_update
    except AttributeError:
        pass
    print("[Startup] Voice-Sperre aufgehoben.")

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
