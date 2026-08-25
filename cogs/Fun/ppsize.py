import hashlib
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

MAX_SIZE = 30


def _seeded_size(user_id: int) -> int:
    digest = hashlib.sha256(f"ppsize:{user_id}".encode()).hexdigest()
    return int(digest[:8], 16) % (MAX_SIZE + 1)


def _bar(size: int) -> str:
    filled = max(1, round(size / MAX_SIZE * 12))
    return "█" * filled + "░" * (12 - filled)


def _verdict(size: int) -> str:
    if size >= 25:
        return "Mega 🐴"
    if size >= 18:
        return "Above average 😏"
    if size >= 10:
        return "Perfectly average 📏"
    if size >= 4:
        return "Petite but mighty 🤏"
    return "Where is it? 🔍"


class PPSize(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="ppsize", description="Scientifically measure a user's PP size.")
    @app_commands.describe(user="The user to measure (defaults to you)")
    async def ppsize(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        target = user or ctx.author
        size = _seeded_size(target.id)

        embed = discord.Embed(
            title=f"📏 PP Size Machine — {target.display_name}",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Measurement", value=_bar(size), inline=False)
        embed.add_field(name="Size", value=f"`{size} cm`", inline=True)
        embed.add_field(name="Verdict", value=_verdict(size), inline=True)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text="Measured by science 🔬 | Results are 100% accurate*")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(PPSize(bot))
