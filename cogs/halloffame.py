import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timezone

HALL_CHANNEL_ID = 1511417114274038002
DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "halloffame_data.json")
BOT_OWNER_ID = 246291642468794369

MEDALS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]


def _fmt_time(seconds: float) -> str:
    """Wandelt Sekunden in 'Xh Ym' um."""
    seconds = int(seconds)
    h, m = divmod(seconds // 60, 60)
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m"


class HallOfFameCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = self._load_data()
        # Laufende Sessions: user_id → {"start": timestamp_float, "type": "talk"|"afk"}
        self.sessions: dict[int, dict] = {}
        self.update_leaderboard.start()

    def cog_unload(self):
        self.update_leaderboard.cancel()

    # ── Persistenz ─────────────────────────────────────────────────────────────

    def _load_data(self) -> dict:
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"[HallOfFame] Ladefehler: {e}")
        return {"message_id": None, "talk": {}, "afk": {}}

    def _save_data(self):
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f)
        except Exception as e:
            print(f"[HallOfFame] Speicherfehler: {e}")

    # ── Session-Tracking ───────────────────────────────────────────────────────

    def _session_type(self, member: discord.Member, channel: discord.VoiceChannel | None) -> str | None:
        """Gibt 'talk', 'afk' oder None zurück."""
        if channel is None:
            return None
        # AFK-Channel des Servers
        if member.guild.afk_channel and channel.id == member.guild.afk_channel.id:
            return "afk"
        # Selbst stummgeschaltet, server-stummgeschaltet oder taub
        vs = member.voice
        if vs and (vs.self_mute or vs.mute or vs.self_deaf or vs.deaf):
            return "afk"
        return "talk"

    def _end_session(self, user_id: int):
        """Beendet die laufende Session und addiert die Zeit."""
        session = self.sessions.pop(user_id, None)
        if session is None:
            return
        elapsed = datetime.now(timezone.utc).timestamp() - session["start"]
        if elapsed < 1:
            return
        key = session["type"]
        uid = str(user_id)
        self.data[key][uid] = self.data[key].get(uid, 0) + elapsed

    def _start_session(self, user_id: int, stype: str):
        self.sessions[user_id] = {
            "start": datetime.now(timezone.utc).timestamp(),
            "type": stype,
        }

    # ── Voice-State-Listener ───────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return

        uid = member.id

        # Alte Session beenden
        self._end_session(uid)

        # Neue Session starten
        stype = self._session_type(member, after.channel)
        if stype:
            self._start_session(uid, stype)

        self._save_data()

    # ── Leaderboard aufbauen ───────────────────────────────────────────────────

    def _build_embed(self) -> discord.Embed:
        now = discord.utils.utcnow()

        # Laufende Sessions in temporäre Kopie einrechnen
        talk_tmp = dict(self.data["talk"])
        afk_tmp  = dict(self.data["afk"])
        now_ts   = now.timestamp()

        for uid, session in self.sessions.items():
            elapsed = now_ts - session["start"]
            key_tmp = talk_tmp if session["type"] == "talk" else afk_tmp
            key_tmp[str(uid)] = key_tmp.get(str(uid), 0) + elapsed

        # Sortieren
        top_talk = sorted(talk_tmp.items(), key=lambda x: x[1], reverse=True)[:5]
        top_afk  = sorted(afk_tmp.items(),  key=lambda x: x[1], reverse=True)[:3]

        embed = discord.Embed(
            title="🏆  S I E G E S H A L L E",
            description=(
                "Hier werden die aktivsten Mitglieder unseres Servers geehrt!\n"
                "Die Zeiten werden live gemessen und alle 5 Minuten aktualisiert.\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            color=discord.Color.gold(),
            timestamp=now,
        )

        # Top 5 Aktive Member
        if top_talk:
            lines = []
            for i, (uid, secs) in enumerate(top_talk):
                medal = MEDALS[i] if i < len(MEDALS) else f"{i+1}."
                lines.append(f"{medal} <@{uid}>\n┗ ⏱️ **{_fmt_time(secs)}**")
            embed.add_field(
                name="🎙️ ┃ Top 5 Aktive Member",
                value="\n".join(lines),
                inline=False,
            )
        else:
            embed.add_field(
                name="🎙️ ┃ Top 5 Aktive Member",
                value="*Noch keine Daten — sprich einfach im Voice-Channel!*",
                inline=False,
            )

        embed.add_field(name="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", value="", inline=False)

        # Top 3 nicht so Aktive Member
        if top_afk:
            lines = []
            for i, (uid, secs) in enumerate(top_afk):
                medal = MEDALS[i] if i < 3 else f"{i+1}."
                lines.append(f"{medal} <@{uid}>\n┗ 💤 **{_fmt_time(secs)}**")
            embed.add_field(
                name="😴 ┃ Top 3 AFK Member",
                value="\n".join(lines),
                inline=False,
            )
        else:
            embed.add_field(
                name="😴 ┃ Top 3 AFK Member",
                value="*Noch keine Daten.*",
                inline=False,
            )

        embed.set_footer(text="🕐 Zuletzt aktualisiert")
        return embed

    # ── Leaderboard posten/updaten ─────────────────────────────────────────────

    @tasks.loop(minutes=5)
    async def update_leaderboard(self):
        channel = self.bot.get_channel(HALL_CHANNEL_ID)
        if not channel:
            return

        embed = self._build_embed()

        # Alte Nachricht löschen
        old_id = self.data.get("message_id")
        if old_id:
            try:
                old_msg = await channel.fetch_message(old_id)
                await old_msg.delete()
            except Exception:
                pass

        # Neue Nachricht senden
        try:
            msg = await channel.send(embed=embed)
            self.data["message_id"] = msg.id
            self._save_data()
        except Exception as e:
            print(f"[HallOfFame] Fehler beim Senden: {e}")

    @update_leaderboard.before_loop
    async def before_update(self):
        await self.bot.wait_until_ready()

    # ── Slash-Befehle ──────────────────────────────────────────────────────────

    @app_commands.command(name="hallofame", description="Siegeshalle sofort aktualisieren")
    @app_commands.default_permissions(administrator=True)
    async def hallofame(self, interaction: discord.Interaction):
        await interaction.response.send_message("🔄 Aktualisiere…", ephemeral=True)
        await self.update_leaderboard()
        await interaction.edit_original_response(content="✅ Siegeshalle aktualisiert!")

    @app_commands.command(name="resetstats", description="Alle Sprachstatistiken zurücksetzen")
    @app_commands.default_permissions(administrator=True)
    async def resetstats(self, interaction: discord.Interaction):
        self.data["talk"] = {}
        self.data["afk"] = {}
        self.sessions.clear()
        self._save_data()
        await interaction.response.send_message("✅ Statistiken zurückgesetzt.", ephemeral=True)
        await self.update_leaderboard()


async def setup(bot: commands.Bot):
    await bot.add_cog(HallOfFameCog(bot))
