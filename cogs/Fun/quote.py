import discord
from discord.ext import commands
import aiohttp
from typing import Optional, Tuple

class RandomQuote(discord.ui.View):
    def __init__(self, bot: commands.Bot, *, timeout=180):
        super().__init__(timeout=timeout)
        self.bot = bot

    @discord.ui.button(label="New Quote", emoji="🎲", style=discord.ButtonStyle.primary)
    async def quotebutton(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        content, author = await fetch_quote(self.bot)
        if content:
            embed = discord.Embed(
                description=f"## *\"{content}\"*",
                color=discord.Color.teal()
            )
            embed.set_footer(text=f"— {author}")
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.followup.send("Failed to retrieve a new quote. Please try again later.", ephemeral=True)

async def fetch_quote(bot: commands.Bot) -> Tuple[Optional[str], Optional[str]]:
    session = getattr(bot, 'session', None)
    close_session = False
    if session is None or session.closed:
        session = aiohttp.ClientSession()
        close_session = True

    try:
        async with session.get("https://api.quotable.io/random", timeout=5) as response:
            if response.status == 200:
                data = await response.json()
                if isinstance(data, list) and data:
                    data = data[0]
                if isinstance(data, dict):
                    return data.get("content"), data.get("author", "Unknown")
        # Fallback to zenquotes if quotable is down
        async with session.get("https://zenquotes.io/api/random", timeout=5) as response:
            if response.status == 200:
                data = await response.json()
                if isinstance(data, list) and data:
                    return data[0].get("q"), data[0].get("a", "Unknown")
    except Exception:
        pass
    finally:
        if close_session and session and not session.closed:
            await session.close()
    return None, None

class Quote(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="quote", description="Get a random inspirational quote.")
    async def quote(self, ctx: commands.Context):
        await ctx.defer()
        content, author = await fetch_quote(self.bot)
        if content:
            embed = discord.Embed(
                description=f"## *\"{content}\"*",
                color=discord.Color.teal()
            )
            embed.set_footer(text=f"— {author}")
            view = RandomQuote(self.bot)
            await ctx.send(embed=embed, view=view)
        else:
            await ctx.send("Failed to retrieve a quote at this moment. Please try again later.")

async def setup(bot: commands.Bot):
    await bot.add_cog(Quote(bot))