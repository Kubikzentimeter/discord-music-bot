import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import asyncio
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import os
import re
from collections import deque

RADIO_STATIONS: dict[str, dict] = {
    "ballermann": {
        "name": "Ballermann Radio",
        "url": "https://www.ballermann-radio.de/stream/ballermannradio/",
        "emoji": "🍺",
    },
    "1live": {
        "name": "WDR 1LIVE",
        "url": "https://wdr-1live-live.icecastssl.wdr.de/wdr/1live/live/mp3/128/stream.mp3",
        "emoji": "📻",
    },
    "antenne bayern": {
        "name": "Antenne Bayern",
        "url": "https://stream.antenne.de/antenne/stream/mp3",
        "emoji": "📻",
    },
    "energy": {
        "name": "Energy Deutschland",
        "url": "https://stream.energy.de/energy/stream/mp3",
        "emoji": "⚡",
    },
    "radio bob": {
        "name": "Radio BOB!",
        "url": "https://streams.radiobob.de/bob-live/mp3-192/mediaplayer",
        "emoji": "🎸",
    },
    "sunshine live": {
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

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

sp = None
if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
    sp = spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
        )
    )

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

SPOTIFY_TRACK_RE = re.compile(r"spotify\.com/track/([A-Za-z0-9]+)")
SPOTIFY_PLAYLIST_RE = re.compile(r"spotify\.com/playlist/([A-Za-z0-9]+)")


def has_permission(interaction: discord.Interaction) -> bool:
    if not ALLOWED_ROLE_IDS and not ALLOWED_USER_IDS:
        return True
    if interaction.user.id in ALLOWED_USER_IDS:
        return True
    user_role_ids = {r.id for r in interaction.user.roles}
    return bool(user_role_ids & ALLOWED_ROLE_IDS)


async def check_permission(interaction: discord.Interaction) -> bool:
    if not has_permission(interaction):
        await interaction.response.send_message(
            "Du hast keine Berechtigung, den Bot zu steuern.", ephemeral=True
        )
        return False
    return True


