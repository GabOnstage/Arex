import discord
from discord.ext import commands
import aiohttp
import random

class Quotes(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="quote", description="Get a random inspirational quote.")
    async def quote(self, ctx: commands.Context):
        await ctx.defer()
        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True
        try:
            async with session.get('https://api.quotable.io/random', timeout=6) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    content = data.get('content')
                    author = data.get('author','Unknown')
                    embed = discord.Embed(description=f"## *\"{content}\"*", color=discord.Color.teal())
                    embed.set_footer(text=f"— {author}")
                    await ctx.send(embed=embed)
                    return
            # fallback
            async with session.get('https://api.adviceslip.com/advice', timeout=6) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    slip = data.get('slip', {})
                    if 'advice' in slip:
                        await ctx.send(slip['advice'])
                        return
        except Exception:
            pass
        finally:
            if close_session and session and not session.closed:
                await session.close()
        await ctx.send('Failed to fetch a quote at this time.')

async def setup(bot: commands.Bot):
    await bot.add_cog(Quotes(bot))
