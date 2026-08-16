import os
import discord
import aiohttp
from discord.ext import commands

class APOD(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="apod", description="NASA Astronomy Picture of the Day.")
    async def get_apod(self, ctx: commands.Context):
        await ctx.defer()
        api_key = os.getenv('NASA_API_KEY') or 'DEMO_KEY'
        url = f'https://api.nasa.gov/planetary/apod?api_key={api_key}'

        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    title = data.get('title', 'Astronomy Picture of the Day')
                    image_url = data.get('hdurl') or data.get('url')
                    explanation = data.get('explanation', 'No explanation provided.')
                    date_str = data.get('date', '')

                    embed = discord.Embed(
                        title=f"🌌 {title}",
                        description=explanation[:4000],
                        color=discord.Color.dark_purple()
                    )
                    if image_url:
                        embed.set_image(url=image_url)
                    embed.set_footer(text=f"NASA APOD • {date_str}")
                    await ctx.send(embed=embed)
                else:
                    await ctx.send(f'Failed to fetch APOD from NASA API (Status: {response.status}).')
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")
        finally:
            if close_session and session and not session.closed:
                await session.close()

async def setup(bot: commands.Bot):
    await bot.add_cog(APOD(bot))