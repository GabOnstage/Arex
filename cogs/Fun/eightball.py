import discord
from discord.ext import commands
import aiohttp
import urllib.parse

class Ball(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="ball", aliases=["8ball", "magic8ball"], description="Ask a question to the Magic 8-Ball.")
    async def ball(self, ctx: commands.Context, *, question: str):
        """Ask a question to the Magic 8-Ball."""
        formatted_question = urllib.parse.quote(question)
        api_url = f"https://www.eightballapi.com/api?question={formatted_question}&lucky=true"

        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            async with session.get(api_url, timeout=5) as response:
                if response.status == 200:
                    ball_data = await response.json()
                    response_text = ball_data.get("reading", "The 8-ball is cloudy... Try again later.")

                    embed = discord.Embed(
                        title="🎱 Magic 8-Ball",
                        color=discord.Color.purple()
                    )
                    embed.add_field(name="Question", value=question, inline=False)
                    embed.add_field(name="Answer", value=f"*{response_text}*", inline=False)
                    await ctx.send(embed=embed)
                else:
                    error_embed = discord.Embed(
                        title="Error",
                        description="Oops! Something went wrong while consulting the 8-ball.",
                        color=discord.Color.red()
                    )
                    await ctx.send(embed=error_embed)
        except Exception as e:
            await ctx.send(f"Could not consult the 8-ball: {e}")
        finally:
            if close_session and session and not session.closed:
                await session.close()

async def setup(bot: commands.Bot):
    await bot.add_cog(Ball(bot))
