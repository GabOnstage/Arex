import aiohttp
import discord
from discord.ext import commands
from discord import app_commands
import random

KITSU_API = "https://kitsu.io/api/edge/anime"
KITSU_HEADERS = {"Accept": "application/vnd.api+json"}

QUOTE_API = "https://yurippe.vercel.app/api/quotes?random"

FALLBACK_QUOTES = [
    {"character": "Kamina", "show": "Gurren Lagann", "quote": "Don't believe in yourself. Believe in me! Believe in the Kamina who believes in you!"},
    {"character": "Itachi Uchiha", "show": "Naruto", "quote": "Those who forgive themselves, and are able to accept their true nature... they are the strong ones."},
    {"character": "Saitama", "show": "One Punch Man", "quote": "The true power of us human beings is that we can change ourselves on our own."},
    {"character": "Monkey D. Luffy", "show": "One Piece", "quote": "If you don't take risks, you can't create a future."},
    {"character": "Eren Yeager", "show": "Attack on Titan", "quote": "If you win, you live. If you lose, you die. If you don't fight, you can't win!"},
    {"character": "Light Yagami", "show": "Death Note", "quote": "I am justice!"},
]


class Anime(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_group(name="anime", description="Anime-related commands.")
    async def anime_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("Usage: `/anime search <title>` or `/anime quote`")

    @anime_group.command(name="search", description="Search for an anime on Kitsu.")
    @app_commands.describe(title="Anime title to search for")
    async def anime_search_cmd(self, ctx: commands.Context, *, title: str):
        await self._anime_search(ctx, title=title)

    async def _anime_search(self, ctx: commands.Context, *, title: str):
        await ctx.defer()
        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            async with session.get(
                KITSU_API,
                params={"page[limit]": "5", "filter[text]": title.strip()},
                headers=KITSU_HEADERS,
                timeout=8,
            ) as resp:
                if resp.status != 200:
                    await ctx.send(f"Kitsu API returned error (Status: {resp.status}). Try again later.")
                    return
                results = (await resp.json()).get("data", [])
        except Exception as e:
            await ctx.send(f"An error occurred while searching Kitsu: {e}")
            return
        finally:
            if close_session and session and not session.closed:
                await session.close()

        if not results:
            embed_notfound = discord.Embed(
                title="Not Found",
                description=f"Could not find any anime matching `{title}`.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed_notfound, ephemeral=True)
            return

        entry = results[0]["attributes"]
        name = entry.get("canonicalTitle") or entry.get("titles", {}).get("en") or "Unknown"
        synopsis = entry.get("synopsis") or "No synopsis available."
        if len(synopsis) > 400:
            synopsis = synopsis[:400].rsplit(" ", 1)[0] + "..."

        embed = discord.Embed(
            title=name,
            url=f"https://kitsu.io/anime/{entry.get('slug', '')}",
            description=synopsis,
            color=discord.Color.orange()
        )
        embed.add_field(name="Type", value=(entry.get("subtype") or "?").capitalize(), inline=True)
        embed.add_field(name="Status", value=(entry.get("status") or "?").replace("-", " ").capitalize(), inline=True)
        episodes = entry.get("episodeCount")
        embed.add_field(name="Episodes", value=str(episodes) if episodes else "Unknown", inline=True)
        score = entry.get("averageRating")
        embed.add_field(name="Score", value=f"{score}%" if score else "Unrated", inline=True)
        age_rating = entry.get("ageRating")
        embed.add_field(name="Age Rating", value=age_rating or "N/A", inline=True)
        start = (entry.get("startDate") or "")[:4]
        if start:
            embed.add_field(name="Year", value=start, inline=True)

        poster = (entry.get("posterImage") or {}).get("large") or (entry.get("posterImage") or {}).get("medium")
        if poster:
            embed.set_thumbnail(url=poster)

        matches = len(results)
        if matches > 1:
            embed.set_footer(text=f"Powered by Kitsu | {matches - 1} other result(s) found")
        else:
            embed.set_footer(text="Powered by Kitsu")
        await ctx.send(embed=embed)

    @anime_group.command(name="quote", description="Get a random anime quote.")
    async def anime_quote_cmd(self, ctx: commands.Context):
        await ctx.defer()
        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        quote_data = None
        try:
            async with session.get(QUOTE_API, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    if isinstance(data, list) and data:
                        quote_data = random.choice(data)
        except Exception:
            pass
        finally:
            if close_session and session and not session.closed:
                await session.close()

        if not quote_data or not quote_data.get("quote"):
            quote_data = random.choice(FALLBACK_QUOTES)

        embed = discord.Embed(
            title="🎌 Anime Quote",
            description=f"### *\"{quote_data['quote']}\"*",
            color=discord.Color.magenta()
        )
        embed.set_footer(text=f"— {quote_data.get('character', 'Unknown')}, {quote_data.get('show', 'Unknown')}")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Anime(bot))
