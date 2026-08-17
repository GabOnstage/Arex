import os
import discord
from discord.ext import commands

def is_authorized_admin(user_id: int) -> bool:
    raw_owners = os.getenv('OWNERS', '')
    raw_allowed = os.getenv('ALLOWED_USER_IDS', '')
    owner_ids = [int(o.strip()) for o in raw_owners.split(',') if o.strip().isdigit()]
    allowed_ids = [int(a.strip()) for a in raw_allowed.split(',') if a.strip().isdigit()]
    return user_id in owner_ids or user_id in allowed_ids

class Shutdown(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="close", aliases=["shutdown", "stopbot"], description="Safely disconnect and shut down the bot.")
    async def close_bot(self, ctx: commands.Context):
        """Safely shut down the bot."""
        is_owner = await self.bot.is_owner(ctx.author)
        if not is_owner and not is_authorized_admin(ctx.author.id):
            embed = discord.Embed(
                title="⛔ Permission Denied",
                description="You do not have permission to shut down this bot.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="🔌 Shutting Down",
            description=f"Shutting down {self.bot.user.mention if self.bot.user else 'the bot'}. Goodbye!",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)

        if hasattr(self.bot, 'session') and self.bot.session and not self.bot.session.closed:
            await self.bot.session.close()

        await self.bot.close()

async def setup(bot: commands.Bot):
    await bot.add_cog(Shutdown(bot))
