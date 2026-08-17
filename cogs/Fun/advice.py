import discord
from discord.ext import commands
import aiohttp
import random
from typing import Optional

FALLBACK_ADVICE = [
    "Always remember that you are absolutely unique. Just like everyone else.",
    "Never let the fear of striking out keep you from playing the game.",
    "The secret of getting ahead is getting started.",
    "Don't worry about failures, worry about the chances you miss when you don't even try.",
    "It does not matter how slowly you go as long as you do not stop.",
    "If you want to live a happy life, tie it to a goal, not to people or things.",
    "Believe you can and you're halfway there.",
    "Take care of your body. It's the only place you have to live.",
    "Do not wait to strike till the iron is hot; but make it hot by striking.",
    "Great things never come from comfort zones."
]

async def fetch_advice(bot: commands.Bot) -> str:
    session = getattr(bot, 'session', None)
    close_session = False
    if session is None or session.closed:
        session = aiohttp.ClientSession()
        close_session = True

    try:
        async with session.get("https://api.adviceslip.com/advice", timeout=5) as response:
            if response.status == 200:
                data = await response.json(content_type=None)
                slip = data.get("slip", {})
                if "advice" in slip:
                    return slip["advice"]
    except Exception:
        pass
    finally:
        if close_session and session and not session.closed:
            await session.close()
    return random.choice(FALLBACK_ADVICE)

class AdviceView(discord.ui.View):
    def __init__(self, bot: commands.Bot, timeout=180):
        super().__init__(timeout=timeout)
        self.bot = bot

    @discord.ui.button(label="New Advice", emoji="💡", style=discord.ButtonStyle.primary)
    async def advice_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        advice = await fetch_advice(self.bot)
        embed = discord.Embed(
            title="💡 Words of Wisdom",
            description=f"### *\"{advice}\"*",
            color=discord.Color.gold()
        )
        embed.set_footer(text="Requested advice")
        await interaction.edit_original_response(embed=embed, view=self)

class Advice(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="advice", description="Get a random piece of life advice.")
    async def advice(self, ctx: commands.Context):
        """Get a random piece of advice."""
        await ctx.defer()
        advice = await fetch_advice(self.bot)
        embed = discord.Embed(
            title="💡 Words of Wisdom",
            description=f"### *\"{advice}\"*",
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name}")
        view = AdviceView(self.bot)
        await ctx.send(embed=embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(Advice(bot))
