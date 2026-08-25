import aiohttp
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

YIFFY_API = "https://v2.yiff.rest"

SFW_CATEGORY_CHOICES = [
    app_commands.Choice(name="Birb", value="animals.birb"),
    app_commands.Choice(name="Blep", value="animals.blep"),
    app_commands.Choice(name="Dik Dik", value="animals.dikdik"),
    app_commands.Choice(name="Boop", value="furry.boop"),
    app_commands.Choice(name="Cuddle", value="furry.cuddle"),
    app_commands.Choice(name="Flop", value="furry.flop"),
    app_commands.Choice(name="Fursuit", value="furry.fursuit"),
    app_commands.Choice(name="Hold", value="furry.hold"),
    app_commands.Choice(name="Howl", value="furry.howl"),
    app_commands.Choice(name="Hug", value="furry.hug"),
    app_commands.Choice(name="Kiss", value="furry.kiss"),
    app_commands.Choice(name="Lick", value="furry.lick"),
    app_commands.Choice(name="Propose", value="furry.propose"),
]

NSFW_CATEGORY_CHOICES = [
    app_commands.Choice(name="Butts", value="furry.butts"),
    app_commands.Choice(name="Bulge", value="furry.bulge"),
    app_commands.Choice(name="Andromorph", value="furry.yiff.andromorph"),
    app_commands.Choice(name="Gay", value="furry.yiff.gay"),
    app_commands.Choice(name="Gynomorph", value="furry.yiff.gynomorph"),
    app_commands.Choice(name="Lesbian", value="furry.yiff.lesbian"),
    app_commands.Choice(name="Straight", value="furry.yiff.straight"),
]


class Yiffy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _is_nsfw_allowed(self, ctx: commands.Context) -> bool:
        return ctx.guild is not None and getattr(ctx.channel, "is_nsfw", lambda: False)()

    async def _fetch_random(self, category_db: str) -> Optional[dict]:
        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        url = f"{YIFFY_API}/{category_db.replace('.', '/')}"
        try:
            async with session.get(url, timeout=8) as resp:
                if resp.status != 200:
                    return None
                images = (await resp.json()).get("images", [])
                return images[0] if images else None
        except Exception:
            return None
        finally:
            if close_session and session and not session.closed:
                await session.close()

    def _build_embed(self, item: dict, display_name: str, nsfw: bool):
        artists = ", ".join(a for a in item.get("artists", [])[:3] if a) or "Unknown artist"
        prefix = "🔞" if nsfw else "🐾"
        embed = discord.Embed(title=f"{prefix} {display_name}", color=discord.Color.blurple())
        embed.set_image(url=item["url"])
        embed.set_footer(text=f"🎨 Artist: {artists}")

        view = discord.ui.View(timeout=180)
        source = next((s for s in item.get("sources", []) if isinstance(s, str) and s.startswith("http")), None)
        if source is None:
            source = item.get("shortURL")
        if isinstance(source, str) and source.startswith("http"):
            view.add_item(discord.ui.Button(label="Source", style=discord.ButtonStyle.link, url=source))
        return embed, view

    async def _send_random(self, ctx: commands.Context, category_db: str, display_name: str, nsfw: bool = False):
        await ctx.defer()
        item = await self._fetch_random(category_db)

        if item is None or not item.get("url"):
            embed_error = discord.Embed(
                title="Error",
                description="Couldn't fetch an image from the Yiffy API right now. Try again later.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed_error, ephemeral=True)
            return

        embed, view = self._build_embed(item, display_name, nsfw)
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="yiffy_sfw", description="Fetch a random SFW furry image from the Yiffy API.")
    @app_commands.describe(category="Image category (defaults to Fursuit)")
    @app_commands.choices(category=SFW_CATEGORY_CHOICES)
    async def yiffy_sfw(self, ctx: commands.Context, category: Optional[app_commands.Choice[str]] = None):
        category_db = category.value if category else "furry.fursuit"
        display_name = category.name if category else "Fursuit"
        await self._send_random(ctx, category_db, display_name)

    @commands.hybrid_command(name="yiffy_nsfw", description="Fetch a random NSFW furry image from the Yiffy API (NSFW channels only).")
    @app_commands.describe(category="Image category (defaults to Straight)")
    @app_commands.choices(category=NSFW_CATEGORY_CHOICES)
    async def yiffy_nsfw(self, ctx: commands.Context, category: Optional[app_commands.Choice[str]] = None):
        if not self._is_nsfw_allowed(ctx):
            await ctx.send("🔞 This command can only be used in Age-Restricted (NSFW) channels.", ephemeral=True)
            return
        category_db = category.value if category else "furry.yiff.straight"
        display_name = category.name if category else "Straight"
        await self._send_random(ctx, category_db, display_name, nsfw=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Yiffy(bot))
