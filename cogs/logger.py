import discord
from discord.ext import commands
from datetime import datetime, timezone

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


async def setup(bot: commands.Bot):
    await bot.add_cog(LoggerCog(bot))
