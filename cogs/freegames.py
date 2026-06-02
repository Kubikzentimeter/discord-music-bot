import discord
from discord import app_commands
from discord.ext import commands, tasks
import aiohttp
import json
import os

SOURCES = [
    {"url": "https://www.gamerpower.com/api/giveaways?platform=steam&type=game",            "label": "🎮 Kostenloses Steam-Spiel",       "color": 0x1b2838},
    {"url": "https://www.gamerpower.com/api/giveaways?platform=epic-games-store&type=game", "label": "🎁 Kostenloses Epic Games-Spiel",   "color": 0x2d2d2d},
]
DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "freegames_data.json")

BOT_OWNER_ID = 246291642468794369
DEFAULT_CHANNEL_ID = 1511389381171220622


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
        return {"channel_id": DEFAULT_CHANNEL_ID, "seen_ids": []}

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

        any_new = False
        async with aiohttp.ClientSession() as session:
            for source in SOURCES:
                try:
                    async with session.get(source["url"], timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status != 200:
                            print(f"[FreeGames] API-Fehler {source['label']}: HTTP {resp.status}")
                            continue
                        games = await resp.json(content_type=None)
                except Exception as e:
                    print(f"[FreeGames] Netzwerkfehler {source['label']}: {e}")
                    continue

                if not isinstance(games, list):
                    continue

                new_games = [g for g in games if str(g.get("id")) not in self.data["seen_ids"]]
                for game in new_games:
                    try:
                        embed = discord.Embed(
                            title=f"{source['label']}: {game.get('title', 'Unbekannt')}",
                            description="Für kurze Zeit kostenlos erhältlich! Jetzt schnell zugreifen. 👇",
                            color=source["color"],
                            url=game.get("open_giveaway_url") or game.get("gamerpower_url", ""),
                        )
                        if game.get("image"):
                            embed.set_image(url=game["image"])
                        elif game.get("thumbnail"):
                            embed.set_thumbnail(url=game["thumbnail"])
                        embed.add_field(name="💰 Wert",       value=game.get("worth", "Unbekannt"),    inline=True)
                        embed.add_field(name="⏳ Endet am",   value=game.get("end_date", "Unbekannt"), inline=True)
                        embed.add_field(name="🖥️ Plattform", value=game.get("platforms", "—"),        inline=True)
                        embed.set_footer(text="Quelle: GamerPower • Kostenlos solange der Aktionszeitraum läuft")
                        await channel.send(embed=embed)
                        self.data["seen_ids"].append(str(game["id"]))
                        any_new = True
                        print(f"[FreeGames] Gepostet: {game.get('title')}")
                    except Exception as e:
                        print(f"[FreeGames] Fehler beim Posten: {e}")

        if any_new:
            self._save_data()

    @check_free_games.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    # ── Slash-Befehle ──────────────────────────────────────────────────────────

    @app_commands.command(name="setfreegames", description="Setzt den Channel für kostenlose Steam & Epic-Spiele")
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

    @app_commands.command(name="checkfreegames", description="Jetzt sofort auf kostenlose Steam & Epic-Spiele prüfen")
    async def checkfreegames(self, interaction: discord.Interaction):
        if interaction.user.id != BOT_OWNER_ID:
            return await interaction.response.send_message("Keine Berechtigung.", ephemeral=True)
        await interaction.response.send_message("🔍 Prüfe auf kostenlose Spiele…", ephemeral=True)
        await self.check_free_games()
        await interaction.edit_original_response(content="✅ Fertig — neue Spiele wurden gepostet (falls vorhanden).")


async def setup(bot: commands.Bot):
    await bot.add_cog(FreeGamesCog(bot))
