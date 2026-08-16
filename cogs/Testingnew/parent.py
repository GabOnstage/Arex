import discord
from discord.ext import commands

class ParentCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_group(name="parent", fallback="info", description="Example command group")
    async def parent_group(self, ctx: commands.Context) -> None:
        await ctx.send("Hello from the parent command group! Use `/parent sub-command` to run subcommands.")

    @parent_group.command(name="sub-command", description="Example subcommand")
    async def sub_command(self, ctx: commands.Context) -> None:
        await ctx.send("Hello from the sub command!")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ParentCog(bot))