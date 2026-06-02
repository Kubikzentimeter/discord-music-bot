import discord
from discord.ext import commands

INVITE_LOG_CHANNEL_ID = 1122303908648329218
ADMIN_ROLE_ID         = 1122303908178571290
ASSIGNABLE_ROLE_ID    = 1122303908178571289
ASSIGNABLE_ROLE_ID_2  = 1122303908161790048


class AssignRoleView(discord.ui.View):
    """Zwei Knöpfe zum Vergeben von Rängen direkt aus dem Log-Channel."""

    def __init__(self, member: discord.Member, role1: discord.Role, role2: discord.Role):
        super().__init__(timeout=86400)  # 24 Stunden
        self.member = member
        self.role1 = role1
        self.role2 = role2

    def _has_perm(self, interaction: discord.Interaction) -> bool:
        return (
            interaction.user.guild_permissions.administrator
            or any(r.id == ADMIN_ROLE_ID for r in interaction.user.roles)
        )

    async def _assign(self, interaction: discord.Interaction, button: discord.ui.Button, role: discord.Role):
        if not self._has_perm(interaction):
            return await interaction.response.send_message("Keine Berechtigung.", ephemeral=True)
        if role in self.member.roles:
            button.label = f"✅ {role.name} bereits vorhanden"
            button.disabled = True
            return await interaction.response.edit_message(view=self)
        try:
            await self.member.add_roles(role, reason=f"Vergeben von {interaction.user}")
            button.label = f"✅ {role.name} — {interaction.user.display_name}"
            button.disabled = True
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(
                f"✅ {self.member.mention} hat die Rolle **{role.name}** erhalten!", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message("❌ Keine Berechtigung diese Rolle zu vergeben.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Fehler: {e}", ephemeral=True)

    @discord.ui.button(label="✅ Rang vergeben", style=discord.ButtonStyle.green)
    async def assign_role1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._assign(interaction, button, self.role1)

    @discord.ui.button(label="✅ Rang vergeben", style=discord.ButtonStyle.blurple)
    async def assign_role2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._assign(interaction, button, self.role2)

    async def update_labels(self):
        """Setzt die Knopf-Labels auf den echten Rollennamen."""
        buttons = [c for c in self.children if isinstance(c, discord.ui.Button)]
        if len(buttons) >= 2:
            buttons[0].label = f"✅ {self.role1.name} vergeben"
            buttons[1].label = f"✅ {self.role2.name} vergeben"
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

        admin_role       = guild.get_role(ADMIN_ROLE_ID)
        assignable_role  = guild.get_role(ASSIGNABLE_ROLE_ID)
        assignable_role2 = guild.get_role(ASSIGNABLE_ROLE_ID_2)
        inviter_text     = inviter.mention if inviter else "Unbekannt (OAuth / Vanity-URL)"

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
        view   = None
        if assignable_role and assignable_role2:
            view = AssignRoleView(member, assignable_role, assignable_role2)
            await view.update_labels()

        await log_channel.send(content=ping, embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(InviteTrackerCog(bot))
