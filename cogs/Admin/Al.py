import os
import discord
from discord.ext import commands

def get_allowed_user_ids():
    raw = os.getenv('ALLOWED_USER_IDS', '')
    return [u.strip() for u in raw.split(',') if u.strip().isdigit()]

class AllowedUsers(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="al", description="List all verified bot administrators.")
    async def al(self, ctx: commands.Context):
        allowed_ids = get_allowed_user_ids()
        
        # Check if the user invoking the command is an allowed admin or bot owner
        is_owner = await self.bot.is_owner(ctx.author)
        if str(ctx.author.id) not in allowed_ids and not is_owner:
            embed = discord.Embed(
                title="Permission Denied",
                description="You do not have permission to use this command.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="🛡️ Verified Bot Administrators",
            color=discord.Color.blue()
        )

        if not allowed_ids:
            embed.description = "No specific allowed user IDs configured."
        else:
            for user_id in allowed_ids:
                try:
                    user = await self.bot.fetch_user(int(user_id))
                    if user:
                        embed.add_field(name=user.name, value=f"ID: `{user.id}`", inline=False)
                except discord.NotFound:
                    embed.add_field(name="Unknown User", value=f"ID: `{user_id}` (Not Found)", inline=False)
                except Exception:
                    pass

        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(AllowedUsers(bot))
