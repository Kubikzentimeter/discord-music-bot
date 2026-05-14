import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import os

RADIO_STATIONS: dict[str, dict] = {
    "ballermann": {
        "name": "Ballermann Radio",
        "url": "https://stream.bmr-radio.de/ballermann-radio.mp3",
        "emoji": "🍺",
    },
    "1live": {
        "name": "WDR 1LIVE",
        "url": "https://wdr-1live-live.icecastssl.wdr.de/wdr/1live/live/mp3/128/stream.mp3",
        "emoji": "📻",
    },
    "antenne": {
        "name": "Antenne Bayern",
        "url": "https://stream.antenne.de/antenne/stream/mp3",
        "emoji": "📻",
    },
    "energy": {
        "name": "Energy Deutschland",
        "url": "https://stream.energy.de/energy/stream/mp3",
        "emoji": "⚡",
    },
    "bob": {
        "name": "Radio BOB!",
        "url": "https://streams.radiobob.de/bob-live/mp3-192/mediaplayer",
        "emoji": "🎸",
    },
    "sunshine": {
        "name": "sunshine live",
        "url": "https://stream.sunshine-live.de/live/mp3-192",
        "emoji": "☀️",
    },
    "bigfm": {
        "name": "bigFM",
        "url": "https://streams.bigfm.de/bigfm-deutschland-128-mp3",
        "emoji": "🔊",
    },
    "bayern3": {
        "name": "Bayern 3",
        "url": "https://dispatcher.rndfnk.com/br/br3/live/mp3/low",
        "emoji": "📻",
    },
}

_raw_roles = os.getenv("ALLOWED_ROLE_IDS", "")
_raw_users = os.getenv("ALLOWED_USER_IDS", "")
ALLOWED_ROLE_IDS: set[int] = {int(x) for x in _raw_roles.split(",") if x.strip()}
ALLOWED_USER_IDS: set[int] = {int(x) for x in _raw_users.split(",") if x.strip()}

YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "extractor_args": {"youtube": {"player_client": ["ios", "web"]}},
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

FFMPEG_RADIO_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -reconnect_on_network_error 1",
    "options": "-vn",
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)


def has_permission(interaction: discord.Interaction) -> bool:
    if not ALLOWED_ROLE_IDS and not ALLOWED_USER_IDS:
        return True
    if interaction.user.id in ALLOWED_USER_IDS:
        return True
    return bool({r.id for r in interaction.user.roles} & ALLOWED_ROLE_IDS)


