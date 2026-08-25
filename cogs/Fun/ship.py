import hashlib
import discord
from discord.ext import commands
from discord import app_commands


def _seeded_percent(a: int, b: int) -> int:
    low, high = sorted((a, b))
    digest = hashlib.sha256(f"{low}:{high}".encode()).hexdigest()
    return int(digest[:8], 16) % 101


def _heart_bar(percent: int) -> str:
    filled = round(percent / 10)
    return "❤️" * filled + "🖤" * (10 - filled)


def _ship_quote(percent: int) -> str:
    if percent >= 90:
        return "A match made in heaven! Start planning the wedding 💍"
    if percent >= 70:
        return "Strong chemistry detected 🔥"
    if percent >= 50:
        return "There's definitely potential here 😉"
    if percent >= 30:
        return "Hmm... friendship might be the safer option 🤔"
    if percent >= 10:
        return "The odds are not in your favor 😬"
    return "Even Google couldn't find any chemistry here 💀"


class Ship(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="ship", description="Calculate the compatibility between two users.")
    @app_commands.describe(user1="First user to ship", user2="Second user to ship")
    async def ship(self, ctx: commands.Context, user1: discord.Member, user2: discord.Member):
        percent = _seeded_percent(user1.id, user2.id)

        embed = discord.Embed(
            title=f"💕 {user1.display_name} × {user2.display_name}",
            description=f"{_heart_bar(percent)}\n\n### {percent}% compatible",
            color=discord.Color.nitro_pink()
        )
        embed.add_field(name="Verdict", value=_ship_quote(percent), inline=False)
        embed.set_thumbnail(url=user2.display_avatar.url)
        embed.set_author(
            name=f"Shipped by {ctx.author.display_name}",
            icon_url=ctx.author.display_avatar.url
        )
        if percent == 100:
            embed.set_footer(text="💯 PERFECT MATCH — destiny has spoken!")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Ship(bot))
