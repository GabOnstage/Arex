import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import random
from typing import Optional

RIZZ_LINES = [
    "Are you a magician? Because whenever I look at you, everyone else disappears.",
    "Do you have a map? I keep getting lost in your eyes.",
    "Are you Wi-Fi? Because I'm really feeling a connection.",
    "Is your name Google? Because you have everything I’ve been searching for.",
    "If you were a vegetable, you’d be a cute-cumber.",
    "Do you believe in love at first sight, or should I walk by again?",
    "Are you a camera? Every time I look at you, I smile.",
    "Is it hot in here or is it just you?",
    "If being sexy was a crime, you’d be serving a life sentence.",
    "Are you French? Because Eiffel for you.",
    "Do you like Star Wars? Because Yoda only one for me.",
    "Are you made of copper and tellurium? Because you're Cu-Te.",
    "Can I follow you home? Cause my parents always told me to follow my dreams.",
    "Are you an interior decorator? Because when you walked in, the room became beautiful.",
    "If you were a triangle, you'd be an acute one.",
    "Are you a parking ticket? Because you've got FINE written all over you.",
    "I must be a snowflake, because I've fallen for you.",
    "Are you a keyboard? Because you're definitely my type.",
    "Do you have a sunburn, or are you always this hot?",
    "Is your name Chapstick? Because you're da balm."
]

async def fetch_rizz(bot: commands.Bot) -> str:
    session = getattr(bot, 'session', None)
    close_session = False
    if session is None or session.closed:
        session = aiohttp.ClientSession()
        close_session = True

    try:
        async with session.get("https://vincenttechblog.com/api/rizz.php", timeout=4) as response:
            if response.status == 200:
                data = await response.json(content_type=None)
                if isinstance(data, dict) and "text" in data:
                    return data["text"]
                elif isinstance(data, dict) and "rizz" in data:
                    return data["rizz"]
    except Exception:
        pass
    finally:
        if close_session and session and not session.closed:
            await session.close()
    return random.choice(RIZZ_LINES)

class RizzView(discord.ui.View):
    def __init__(self, bot: commands.Bot, target_user: Optional[discord.Member] = None, timeout=180):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.target_user = target_user

    @discord.ui.button(label="More Rizz", emoji="🔥", style=discord.ButtonStyle.primary)
    async def new_rizz(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        line = await fetch_rizz(self.bot)
        
        embed = discord.Embed(
            title="😏 Ultimate Rizz",
            description=f"### *\"{line}\"*",
            color=discord.Color.nitro_pink()
        )
        content = f"{self.target_user.mention}" if self.target_user else None
        await interaction.edit_original_response(content=content, embed=embed, view=self)

class Rizz(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="rizz", description="Generate a smooth or hilarious rizz / pickup line.")
    @app_commands.describe(user="Select a user you want to rizz up")
    async def rizz(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        """Generate a rizz line."""
        await ctx.defer()
        line = await fetch_rizz(self.bot)

        embed = discord.Embed(
            title="😏 Ultimate Rizz",
            description=f"### *\"{line}\"*",
            color=discord.Color.nitro_pink()
        )
        embed.set_footer(text=f"Delivered by {ctx.author.display_name}")

        content = f"{user.mention}" if user else None
        view = RizzView(self.bot, target_user=user)
        await ctx.send(content=content, embed=embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(Rizz(bot))
