import discord
from discord.ext import commands
import random


class CoinFlip(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="coinflip", aliases=["cf", "flip"], description="Flip a coin.")
    async def coinflip(self, ctx: commands.Context):
        result = random.choice(["Heads", "Tails"])

        embed = discord.Embed(
            title="🪙 Coin Flip",
            color=discord.Color.gold()
        )
        embed.add_field(name="Result", value=f"**{result}**", inline=False)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(CoinFlip(bot))
