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
        await ctx.defer()
        formatted_question = urllib.parse.quote(question)
        api_url = f"https://www.eightballapi.com/api?question={formatted_question}&lucky=true"

        fallback_answers = [
            "It is certain.", "It is decidedly so.", "Without a doubt.",
            "Yes definitely.", "You may rely on it.", "As I see it, yes.",
            "Most likely.", "Outlook good.", "Yes.", "Signs point to yes.",
            "Reply hazy, try again.", "Ask again later.", "Better not tell you now.",
            "Cannot predict now.", "Concentrate and ask again.",
            "Don't count on it.", "My reply is no.", "My sources say no.",
            "Outlook not so good.", "Very doubtful."
        ]

        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        response_text = None
        try:
            async with session.get(api_url, timeout=4) as response:
                if response.status == 200:
                    ball_data = await response.json()
                    response_text = ball_data.get("reading")
        except Exception:
            pass
        finally:
            if close_session and session and not session.closed:
                await session.close()

        if not response_text:
            import random
            response_text = random.choice(fallback_answers)

        embed = discord.Embed(
            title="🎱 Magic 8-Ball",
            color=discord.Color.purple()
        )
        embed.add_field(name="Question", value=question, inline=False)
        embed.add_field(name="Answer", value=f"*{response_text}*", inline=False)
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Ball(bot))
