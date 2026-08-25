import hashlib
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

RAINBOW = [
    discord.Color.from_str("#E40303"),
    discord.Color.from_str("#FF8C00"),
    discord.Color.from_str("#FFED00"),
    discord.Color.from_str("#008026"),
    discord.Color.from_str("#004DFF"),
    discord.Color.from_str("#750787"),
]


def _seeded_percent(user_id: int) -> int:
    digest = hashlib.sha256(f"gayness:{user_id}".encode()).hexdigest()
    return int(digest[:8], 16) % 101


def _verdict(percent: int) -> str:
    if percent >= 90:
        return "Certified rainbow legend 🌈"
    if percent >= 70:
        return "Fabulous and proud ✨"
    if percent >= 50:
        return "Halfway to fabulous 💅"
    if percent >= 20:
        return "A little sparkle detected 👀"
    return "Straight as a ruler 📏"


class Gayness(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="gayness", description="Measure a user's gay percentage.")
    @app_commands.describe(user="The user to measure (defaults to you)")
    async def gayness(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        target = user or ctx.author
        percent = _seeded_percent(target.id)
        color = RAINBOW[percent % len(RAINBOW)]

        embed = discord.Embed(
            title=f"🌈 Gayness Meter — {target.display_name}",
            description=f"### {percent}% gay",
            color=color
        )
        embed.add_field(name="Analysis", value=_verdict(percent), inline=False)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text="Love is love 💖")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Gayness(bot))
