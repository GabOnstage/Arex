import discord
from discord.ext import commands

class Echo(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="echo", description="Repeats a message.")
    async def echo(self, ctx: commands.Context, *, message: str):
        # Prevent mass mention abuse
        await ctx.send(message, allowed_mentions=discord.AllowedMentions.none())

async def setup(bot: commands.Bot):
    await bot.add_cog(Echo(bot))