import discord
from discord import app_commands
from discord.ext import commands, tasks
import aiohttp
import json
import os

GAMERPOWER_URL = "https://www.gamerpower.com/api/giveaways?platform=steam&type=game"
DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "freegames_data.json")

BOT_OWNER_ID = 246291642468794369


class FreeGamesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = self._load_data()
        self.check_free_games.start()

    def cog_unload(self):
        self.check_free_games.cancel()

    # ── Persistenz ────────────────────────────────────────────────────────────

    def _load_data(self) -> dict:
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"[FreeGames] Fehler beim Laden der Daten: {e}")
        return {"channel_id": None, "seen_ids": []}

    def _save_data(self):
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f)
        except Exception as e:
            print(f"[FreeGames] Fehler beim Speichern der Daten: {e}")

    # ── Hintergrundtask ────────────────────────────────────────────────────────

    @tasks.loop(minutes=30)
    async def check_free_games(self):
        channel_id = self.data.get("channel_id")
        if not channel_id:
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(GAMERPOWER_URL, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        print(f"[FreeGames] API-Fehler: HTTP {resp.status}")
                        return
                    games = await resp.json(content_type=None)
        except Exception as e:
            print(f"[FreeGames] Netzwerkfehler: {e}")
            return

        if not isinstance(games, list):
            return

        new_games = [g for g in games if str(g.get("id")) not in self.data["seen_ids"]]

        for game in new_games:
            try:
                embed = discord.Embed(
                    title=f"🎮 Kostenloses Steam-Spiel: {game.get('title', 'Unbekannt')}",
                    description=game.get("description", "")[:300] + ("…" if len(game.get("description", "")) > 300 else ""),
                    color=discord.Color.green(),
                    url=game.get("open_giveaway_url") or game.get("gamerpower_url", ""),
                )
                if game.get("image"):
                    embed.set_image(url=game["image"])
                elif game.get("thumbnail"):
                    embed.set_thumbnail(url=game["thumbnail"])

                worth = game.get("worth", "Unbekannt")
                end_date = game.get("end_date", "Unbekannt")
                platforms = game.get("platforms", "Steam")

                embed.add_field(name="💰 Wert", value=worth, inline=True)
                embed.add_field(name="⏳ Endet am", value=end_date, inline=True)
                embed.add_field(name="🖥️ Plattform", value=platforms, inline=True)
                embed.set_footer(text="Quelle: GamerPower • Kostenlos solange der Aktionszeitraum läuft")

                await channel.send(embed=embed)
                self.data["seen_ids"].append(str(game["id"]))
                print(f"[FreeGames] Neues Spiel gepostet: {game.get('title')}")
            except Exception as e:
                print(f"[FreeGames] Fehler beim Posten: {e}")

        if new_games:
            self._save_data()

    @check_free_games.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    # ── Slash-Befehle ──────────────────────────────────────────────────────────

    @app_commands.command(name="setfreegames", description="Setzt den Channel für kostenlose Steam-Spiele")
    @app_commands.describe(channel="Der Channel in dem neue kostenlose Spiele gepostet werden")
    async def setfreegames(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if interaction.user.id != BOT_OWNER_ID:
            return await interaction.response.send_message("Keine Berechtigung.", ephemeral=True)
        self.data["channel_id"] = channel.id
        self._save_data()
        embed = discord.Embed(
            title="✅ Free-Games Channel gesetzt",
            description=f"Kostenlose Steam-Spiele werden ab jetzt in {channel.mention} gepostet.\nDer Bot prüft alle 30 Minuten auf neue Aktionen.",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="checkfreegames", description="Jetzt sofort auf kostenlose Steam-Spiele prüfen")
    async def checkfreegames(self, interaction: discord.Interaction):
        if interaction.user.id != BOT_OWNER_ID:
            return await interaction.response.send_message("Keine Berechtigung.", ephemeral=True)
        await interaction.response.send_message("🔍 Prüfe auf kostenlose Spiele…", ephemeral=True)
        await self.check_free_games()
        await interaction.edit_original_response(content="✅ Fertig — neue Spiele wurden gepostet (falls vorhanden).")


async def setup(bot: commands.Bot):
    await bot.add_cog(FreeGamesCog(bot))
