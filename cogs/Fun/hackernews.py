import discord
from discord.ext import commands
import aiohttp

class HackerNews(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="hn", description="Show top Hacker News stories (titles + links).")
    async def hn(self, ctx: commands.Context, count: int = 5):
        await ctx.defer()
        count = max(1, min(10, count))
        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True
        try:
            async with session.get('https://hacker-news.firebaseio.com/v0/topstories.json', timeout=6) as resp:
                if resp.status != 200:
                    await ctx.send('Failed to fetch Hacker News stories.')
                    return
                ids = await resp.json()
            items = []
            for sid in ids[:count]:
                async with session.get(f'https://hacker-news.firebaseio.com/v0/item/{sid}.json', timeout=6) as r:
                    if r.status == 200:
                        it = await r.json()
                        if it:
                            items.append(it)
            embed = discord.Embed(title='Top Hacker News', color=discord.Color.dark_gold())
            for i, it in enumerate(items, start=1):
                title = it.get('title','(no title)')
                url = it.get('url') or f"https://news.ycombinator.com/item?id={it.get('id')}"
                embed.add_field(name=f"{i}. {title}", value=url, inline=False)
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f'Error fetching HN: {e}')
        finally:
            if close_session and session and not session.closed:
                await session.close()

async def setup(bot: commands.Bot):
    await bot.add_cog(HackerNews(bot))
