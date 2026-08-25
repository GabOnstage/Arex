import aiohttp
import discord
from discord.ext import commands
from discord import app_commands

KITSU_API = "https://kitsu.io/api/edge/anime"
HEADERS = {"Accept": "application/vnd.api+json"}


class Anime(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="anime", description="Search for an anime on Kitsu.")
    @app_commands.describe(title="Anime title to search for")
    async def anime(self, ctx: commands.Context, *, title: str):
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
                headers=HEADERS,
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
        embed.set_footer(text="Powered by Kitsu")

        matches = len(results)
        if matches > 1:
            embed.set_footer(text=f"Powered by Kitsu | {matches - 1} other result(s) found")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Anime(bot))