async def get_voice_client(interaction: discord.Interaction) -> discord.VoiceClient | None:
    """Connect to the user's voice channel with stale-session cleanup."""
    if not interaction.user.voice:
        await interaction.followup.send("Du musst in einem Voice-Channel sein!")
        return None

    target = interaction.user.voice.channel

    # Always disconnect first so Discord clears any stale voice session
    existing = interaction.guild.voice_client
    if existing:
        try:
            await existing.disconnect(force=True)
        except Exception:
            pass

    await interaction.guild.change_voice_state(channel=None)
    await asyncio.sleep(3)

    try:
        vc = await target.connect()
        print(f"[Voice] Verbunden mit #{target.name}")
        return vc
    except Exception as e:
        print(f"[Voice] Fehler: {e}")
        await interaction.followup.send(f"Konnte nicht verbinden: {e}")
        return None


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.volume: dict[int, float] = {}

    def get_volume(self, guild_id: int) -> float:
        return self.volume.get(guild_id, 0.5)

    async def start_radio(self, guild: discord.Guild, vc: discord.VoiceClient, station_key: str):
        station = RADIO_STATIONS.get(station_key.lower())
        if not station:
            print(f"[Radio] Unbekannter Sender: {station_key}")
            return
        if vc.is_playing():
            vc.stop()
        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(station["url"], **FFMPEG_RADIO_OPTIONS),
            volume=self.get_volume(guild.id),
        )
        vc.play(source)

    @app_commands.command(name="radio", description="Spielt einen Radiosender ab")
    @app_commands.describe(sender="z.B. ballermann, 1live, bayern3, antenne, energy, bob, sunshine, bigfm")
    async def radio(self, interaction: discord.Interaction, sender: str):
        if not has_permission(interaction):
            return await interaction.response.send_message("Keine Berechtigung.", ephemeral=True)
        if not interaction.user.voice:
            return await interaction.response.send_message("Du musst in einem Voice-Channel sein!", ephemeral=True)

        key = sender.lower().strip()
        station = RADIO_STATIONS.get(key)

        if station:
            stream_url = station["url"]
            display_name = f"{station['emoji']} {station['name']}"
        elif sender.startswith("http://") or sender.startswith("https://"):
            stream_url = sender
            display_name = f"📻 {sender}"
        else:
            names = "\n".join(f"• `{k}` — {v['emoji']} {v['name']}" for k, v in RADIO_STATIONS.items())
            return await interaction.response.send_message(
                f"Sender `{sender}` nicht gefunden.\n{names}", ephemeral=True
            )

        await interaction.response.defer()
        vc = await get_voice_client(interaction)
        if vc is None:
            return

        if vc.is_playing():
            vc.stop()
            await asyncio.sleep(0.3)

        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(stream_url, **FFMPEG_RADIO_OPTIONS),
            volume=self.get_volume(interaction.guild.id),
        )
        vc.play(source)

        embed = discord.Embed(
            title="📻 Radio",
            description=f"**{display_name}** läuft jetzt!",
            color=discord.Color.orange(),
        )
        embed.set_footer(text="Mit /stop kannst du das Radio beenden.")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="play", description="YouTube-Song abspielen")
    @app_commands.describe(suche="Song-Name oder YouTube-URL")
    async def play(self, interaction: discord.Interaction, suche: str):
        if not has_permission(interaction):
            return await interaction.response.send_message("Keine Berechtigung.", ephemeral=True)
        if not interaction.user.voice:
            return await interaction.response.send_message("Du musst in einem Voice-Channel sein!", ephemeral=True)

        await interaction.response.defer()
        vc = await get_voice_client(interaction)
        if vc is None:
            return

        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(suche, download=False))
            if "entries" in data:
                data = data["entries"][0]
            url = data["url"]
            title = data.get("title", "Unbekannt")
        except Exception as e:
            return await interaction.followup.send(f"Fehler beim Laden: {e}")

        if vc.is_playing():
            vc.stop()
            await asyncio.sleep(0.3)

        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS),
            volume=self.get_volume(interaction.guild.id),
        )
        vc.play(source)

        embed = discord.Embed(
            title="▶ Spiele jetzt",
            description=title,
            color=discord.Color.blurple(),
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="stop", description="Musik stoppen und Bot trennen")
    async def stop(self, interaction: discord.Interaction):
        if not has_permission(interaction):
            return await interaction.response.send_message("Keine Berechtigung.", ephemeral=True)
        vc = interaction.guild.voice_client
        if vc:
            vc.stop()
            await vc.disconnect()
            await interaction.response.send_message("Gestoppt und getrennt. 🛑")
        else:
            await interaction.response.send_message("Ich bin in keinem Voice-Channel.")

    @app_commands.command(name="volume", description="Lautstärke einstellen (0–100)")
    @app_commands.describe(wert="Lautstärke zwischen 0 und 100")
    async def volume(self, interaction: discord.Interaction, wert: int):
        if not has_permission(interaction):
            return await interaction.response.send_message("Keine Berechtigung.", ephemeral=True)
        if not 0 <= wert <= 100:
            return await interaction.response.send_message("Wert muss zwischen 0 und 100 liegen.")
        self.volume[interaction.guild.id] = wert / 100
        vc = interaction.guild.voice_client
        if vc and vc.source:
            vc.source.volume = wert / 100
        await interaction.response.send_message(f"Lautstärke: **{wert}%** 🔊")

    @app_commands.command(name="radiolist", description="Alle verfügbaren Radiosender anzeigen")
    async def radiolist(self, interaction: discord.Interaction):
        embed = discord.Embed(title="📻 Radiosender", color=discord.Color.orange())
        embed.description = "\n".join(
            f"{v['emoji']} **{v['name']}** — `/radio {k}`" for k, v in RADIO_STATIONS.items()
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
