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
        conn = self._connection
        # discord.py stores event parsers in conn.parsers (dict built in ConnectionState.__init__)
        p = getattr(conn, 'parsers', None) or getattr(conn, '_parsers', {})
        self._parsers_dict = p
        self._orig_voice_server_update = p.get('VOICE_SERVER_UPDATE')
        p['VOICE_SERVER_UPDATE'] = lambda data: print(
            f"[Startup] Blockiere VOICE_SERVER_UPDATE Guild {data.get('guild_id')}"
        )
        print("[Startup] VOICE_SERVER_UPDATE blockiert.")


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

    # Restore original VOICE_SERVER_UPDATE handler
    if hasattr(bot, '_parsers_dict') and hasattr(bot, '_orig_voice_server_update'):
        if bot._orig_voice_server_update:
            bot._parsers_dict['VOICE_SERVER_UPDATE'] = bot._orig_voice_server_update
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
