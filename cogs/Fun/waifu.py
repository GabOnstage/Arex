import aiohttp
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

WAIFU_API = "https://api.waifu.im/images"

TAG_CHOICES = [
    app_commands.Choice(name="Waifu", value="waifu"),
    app_commands.Choice(name="Maid", value="maid"),
    app_commands.Choice(name="Uniform", value="uniform"),
    app_commands.Choice(name="Selfies", value="selfies"),
]


class Waifu(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _fetch_image(self, tag: str, animated: bool) -> Optional[dict]:
        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        params = {"IncludedTags": tag, "IsNsfw": "false"}
        if animated:
            params["Gif"] = "true"

        try:
            async with session.get(WAIFU_API, params=params, timeout=6) as resp:
                if resp.status != 200:
                    return None
                items = (await resp.json()).get("items", [])
                return items[0] if items else None
        except Exception:
            return None
        finally:
            if close_session and session and not session.closed:
                await session.close()

    @staticmethod
    def _build_embed(item: dict, tag_value: str):
        try:
            color = discord.Color.from_str(item.get("dominantColor") or "#ff6fa3")
        except ValueError:
            color = discord.Color(0xEB459E)

        artists = ", ".join(a.get("name", "Unknown") for a in item.get("artists", [])[:3]) or "Unknown artist"

        embed = discord.Embed(title=f"🌸 {tag_value.replace('-', ' ').title()}", color=color)
        embed.set_image(url=item["url"])
        embed.set_footer(text=f"🎨 Artist: {artists}")
        view = discord.ui.View(timeout=180)
        source = item.get("source")
        if isinstance(source, str) and source.startswith("http"):
            view.add_item(discord.ui.Button(label="Source", style=discord.ButtonStyle.link, url=source))
        return embed, view

    async def _send_image(self, ctx: commands.Context, tag_value: str, animated: bool):
        await ctx.defer()
        item = await self._fetch_image(tag_value, animated)

        if item is None:
            embed_error = discord.Embed(
                title="Error",
                description="Couldn't fetch an image from waifu.im right now. Try again later.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed_error, ephemeral=True)
            return

        embed, view = self._build_embed(item, tag_value)
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="waifu", description="Fetch a random SFW anime image from waifu.im.")
    @app_commands.describe(tag="Image category (defaults to Waifu)", animated="Only GIFs instead of static images")
    @app_commands.choices(tag=TAG_CHOICES)
    async def waifu(self, ctx: commands.Context, tag: Optional[app_commands.Choice[str]] = None, animated: bool = False):
        tag_value = tag.value if tag else "waifu"
        await self._send_image(ctx, tag_value, animated)


async def setup(bot: commands.Bot):
    await bot.add_cog(Waifu(bot))
