import aiohttp
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

NEKOS_API = "https://nekos.life/api/v2/img/"

ACTIONS = [
    app_commands.Choice(name="Hug", value="hug"),
    app_commands.Choice(name="Kiss", value="kiss"),
    app_commands.Choice(name="Pat", value="pat"),
    app_commands.Choice(name="Slap", value="slap"),
    app_commands.Choice(name="Poke", value="poke"),
    app_commands.Choice(name="Cuddle", value="cuddle"),
    app_commands.Choice(name="Tickle", value="tickle"),
    app_commands.Choice(name="Feed", value="feed"),
]

VERBS = {
    "hug": "hugged",
    "kiss": "kissed",
    "pat": "patted",
    "slap": "slapped",
    "poke": "poked",
    "cuddle": "cuddled",
    "tickle": "tickled",
    "feed": "fed",
}


class Action(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="action", description="Send an anime reaction GIF to a user.")
    @app_commands.describe(type="The action to perform", user="The target of your action (optional)")
    @app_commands.choices(type=ACTIONS)
    async def action(self, ctx: commands.Context, type: app_commands.Choice[str], user: Optional[discord.Member] = None):
        await ctx.defer()
        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        gif_url = None
        try:
            async with session.get(f"{NEKOS_API}{type.value}", timeout=5) as resp:
                if resp.status == 200:
                    gif_url = (await resp.json()).get("url")
        except Exception:
            pass
        finally:
            if close_session and session and not session.closed:
                await session.close()

        if not gif_url:
            embed_error = discord.Embed(
                title="Error",
                description="Couldn't fetch a GIF right now. Try again later.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed_error, ephemeral=True)
            return

        verb = VERBS.get(type.value, type.value)
        if user and user.id == ctx.author.id:
            caption = f"{ctx.author.display_name} {verb} themselves... interesting choice 👀"
        elif user and user.id == self.bot.user.id:
            caption = f"Wh-what?! {ctx.author.display_name} {verb} me?! 😳"
        elif user:
            caption = f"{ctx.author.display_name} {verb} {user.display_name}!"
        else:
            caption = f"{ctx.author.display_name} {verb} nobody in particular..."

        embed = discord.Embed(description=caption, color=discord.Color(0xEB459F))
        embed.set_image(url=gif_url)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Action(bot))
