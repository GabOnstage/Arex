import discord
from discord.ext import commands
import aiohttp

IMDB_BASE = 'https://imdb.iamidiotareyoutoo.com'

class Movie(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_group(name="movie", fallback="search", description="Movie & TV show search.")
    async def movie_group(self, ctx: commands.Context, *, query: str):
        await self._movie_search(ctx, query=query)

    @movie_group.command(name="search", description="Search IMDB for a title (uses unofficial API).")
    async def movie_search_cmd(self, ctx: commands.Context, *, query: str):
        await self._movie_search(ctx, query=query)

    async def _movie_search(self, ctx: commands.Context, *, query: str):
        await ctx.defer()
        q = query.strip()
        if not q:
            await ctx.send('Provide a search query.')
            return
        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True
        try:
            async with session.get(f'{IMDB_BASE}/search/{q}', timeout=8) as r:
                if r.status != 200:
                    await ctx.send('IMDB API search failed.')
                    return
                data = await r.json()
                results = data.get('results', [])
                if not results:
                    await ctx.send('No results found.')
                    return
                top = results[0]
                title = top.get('title')
                year = top.get('year')
                url = top.get('url') or top.get('link')
                embed = discord.Embed(title=f"{title} ({year})", url=url or None, color=discord.Color.dark_blue())
                embed.add_field(name='Rating', value=str(top.get('rating', 'N/A')), inline=True)
                embed.add_field(name='Type', value=top.get('type', 'N/A'), inline=True)
                desc = top.get('description') or top.get('summary')
                if desc:
                    embed.add_field(name='Summary', value=desc[:1024], inline=False)
                thumb = top.get('image') or top.get('thumbnail')
                if thumb:
                    embed.set_thumbnail(url=thumb)
                await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f'IMDB fetch error: {e}')
        finally:
            if close_session and session and not session.closed:
                await session.close()

async def setup(bot: commands.Bot):
    await bot.add_cog(Movie(bot))