class Song:
    def __init__(self, title: str, url: str, webpage_url: str, duration: int, requester: discord.Member):
        self.title = title
        self.url = url
        self.webpage_url = webpage_url
        self.duration = duration
        self.requester = requester

    @staticmethod
    async def from_query(query: str, requester: discord.Member, loop: asyncio.AbstractEventLoop) -> "Song":
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
        if "entries" in data:
            data = data["entries"][0]
        return Song(
            title=data.get("title", "Unbekannt"),
            url=data["url"],
            webpage_url=data.get("webpage_url", query),
            duration=data.get("duration", 0),
            requester=requester,
        )

    def format_duration(self) -> str:
        mins, secs = divmod(self.duration, 60)
        return f"{mins}:{secs:02d}"

    def create_embed(self, status: str = "Spiele jetzt") -> discord.Embed:
        embed = discord.Embed(
            title=status,
            description=f"[{self.title}]({self.webpage_url})",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Dauer", value=self.format_duration())
        embed.add_field(name="Angefragt von", value=self.requester.mention)
        return embed


class GuildPlayer:
    def __init__(self):
        self.queue: deque[Song] = deque()
        self.current: Song | None = None
        self.loop_song = False
        self.loop_queue = False
        self.volume = 0.5

    def clear(self):
        self.queue.clear()
        self.current = None


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players: dict[int, GuildPlayer] = {}

    def get_player(self, guild_id: int) -> GuildPlayer:
        if guild_id not in self.players:
            self.players[guild_id] = GuildPlayer()
        return self.players[guild_id]

    async def start_radio(self, guild: discord.Guild, voice_client: discord.VoiceClient, station_key: str):
        station = RADIO_STATIONS.get(station_key.lower())
        if not station:
            print(f"[Auto-Radio] Unbekannter Sender: {station_key}")
            return
        if voice_client.is_playing():
            voice_client.stop()
        player = self.get_player(guild.id)
        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(station["url"], **FFMPEG_RADIO_OPTIONS),
            volume=player.volume,
        )
        voice_client.play(source)

    async def _resolve_spotify(self, url: str) -> list[str]:
        if sp is None:
            return [url]
        queries = []
        track_match = SPOTIFY_TRACK_RE.search(url)
        playlist_match = SPOTIFY_PLAYLIST_RE.search(url)
        if track_match:
            track = sp.track(track_match.group(1))
            artist = track["artists"][0]["name"]
            name = track["name"]
            queries.append(f"{artist} {name}")
        elif playlist_match:
            results = sp.playlist_tracks(playlist_match.group(1))
            for item in results["items"][:25]:
                t = item.get("track")
                if t:
                    artist = t["artists"][0]["name"]
                    queries.append(f"{artist} {t['name']}")
        return queries or [url]

    def _play_next(self, guild: discord.Guild, voice_client: discord.VoiceClient, channel: discord.TextChannel):
        player = self.get_player(guild.id)

        if player.loop_song and player.current:
            song = player.current
        elif player.queue:
            song = player.queue.popleft()
            if player.loop_queue:
                player.queue.append(song)
            player.current = song
        else:
            player.current = None
            asyncio.run_coroutine_threadsafe(channel.send("Queue ist leer. Bis zum nächsten Mal! 👋"), self.bot.loop)
            return

        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(song.url, **FFMPEG_OPTIONS),
            volume=player.volume,
        )

        def after(error):
            if error:
                print(f"Playback Fehler: {error}")
            self._play_next(guild, voice_client, channel)

        voice_client.play(source, after=after)
        asyncio.run_coroutine_threadsafe(channel.send(embed=song.create_embed()), self.bot.loop)

    # ─── Slash Commands ───────────────────────────────────────────────────────

    @app_commands.command(name="play", description="Spiele einen Song von YouTube oder Spotify ab")
    @app_commands.describe(suche="Song-Name, YouTube-URL oder Spotify-Link")
    async def play(self, interaction: discord.Interaction, suche: str):
        if not await check_permission(interaction):
            return
        await interaction.response.defer()

        if not interaction.user.voice:
            return await interaction.followup.send("Du musst in einem Voice-Channel sein!")

        voice_channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client

        if voice_client is None:
            voice_client = await voice_channel.connect()
        elif voice_client.channel != voice_channel:
            await voice_client.move_to(voice_channel)

        player = self.get_player(interaction.guild.id)

        queries = [suche]
        if "spotify.com" in suche:
            queries = await self._resolve_spotify(suche)
            if len(queries) > 1:
                await interaction.followup.send(f"Spotify-Playlist erkannt — lade **{len(queries)}** Songs...")

        songs_added = []
        for q in queries:
            try:
                song = await Song.from_query(q, interaction.user, self.bot.loop)
                player.queue.append(song)
                songs_added.append(song)
            except Exception as e:
                await interaction.followup.send(f"Fehler beim Laden von `{q}`: {e}")

        if not songs_added:
            return

        if not voice_client.is_playing():
            self._play_next(interaction.guild, voice_client, interaction.channel)
            if len(songs_added) == 1:
                await interaction.followup.send(embed=songs_added[0].create_embed("Wird geladen..."))
            else:
                await interaction.followup.send(f"Starte Wiedergabe von **{len(songs_added)}** Songs.")
        else:
            if len(songs_added) == 1:
                await interaction.followup.send(f"Zur Queue hinzugefügt: **{songs_added[0].title}**")
            else:
                await interaction.followup.send(f"**{len(songs_added)}** Songs zur Queue hinzugefügt.")

    @app_commands.command(name="join", description="Bot joint dem Voice-Channel ohne Musik")
    async def join(self, interaction: discord.Interaction):
        if not interaction.user.voice:
            return await interaction.response.send_message("Du musst in einem Voice-Channel sein!")
        await interaction.response.defer()
        try:
            vc = await interaction.user.voice.channel.connect()
            await asyncio.sleep(3)
            still_connected = interaction.guild.voice_client is not None and interaction.guild.voice_client.is_connected()
            await interaction.followup.send(f"Verbunden! Noch verbunden nach 3s: {still_connected}")
        except Exception as e:
            await interaction.followup.send(f"Fehler: {e}")

    @app_commands.command(name="radio", description="Spielt einen Radiosender ab")
    @app_commands.describe(sender="Sendername oder eigene Stream-URL (z.B. ballermann, 1live, ...)")
    async def radio(self, interaction: discord.Interaction, sender: str):
        if not await check_permission(interaction):
            return

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
                f"Sender `{sender}` nicht gefunden. Verfügbare Sender:\n{names}",
                ephemeral=True,
            )

        await interaction.response.defer()

        voice_channel = interaction.user.voice.channel
        voice_client = interaction.guild.voice_client

        try:
            if voice_client is None:
                voice_client = await voice_channel.connect()
            elif voice_client.channel != voice_channel:
                await voice_client.move_to(voice_channel)
        except Exception as e:
            return await interaction.followup.send(f"Konnte nicht verbinden: {e}")

        # Immer den aktuellen Voice-Client vom Guild holen
        vc = interaction.guild.voice_client
        if vc is None:
            return await interaction.followup.send("Verbindungsfehler — bitte nochmal versuchen.")

        if vc.is_playing():
            vc.stop()
            await asyncio.sleep(0.5)

        self.get_player(interaction.guild.id).current = None

        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(stream_url, **FFMPEG_RADIO_OPTIONS),
            volume=self.get_player(interaction.guild.id).volume,
        )
        vc.play(source)

        embed = discord.Embed(
            title="📻 Radio",
            description=f"**{display_name}** läuft jetzt!",
            color=discord.Color.orange(),
        )
        embed.set_footer(text="Mit /stop kannst du das Radio beenden.")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="radiolist", description="Zeigt alle verfügbaren Radiosender")
    async def radiolist(self, interaction: discord.Interaction):
        if not await check_permission(interaction):
            return
        embed = discord.Embed(title="📻 Verfügbare Radiosender", color=discord.Color.orange())
        lines = [f"{v['emoji']} **{v['name']}** — `/radio {k}`" for k, v in RADIO_STATIONS.items()]
        embed.description = "\n".join(lines)
        embed.set_footer(text="Du kannst auch direkt eine Stream-URL angeben: /radio https://...")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="skip", description="Überspringt den aktuellen Song")
    async def skip(self, interaction: discord.Interaction):
        if not await check_permission(interaction):
            return
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
            await interaction.response.send_message("Song übersprungen ⏭️")
        else:
            await interaction.response.send_message("Es wird gerade nichts abgespielt.")

    @app_commands.command(name="stop", description="Stoppt die Musik und leert die Queue")
    async def stop(self, interaction: discord.Interaction):
        if not await check_permission(interaction):
            return
        vc = interaction.guild.voice_client
        player = self.get_player(interaction.guild.id)
        player.clear()
        if vc:
            vc.stop()
            await vc.disconnect()
        await interaction.response.send_message("Musik gestoppt und Queue geleert. 🛑")

    @app_commands.command(name="queue", description="Zeigt die aktuelle Queue")
    async def queue(self, interaction: discord.Interaction):
        if not await check_permission(interaction):
            return
        player = self.get_player(interaction.guild.id)
        if not player.queue and not player.current:
            return await interaction.response.send_message("Die Queue ist leer.")

        embed = discord.Embed(title="Musik-Queue", color=discord.Color.blurple())

        if player.current:
            embed.add_field(
                name="▶ Spielt gerade",
                value=f"[{player.current.title}]({player.current.webpage_url}) [{player.current.format_duration()}]",
                inline=False,
            )

        if player.queue:
            lines = []
            for i, song in enumerate(list(player.queue)[:10], 1):
                lines.append(f"`{i}.` [{song.title}]({song.webpage_url}) [{song.format_duration()}]")
            if len(player.queue) > 10:
                lines.append(f"...und {len(player.queue) - 10} weitere Songs")
            embed.add_field(name="Als nächstes", value="\n".join(lines), inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="pause", description="Pausiert die Wiedergabe")
    async def pause(self, interaction: discord.Interaction):
        if not await check_permission(interaction):
            return
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message("Pausiert ⏸️")
        else:
            await interaction.response.send_message("Es wird gerade nichts abgespielt.")

    @app_commands.command(name="resume", description="Setzt die Wiedergabe fort")
    async def resume(self, interaction: discord.Interaction):
        if not await check_permission(interaction):
            return
        vc = interaction.guild.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message("Fortgesetzt ▶️")
        else:
            await interaction.response.send_message("Nichts pausiert.")

    @app_commands.command(name="volume", description="Lautstärke einstellen (0-100)")
    @app_commands.describe(wert="Lautstärke zwischen 0 und 100")
    async def volume(self, interaction: discord.Interaction, wert: int):
        if not await check_permission(interaction):
            return
        if not 0 <= wert <= 100:
            return await interaction.response.send_message("Wert muss zwischen 0 und 100 liegen.")
        player = self.get_player(interaction.guild.id)
        player.volume = wert / 100
        vc = interaction.guild.voice_client
        if vc and vc.source:
            vc.source.volume = player.volume
        await interaction.response.send_message(f"Lautstärke auf **{wert}%** gesetzt 🔊")

    @app_commands.command(name="loop", description="Wiederholt den aktuellen Song")
    async def loop(self, interaction: discord.Interaction):
        if not await check_permission(interaction):
            return
        player = self.get_player(interaction.guild.id)
        player.loop_song = not player.loop_song
        status = "aktiviert 🔂" if player.loop_song else "deaktiviert"
        await interaction.response.send_message(f"Song-Loop {status}")

    @app_commands.command(name="loopqueue", description="Wiederholt die gesamte Queue")
    async def loopqueue(self, interaction: discord.Interaction):
        if not await check_permission(interaction):
            return
        player = self.get_player(interaction.guild.id)
        player.loop_queue = not player.loop_queue
        status = "aktiviert 🔁" if player.loop_queue else "deaktiviert"
        await interaction.response.send_message(f"Queue-Loop {status}")

    @app_commands.command(name="nowplaying", description="Zeigt den aktuell laufenden Song")
    async def nowplaying(self, interaction: discord.Interaction):
        if not await check_permission(interaction):
            return
        player = self.get_player(interaction.guild.id)
        if player.current:
            await interaction.response.send_message(embed=player.current.create_embed("Spielt gerade"))
        else:
            await interaction.response.send_message("Es wird gerade nichts abgespielt.")

    @app_commands.command(name="shuffle", description="Mischt die Queue zufällig")
    async def shuffle(self, interaction: discord.Interaction):
        if not await check_permission(interaction):
            return
        import random
        player = self.get_player(interaction.guild.id)
        if not player.queue:
            return await interaction.response.send_message("Die Queue ist leer.")
        queue_list = list(player.queue)
        random.shuffle(queue_list)
        player.queue = deque(queue_list)
        await interaction.response.send_message("Queue gemischt 🔀")

    @app_commands.command(name="remove", description="Entfernt einen Song aus der Queue")
    @app_commands.describe(position="Position in der Queue (1 = erster Song)")
    async def remove(self, interaction: discord.Interaction, position: int):
        if not await check_permission(interaction):
            return
        player = self.get_player(interaction.guild.id)
        if not player.queue or position < 1 or position > len(player.queue):
            return await interaction.response.send_message("Ungültige Position.")
        queue_list = list(player.queue)
        removed = queue_list.pop(position - 1)
        player.queue = deque(queue_list)
        await interaction.response.send_message(f"Entfernt: **{removed.title}**")

    @app_commands.command(name="disconnect", description="Trennt den Bot vom Voice-Channel")
    async def disconnect(self, interaction: discord.Interaction):
        if not await check_permission(interaction):
            return
        vc = interaction.guild.voice_client
        if vc:
            self.get_player(interaction.guild.id).clear()
            await vc.disconnect()
            await interaction.response.send_message("Disconnected 👋")
        else:
            await interaction.response.send_message("Ich bin in keinem Voice-Channel.")


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
