import re
import discord
from discord import app_commands
from discord.ext import commands, tasks
import aiohttp
import json
import os

SOURCES = [
    {
        "url":      "https://www.gamerpower.com/api/giveaways?platform=steam&type=game",
        "platform": "steam",
        "color":    0x1b2838,
        "icon":     "https://raw.githubusercontent.com/Kubikzentimeter/discord-music-bot/main/assets/steam.png",
        "badge":    "Steam",
    },
    {
        "url":      "https://www.gamerpower.com/api/giveaways?platform=epic-games-store&type=game",
        "platform": "epic",
        "color":    0x313131,
        "icon":     "https://raw.githubusercontent.com/Kubikzentimeter/discord-music-bot/main/assets/epic.png",
        "badge":    "Epic Games",
    },
]

DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "freegames_data.json")
BOT_OWNER_ID      = 246291642468794369
DEFAULT_CHANNEL_ID = 1511389381171220622

_TITLE_NOISE = re.compile(
    r"\s*[\(\[]?(steam|epic games?( store)?|gog|pc)[\)\]]?\s*(giveaway|key|game)?\s*$",
    re.IGNORECASE,
)


def _clean_title(raw: str) -> str:
    """Entfernt Plattform-Suffixe wie '(Epic Games) Giveaway' aus dem Spieltitel."""
    return _TITLE_NOISE.sub("", raw).strip()


def _format_date(raw: str) -> str:
    """Wandelt '2026-06-04 23:59:00' in '04.06.2026' um."""
    try:
        parts = raw.split(" ")[0].split("-")
        return f"{parts[2]}.{parts[1]}.{parts[0]}"
    except Exception:
        return raw


def _build_embed(game: dict, source: dict) -> discord.Embed:
    title     = _clean_title(game.get("title", "Unbekannt"))
    worth     = game.get("worth", "N/A")
    end_raw   = game.get("end_date", "")
    end_str   = _format_date(end_raw) if end_raw else "Unbekannt"
    game_url  = game.get("open_giveaway_url") or game.get("gamerpower_url", "")

    # Preis-Zeile: ~~$14.99~~ **Kostenlos** bis zum DD.MM.YYYY
    if worth and worth not in ("N/A", "0.00", "$0.00"):
        price_line = f"~~{worth}~~ **Kostenlos bis zum {end_str}**"
    else:
        price_line = f"**Kostenlos bis zum {end_str}**"

    # Links in der Description
    links = f"[Im Browser öffnen ↗]({game_url})"

    embed = discord.Embed(
        title=title,
        description=f"{price_line}\n\n{links}",
        color=source["color"],
        url=game_url,
    )

    # Bild als großes Banner
    if game.get("image"):
        embed.set_image(url=game["image"])
    elif game.get("thumbnail"):
        embed.set_image(url=game["thumbnail"])

    # Plattform-Logo oben rechts
    embed.set_thumbnail(url=source["icon"])

    embed.set_footer(text=f"via GamerPower • {source['badge']}")
    return embed


class FreeGamesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = self._load_data()
        self.check_free_games.start()

    def cog_unload(self):
        self.check_free_games.cancel()

    def _load_data(self) -> dict:
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"[FreeGames] Fehler beim Laden: {e}")
        return {"channel_id": DEFAULT_CHANNEL_ID, "seen_ids": []}

    def _save_data(self):
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f)
        except Exception as e:
            print(f"[FreeGames] Fehler beim Speichern: {e}")

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
                            print(f"[FreeGames] HTTP {resp.status} für {source['badge']}")
                            continue
                        games = await resp.json(content_type=None)
                except Exception as e:
                    print(f"[FreeGames] Netzwerkfehler {source['badge']}: {e}")
                    continue

                if not isinstance(games, list):
                    continue

                for game in games:
                    if str(game.get("id")) in self.data["seen_ids"]:
                        continue
                    try:
                        embed = _build_embed(game, source)
                        await channel.send(embed=embed)
                        self.data["seen_ids"].append(str(game["id"]))
                        any_new = True
                        print(f"[FreeGames] Gepostet ({source['badge']}): {game.get('title')}")
                    except Exception as e:
                        print(f"[FreeGames] Fehler beim Posten: {e}")

        if any_new:
            self._save_data()

    @check_free_games.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="setfreegames", description="Setzt den Channel für kostenlose Steam & Epic-Spiele")
    @app_commands.describe(channel="Der Channel in dem neue kostenlose Spiele gepostet werden")
    async def setfreegames(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if interaction.user.id != BOT_OWNER_ID:
            return await interaction.response.send_message("Keine Berechtigung.", ephemeral=True)
        self.data["channel_id"] = channel.id
        self._save_data()
        await interaction.response.send_message(
            embed=discord.Embed(
                title="✅ Free-Games Channel gesetzt",
                description=f"Steam & Epic Games werden in {channel.mention} gepostet.\nPrüfung alle 30 Minuten.",
                color=discord.Color.green(),
            )
        )

    @app_commands.command(name="checkfreegames", description="Jetzt sofort auf kostenlose Steam & Epic-Spiele prüfen")
    async def checkfreegames(self, interaction: discord.Interaction):
        if interaction.user.id != BOT_OWNER_ID:
            return await interaction.response.send_message("Keine Berechtigung.", ephemeral=True)
        await interaction.response.send_message("🔍 Prüfe auf kostenlose Spiele…", ephemeral=True)
        await self.check_free_games()
        await interaction.edit_original_response(content="✅ Fertig — neue Spiele wurden gepostet (falls vorhanden).")

    @app_commands.command(name="resetfreegames", description="Alle Spiele als ungesehen markieren und erneut senden")
    async def resetfreegames(self, interaction: discord.Interaction):
        if interaction.user.id != BOT_OWNER_ID:
            return await interaction.response.send_message("Keine Berechtigung.", ephemeral=True)
        self.data["seen_ids"] = []
        self._save_data()
        await interaction.response.send_message("🔄 Liste zurückgesetzt — sende alle Spiele erneut…", ephemeral=True)
        await self.check_free_games()
        await interaction.edit_original_response(content="✅ Alle Spiele wurden erneut gepostet.")


async def setup(bot: commands.Bot):
    await bot.add_cog(FreeGamesCog(bot))
