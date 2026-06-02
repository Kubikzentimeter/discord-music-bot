import discord
from discord.ext import commands

INVITE_LOG_CHANNEL_ID = 1122303908648329218
ADMIN_ROLE_ID         = 1122303908178571290
ASSIGNABLE_ROLE_ID    = 1122303908178571289


class AssignRoleView(discord.ui.View):
    """Knopf zum Vergeben des Mitglieds-Rangs direkt aus dem Log-Channel."""

    def __init__(self, member: discord.Member, role: discord.Role):
        super().__init__(timeout=86400)  # 24 Stunden
        self.member = member
        self.role = role

    @discord.ui.button(label="✅ Rang vergeben", style=discord.ButtonStyle.green)
    async def assign_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Nur Admins / User mit der Admin-Rolle dürfen den Knopf drücken
        has_perm = (
            interaction.user.guild_permissions.administrator
            or any(r.id == ADMIN_ROLE_ID for r in interaction.user.roles)
        )
        if not has_perm:
            return await interaction.response.send_message("Keine Berechtigung.", ephemeral=True)

        if self.role in self.member.roles:
            button.label = "✅ Rang bereits vorhanden"
            button.disabled = True
            await interaction.response.edit_message(view=self)
            return

        try:
            await self.member.add_roles(self.role, reason=f"Vergeben von {interaction.user}")
            button.label = f"✅ Vergeben von {interaction.user.display_name}"
            button.disabled = True
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(
                f"✅ {self.member.mention} hat die Rolle **{self.role.name}** erhalten!",
                ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Ich habe keine Berechtigung diese Rolle zu vergeben.", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"Fehler: {e}", ephemeral=True)


class InviteTrackerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.invite_cache: dict[int, dict[str, int]] = {}  # guild_id → {code: uses}

    # ── Cache aufbauen ─────────────────────────────────────────────────────────

    async def _refresh_cache(self, guild: discord.Guild):
        try:
            invites = await guild.invites()
            self.invite_cache[guild.id] = {inv.code: inv.uses for inv in invites}
        except discord.Forbidden:
            print(f"[InviteTracker] Kein Zugriff auf Invites in {guild.name}")

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            await self._refresh_cache(guild)
        print("[InviteTracker] Invite-Cache geladen")

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        await self._refresh_cache(invite.guild)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        await self._refresh_cache(invite.guild)

    # ── Mitglied beigetreten ───────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        log_channel = self.bot.get_channel(INVITE_LOG_CHANNEL_ID)
        if not log_channel:
            return

        guild = member.guild
        inviter = None
        used_invite = None

        # Welcher Invite wurde genutzt? → Vergleich mit Cache
        try:
            current_invites = await guild.invites()
            cached = self.invite_cache.get(guild.id, {})
            for inv in current_invites:
                if inv.uses > cached.get(inv.code, 0):
                    used_invite = inv
                    inviter = inv.inviter
                    break
            self.invite_cache[guild.id] = {inv.code: inv.uses for inv in current_invites}
        except discord.Forbidden:
            pass

        admin_role      = guild.get_role(ADMIN_ROLE_ID)
        assignable_role = guild.get_role(ASSIGNABLE_ROLE_ID)
        inviter_text    = inviter.mention if inviter else "Unbekannt (OAuth / Vanity-URL)"

        embed = discord.Embed(
            title="👋 Neues Mitglied beigetreten!",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="👤 User",          value=member.mention,  inline=True)
        embed.add_field(name="📨 Eingeladen von", value=inviter_text,   inline=True)
        if used_invite:
            embed.add_field(
                name="🔗 Invite",
                value=f"`{used_invite.code}` — {used_invite.uses}× genutzt",
                inline=False,
            )
        embed.set_footer(text=f"User-ID: {member.id}")

        ping   = admin_role.mention if admin_role else "@admin"
        view   = AssignRoleView(member, assignable_role) if assignable_role else None

        await log_channel.send(content=ping, embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(InviteTrackerCog(bot))
