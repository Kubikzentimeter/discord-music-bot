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
    "bollerwagen": {
        "name": "Radio Bollerwagen",
        "url": "http://player.ffn.de/radiobollerwagen.mp3",
        "emoji": "🍺",
    },
}

_raw_roles = os.getenv("ALLOWED_ROLE_IDS", "")
_raw_users = os.getenv("ALLOWED_USER_IDS", "")
ALLOWED_ROLE_IDS: set[int] = {int(x) for x in _raw_roles.split(",") if x.strip()}
ALLOWED_USER_IDS: set[int] = {int(x) for x in _raw_users.split(",") if x.strip()}

BOT_OWNER_ID = 246291642468794369
JAIL_CHANNEL_NAME = "🔇︱LenMc07s Büro"

YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "cookiefile": "/root/discord-bot/cookies.txt",
    "extractor_args": {"youtube": {"player_client": ["web"]}},
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


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.volume: dict[int, float] = {}
        self.jailed: dict[int, set[int]] = {}  # guild_id → set of jailed user IDs

    def get_volume(self, guild_id: int) -> float:
        return self.volume.get(guild_id, 0.5)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member == self.bot.user:
            print(f"[Voice Event] Bot: #{before.channel} → #{after.channel}")
            # Bot wurde in anderen Channel bewegt → prüfen ob erlaubt
            if (before.channel is not None and after.channel is not None
                    and before.channel.id != after.channel.id):
                await asyncio.sleep(0.3)  # kurz warten bis Audit-Log aktuell ist
                guild = member.guild
                try:
                    async for entry in guild.audit_logs(
                        limit=5,
                        action=discord.AuditLogAction.member_move,
                    ):
                        age = (discord.utils.utcnow() - entry.created_at).total_seconds()
                        if age < 5 and entry.user.id != BOT_OWNER_ID:
                            vc = guild.voice_client
                            if vc and vc.is_connected():
                                await vc.move_to(before.channel)
                                print(f"[Bot-Move] Unbefugter Move von {entry.user} rückgängig gemacht")
                        break
                except discord.Forbidden:
                    print("[Bot-Move] Kein Audit-Log-Zugriff — Berechtigung 'Audit-Log lesen' fehlt")
                except Exception as e:
                    print(f"[Bot-Move] Fehler: {e}")
            return

        # Gefängnis-Logik: eingesperrte User immer zurück ins Loch ziehen
        guild_id = member.guild.id
        if guild_id in self.jailed and member.id in self.jailed[guild_id]:
            jail_channel = discord.utils.get(member.guild.voice_channels, name=JAIL_CHANNEL_NAME)
            if jail_channel is None:
                return
            # User ist in einem anderen Channel als dem Loch → zurückbewegen
            if after.channel is not None and after.channel.id != jail_channel.id:
                try:
                    await member.move_to(jail_channel)
                    print(f"[Jail] {member} zurück ins Loch bewegt")
                except Exception as e:
                    print(f"[Jail] Fehler beim Zurückbewegen: {e}")

    async def _connect(self, interaction: discord.Interaction) -> discord.VoiceClient | None:
        target = interaction.user.voice.channel
        guild = interaction.guild
        vc = guild.voice_client

        # Stabiler VoiceClient im richtigen Channel — direkt verwenden
        if vc and vc.is_connected() and vc.channel.id == target.id:
            print(f"[Voice] Verwende bestehende Verbindung #{target.name}")
            if vc.is_playing():
                vc.stop()
            return vc

        # Stale VoiceClient killen (silent — kein Gateway-LEAVE hier)
        if vc:
            vc_conn = getattr(vc, "_connection", None)
            if vc_conn:
                async def _noop(): pass
                vc_conn.reconnect = _noop
            try:
                runner = getattr(vc_conn, "_runner", None)
                if runner and not runner.done():
                    runner.cancel()
                    try:
                        await asyncio.wait_for(asyncio.shield(runner), timeout=2.0)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass
            except Exception:
                pass
            try:
                ws = getattr(vc_conn, "ws", None)
                if ws:
                    await ws.close(1000)
            except Exception:
                pass
            self.bot._connection._voice_clients.pop(guild.id, None)

        # Nur LEAVE senden wenn Bot laut Discord noch in einem Channel ist
        me = guild.me
        if me and me.voice and me.voice.channel:
            left_event = asyncio.Event()

            async def _on_leave(member, before, after):
                if member == self.bot.user and after.channel is None:
                    left_event.set()

            self.bot.add_listener(_on_leave, "on_voice_state_update")
            try:
                await guild.change_voice_state(channel=None)
                await asyncio.wait_for(left_event.wait(), timeout=5.0)
                print("[Voice] LEAVE von Discord bestätigt")
                await asyncio.sleep(1)
            except asyncio.TimeoutError:
                print("[Voice] LEAVE-Timeout — verbinde trotzdem")
            except Exception as e:
                print(f"[Voice] LEAVE-Fehler: {e}")
            finally:
                self.bot.remove_listener(_on_leave, "on_voice_state_update")
        else:
            print("[Voice] Bot ist laut Discord nicht in Channel — kein LEAVE nötig")

        # Frisch verbinden
        try:
            vc = await target.connect(timeout=30, self_deaf=True)
            print(f"[Voice] Verbunden mit #{target.name} | connected={vc.is_connected()}")
            return vc
        except Exception as e:
            print(f"[Voice] Fehler: {e}")
            await interaction.followup.send(f"Konnte nicht verbinden: {e}")
            return None

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
        vc = await self._connect(interaction)
        if vc is None:
            return

        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(stream_url, **FFMPEG_RADIO_OPTIONS),
            volume=self.get_volume(interaction.guild.id),
        )

        def after_play(error):
            if error:
                print(f"[Voice] Playback-Fehler: {error}")
            else:
                print("[Voice] Playback beendet")

        try:
            vc.play(source, after=after_play)
            print(f"[Voice] play() aufgerufen | playing={vc.is_playing()} connected={vc.is_connected()}")
        except discord.ClientException as e:
            print(f"[Voice] ClientException bei play(): {e}")
            return await interaction.followup.send(f"Fehler beim Abspielen: {e}")

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

        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(suche, download=False))
            if "entries" in data:
                data = data["entries"][0]
            url = data["url"]
            title = data.get("title", "Unbekannt")
        except Exception as e:
            return await interaction.followup.send(f"Fehler beim Laden: {e}")

        vc = await self._connect(interaction)
        if vc is None:
            return

        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS),
            volume=self.get_volume(interaction.guild.id),
        )

        def after_play(error):
            if error:
                print(f"[Voice] Playback-Fehler: {error}")
            else:
                print("[Voice] Playback beendet")

        try:
            vc.play(source, after=after_play)
            print(f"[Voice] play() aufgerufen | playing={vc.is_playing()} connected={vc.is_connected()}")
        except discord.ClientException as e:
            return await interaction.followup.send(f"Fehler beim Abspielen: {e}")

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

    @app_commands.command(name="jail", description="Sperrt einen User ins Loch 🕳️")
    @app_commands.describe(member="Der User der eingesperrt werden soll")
    async def jail(self, interaction: discord.Interaction, member: discord.Member):
        if interaction.user.id != BOT_OWNER_ID:
            return await interaction.response.send_message("Keine Berechtigung.", ephemeral=True)

        guild_id = interaction.guild.id
        if guild_id not in self.jailed:
            self.jailed[guild_id] = set()
        self.jailed[guild_id].add(member.id)

        # Sofort ins Loch bewegen falls in einem Voice-Channel
        jail_channel = discord.utils.get(interaction.guild.voice_channels, name=JAIL_CHANNEL_NAME)
        if jail_channel is None:
            return await interaction.response.send_message(
                f"⚠️ Channel `{JAIL_CHANNEL_NAME}` nicht gefunden!", ephemeral=True
            )
        if member.voice and member.voice.channel:
            try:
                await member.move_to(jail_channel)
            except Exception as e:
                print(f"[Jail] Fehler beim ersten Move: {e}")

        embed = discord.Embed(
            title="🕳️ Ins Loch gesperrt!",
            description=f"{member.mention} wurde eingesperrt und kommt nicht mehr raus.",
            color=discord.Color.dark_gray(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="unjail", description="Befreit einen User aus dem Loch 🔓")
    @app_commands.describe(member="Der User der befreit werden soll")
    async def unjail(self, interaction: discord.Interaction, member: discord.Member):
        if interaction.user.id != BOT_OWNER_ID:
            return await interaction.response.send_message("Keine Berechtigung.", ephemeral=True)

        guild_id = interaction.guild.id
        if guild_id in self.jailed:
            self.jailed[guild_id].discard(member.id)

        embed = discord.Embed(
            title="🔓 Befreit!",
            description=f"{member.mention} wurde aus dem Loch entlassen.",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="radiolist", description="Alle verfügbaren Radiosender anzeigen")
    async def radiolist(self, interaction: discord.Interaction):
        embed = discord.Embed(title="📻 Radiosender", color=discord.Color.orange())
        embed.description = "\n".join(
            f"{v['emoji']} **{v['name']}** — `/radio {k}`" for k, v in RADIO_STATIONS.items()
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
