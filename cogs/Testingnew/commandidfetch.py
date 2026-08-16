import discord
from discord.ext import commands

class CommandIdFetch(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="cmdids", description="Fetches IDs of registered application slash commands.")
    @commands.is_owner()
    async def cmdids(self, ctx: commands.Context):
        try:
            fetched_commands = await self.bot.tree.fetch_commands()
            if not fetched_commands:
                await ctx.send("No global application commands found.")
                return

            lines = [f"</{cmd.name}:{cmd.id}>" for cmd in fetched_commands]
            full_text = "\n".join(lines)

            if len(full_text) > 1900:
                full_text = full_text[:1900] + "\n...(truncated)"
            await ctx.send(full_text)
        except Exception as e:
            await ctx.send(f"Error fetching application commands: {e}")

    @commands.command(name="cmdf", description="Returns all prefix/hybrid commands available.")
    @commands.is_owner()
    async def cmdf(self, ctx: commands.Context):
        cmd_names = [f"`{command.name}`" for command in self.bot.commands]
        response = ", ".join(cmd_names)
        if len(response) > 1900:
            response = response[:1900] + "..."
        await ctx.send(f"**Available Commands ({len(cmd_names)}):**\n{response}")

async def setup(bot: commands.Bot):
    await bot.add_cog(CommandIdFetch(bot))