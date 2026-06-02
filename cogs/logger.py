import asyncio
import discord
from discord.ext import commands

LOG_CHANNEL_ID = 1122303909407502458


class LoggerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # Bot-Bewegungen nicht loggen
        if member.bot:
            return

        channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if channel is None:
            return

        now = discord.utils.utcnow()
        embed = None

        # ── Beitritt ──────────────────────────────────────────────────────────
        if before.channel is None and after.channel is not None:
            embed = discord.Embed(
                description=f"🟢 {member.mention} hat **{after.channel.name}** betreten",
                color=discord.Color.green(),
                timestamp=now,
            )

        # ── Verlassen ─────────────────────────────────────────────────────────
        elif before.channel is not None and after.channel is None:
            embed = discord.Embed(
                description=f"🔴 {member.mention} hat **{before.channel.name}** verlassen",
                color=discord.Color.red(),
                timestamp=now,
            )

        # ── Wechsel zwischen Channels ─────────────────────────────────────────
        elif (before.channel is not None and after.channel is not None
              and before.channel.id != after.channel.id):
            # Prüfen ob ein Moderator den User verschoben hat
            await asyncio.sleep(0.3)
            mover = None
            try:
                async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_move):
                    age = (discord.utils.utcnow() - entry.created_at).total_seconds()
                    if age < 5:
                        mover = entry.user
                    break
            except discord.Forbidden:
                pass

            if mover and not mover.bot:
                embed = discord.Embed(
                    description=f"↔️ {member.mention} wurde von {mover.mention} aus **{before.channel.name}** → **{after.channel.name}** verschoben",
                    color=discord.Color.yellow(),
                    timestamp=now,
                )
            else:
                embed = discord.Embed(
                    description=f"🔀 {member.mention} hat **{before.channel.name}** → **{after.channel.name}** gewechselt",
                    color=discord.Color.orange(),
                    timestamp=now,
                )

        # ── Stummschaltung ────────────────────────────────────────────────────
        elif before.self_mute != after.self_mute and after.channel is not None:
            if after.self_mute:
                embed = discord.Embed(
                    description=f"🔇 {member.mention} hat sich in **{after.channel.name}** stummgeschaltet",
                    color=discord.Color.light_grey(),
                    timestamp=now,
                )
            else:
                embed = discord.Embed(
                    description=f"🔊 {member.mention} hat die Stummschaltung in **{after.channel.name}** aufgehoben",
                    color=discord.Color.light_grey(),
                    timestamp=now,
                )

        # ── Taubheit ──────────────────────────────────────────────────────────
        elif before.self_deaf != after.self_deaf and after.channel is not None:
            if after.self_deaf:
                embed = discord.Embed(
                    description=f"🔕 {member.mention} hat sich in **{after.channel.name}** taubgestellt",
                    color=discord.Color.light_grey(),
                    timestamp=now,
                )
            else:
                embed = discord.Embed(
                    description=f"🔔 {member.mention} hat die Taubheit in **{after.channel.name}** aufgehoben",
                    color=discord.Color.light_grey(),
                    timestamp=now,
                )

        if embed is not None:
            embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
            embed.set_footer(text=f"Server: {member.guild.name}")
            try:
                await channel.send(embed=embed)
            except Exception as e:
                print(f"[Logger] Fehler beim Senden: {e}")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # Rollen-Änderungen erkennen
        added_roles = [r for r in after.roles if r not in before.roles]
        removed_roles = [r for r in before.roles if r not in after.roles]

        if not added_roles and not removed_roles:
            return

        log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if log_channel is None:
            return

        # Kurz warten damit das Audit-Log aktuell ist
        await asyncio.sleep(0.5)

        # Wer hat die Rolle vergeben/entzogen? → Audit-Log
        moderator = None
        try:
            async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_role_update):
                if entry.target.id == after.id:
                    age = (discord.utils.utcnow() - entry.created_at).total_seconds()
                    if age < 10:
                        moderator = entry.user
                    break
        except discord.Forbidden:
            pass

        now = discord.utils.utcnow()
        mod_text = f"von {moderator.mention}" if moderator else "automatisch"

        for role in added_roles:
            embed = discord.Embed(
                description=f"🏅 {after.mention} hat die Rolle **{role.name}** erhalten {mod_text}",
                color=role.color if role.color.value else discord.Color.blurple(),
                timestamp=now,
            )
            embed.set_author(name=after.display_name, icon_url=after.display_avatar.url)
            embed.set_footer(text=f"Server: {after.guild.name}")
            try:
                await log_channel.send(embed=embed)
            except Exception as e:
                print(f"[Logger] Fehler beim Senden: {e}")

        for role in removed_roles:
            embed = discord.Embed(
                description=f"❌ {after.mention} hat die Rolle **{role.name}** verloren {mod_text}",
                color=discord.Color.dark_red(),
                timestamp=now,
            )
            embed.set_author(name=after.display_name, icon_url=after.display_avatar.url)
            embed.set_footer(text=f"Server: {after.guild.name}")
            try:
                await log_channel.send(embed=embed)
            except Exception as e:
                print(f"[Logger] Fehler beim Senden: {e}")


    @commands.Cog.listener()
    async def on_socket_event_type(self, event_type: str, data: dict):
        """Soundboard-Sounds über raw Gateway-Event tracken."""
        if event_type != "VOICE_CHANNEL_EFFECT_SEND":
            return

        sound_id = data.get("sound_id")
        if not sound_id:
            return  # Nur Soundboard-Sounds, keine Emoji-Effekte

        guild_id = int(data.get("guild_id", 0))
        channel_id = int(data.get("channel_id", 0))
        user_id = int(data.get("user_id", 0))

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        member = guild.get_member(user_id)
        vc = guild.get_channel(channel_id)
        log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if not log_channel:
            return

        member_text = member.mention if member else f"<@{user_id}>"
        channel_text = vc.name if vc else f"Channel {channel_id}"
        emoji = data.get("emoji_name") or ""
        emoji_display = f" {emoji}" if emoji else ""

        # Sound-Name über API holen
        sound_name = None
        try:
            sounds = await guild.fetch_soundboard_sounds()
            for s in sounds:
                if str(s.id) == str(sound_id):
                    sound_name = s.name
                    break
        except Exception:
            pass

        sound_display = f"**{sound_name}**" if sound_name else f"Sound `{sound_id}`"

        now = discord.utils.utcnow()
        embed = discord.Embed(
            description=f"🎵{emoji_display} {member_text} hat {sound_display} in **{channel_text}** abgespielt",
            color=discord.Color.purple(),
            timestamp=now,
        )
        if member:
            embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        embed.set_footer(text=f"Server: {guild.name}")
        try:
            await log_channel.send(embed=embed)
        except Exception as e:
            print(f"[Logger] Soundboard-Fehler: {e}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Erkennt Kicks über das Audit-Log (kein eigenes Event in Discord)."""
        log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if log_channel is None:
            return

        await asyncio.sleep(0.5)
        now = discord.utils.utcnow()

        try:
            async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.kick):
                if entry.target.id == member.id:
                    age = (discord.utils.utcnow() - entry.created_at).total_seconds()
                    if age < 10:
                        reason = entry.reason or "Kein Grund angegeben"
                        embed = discord.Embed(
                            description=f"👢 **{member}** wurde von {entry.user.mention} gekickt\n**Grund:** {reason}",
                            color=discord.Color.dark_orange(),
                            timestamp=now,
                        )
                        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
                        embed.set_footer(text=f"User-ID: {member.id}")
                        await log_channel.send(embed=embed)
                    return
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if log_channel is None:
            return

        await asyncio.sleep(0.5)
        now = discord.utils.utcnow()

        moderator = None
        reason = "Kein Grund angegeben"
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
                if entry.target.id == user.id:
                    age = (discord.utils.utcnow() - entry.created_at).total_seconds()
                    if age < 10:
                        moderator = entry.user
                        reason = entry.reason or "Kein Grund angegeben"
                    break
        except discord.Forbidden:
            pass

        mod_text = moderator.mention if moderator else "Unbekannt"
        embed = discord.Embed(
            description=f"🔨 **{user}** wurde von {mod_text} gebannt\n**Grund:** {reason}",
            color=discord.Color.dark_red(),
            timestamp=now,
        )
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        embed.set_footer(text=f"User-ID: {user.id}")
        try:
            await log_channel.send(embed=embed)
        except Exception as e:
            print(f"[Logger] Fehler beim Senden: {e}")

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if log_channel is None:
            return

        await asyncio.sleep(0.5)
        now = discord.utils.utcnow()

        moderator = None
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.unban):
                if entry.target.id == user.id:
                    age = (discord.utils.utcnow() - entry.created_at).total_seconds()
                    if age < 10:
                        moderator = entry.user
                    break
        except discord.Forbidden:
            pass

        mod_text = moderator.mention if moderator else "Unbekannt"
        embed = discord.Embed(
            description=f"✅ **{user}** wurde von {mod_text} entbannt",
            color=discord.Color.green(),
            timestamp=now,
        )
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        embed.set_footer(text=f"User-ID: {user.id}")
        try:
            await log_channel.send(embed=embed)
        except Exception as e:
            print(f"[Logger] Fehler beim Senden: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(LoggerCog(bot))
