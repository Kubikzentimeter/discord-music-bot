import discord
from discord.ext import commands

INVITE_LOG_CHANNEL_ID = 1122303908648329218
ADMIN_ROLE_ID         = 1122303908178571290
ASSIGNABLE_ROLE_ID    = 1122303908178571289
ASSIGNABLE_ROLE_ID_2  = 1122303908161790048
MOD_ROLE_ID           = 1122303908178571289


class AssignRoleView(discord.ui.View):
    def __init__(self, member: discord.Member, role1: discord.Role, role2: discord.Role):
        super().__init__(timeout=86400)
        self.member = member
        self.role1 = role1
        self.role2 = role2
        # Knopf-Labels auf echten Rollennamen setzen
        buttons = [c for c in self.children if isinstance(c, discord.ui.Button)]
        if len(buttons) >= 2:
            buttons[0].label = f"✅ {role1.name} vergeben"
            buttons[1].label = f"✅ {role2.name} vergeben"

    def _has_perm(self, interaction: discord.Interaction) -> bool:
        user_role_ids = {r.id for r in interaction.user.roles}
        return (
            interaction.user.guild_permissions.administrator
            or ADMIN_ROLE_ID in user_role_ids
            or MOD_ROLE_ID in user_role_ids
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


class InviteTrackerCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.invite_cache: dict[int, dict[str, int]] = {}

    async def cog_load(self):
        """Wird direkt beim Laden des Cogs aufgerufen — baut den Invite-Cache auf."""
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            await self._refresh_cache(guild)
        print(f"[InviteTracker] Cache geladen für {len(self.bot.guilds)} Server")

    async def _refresh_cache(self, guild: discord.Guild):
        try:
            invites = await guild.invites()
            self.invite_cache[guild.id] = {inv.code: inv.uses for inv in invites}
            print(f"[InviteTracker] {len(invites)} Invites gecacht für {guild.name}")
        except discord.Forbidden:
            print(f"[InviteTracker] ⚠️ Kein Zugriff auf Invites in {guild.name} — Berechtigung 'Einladungen verwalten' fehlt!")

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        await self._refresh_cache(invite.guild)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        await self._refresh_cache(invite.guild)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        print(f"[InviteTracker] {member} ist beigetreten")
        log_channel = self.bot.get_channel(INVITE_LOG_CHANNEL_ID)
        if not log_channel:
            print(f"[InviteTracker] ⚠️ Log-Channel {INVITE_LOG_CHANNEL_ID} nicht gefunden!")
            return

        guild = member.guild
        inviter = None
        used_invite = None

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
            print("[InviteTracker] ⚠️ Keine Berechtigung Invites abzurufen")

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
        embed.add_field(name="👤 User",           value=member.mention, inline=True)
        embed.add_field(name="📨 Eingeladen von", value=inviter_text,   inline=True)
        if used_invite:
            embed.add_field(
                name="🔗 Invite",
                value=f"`{used_invite.code}` — {used_invite.uses}× genutzt",
                inline=False,
            )
        embed.set_footer(text=f"User-ID: {member.id}")

        ping = admin_role.mention if admin_role else "@admin"
        view = None
        if assignable_role and assignable_role2:
            view = AssignRoleView(member, assignable_role, assignable_role2)

        try:
            await log_channel.send(content=ping, embed=embed, view=view)
            print(f"[InviteTracker] Nachricht gesendet für {member}")
        except Exception as e:
            print(f"[InviteTracker] ⚠️ Fehler beim Senden: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(InviteTrackerCog(bot))
