import discord
from discord.ext import commands
from discord import app_commands

class Userapps(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="testuserapps", description="Demonstrates user-installable application commands.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def userapps(self, ctx: commands.Context):
        await ctx.send("User apps test successful! This command is accessible across servers and direct messages.")

async def setup(bot: commands.Bot):
    await bot.add_cog(Userapps(bot))