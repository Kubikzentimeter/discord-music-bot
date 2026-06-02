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


async def setup(bot: commands.Bot):
    await bot.add_cog(LoggerCog(bot))
