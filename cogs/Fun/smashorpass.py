import random
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

SMASH_LINES = [
    "No hesitation.",
    "The decision was made before you finished asking.",
    "Certified smash. Next question.",
    "Running through the wall like the Kool-Aid Man.",
    "The chemistry is undeniable 🔥",
]

PASS_LINES = [
    "Respectfully, no.",
    "I value our friendship far too much.",
    "Hard pass. Next!",
    "I've seen enough. Closing the app now.",
    "The vibe check failed 💀",
]


class SmashOrPass(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="smashorpass", aliases=["sop"], description="Deliver the ultimate verdict on a user.")
    @app_commands.describe(user="The user to judge (defaults to you)")
    async def smashorpass(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        target = user or ctx.author
        smashed = random.random() < 0.5

        if smashed:
            verdict = "SMASH 🔥"
            reason = random.choice(SMASH_LINES)
            color = discord.Color.green()
        else:
            verdict = "PASS 🚫"
            reason = random.choice(PASS_LINES)
            color = discord.Color.red()

        embed = discord.Embed(
            title=f"🔥 Smash or Pass — {target.display_name}",
            color=color
        )
        embed.add_field(name="Verdict", value=f"## {verdict}", inline=False)
        embed.add_field(name="Why", value=f"*{reason}*", inline=False)
        embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(SmashOrPass(bot))
