import random
import aiohttp
import discord
from discord.ext import commands

QUOTE_API = "https://yurippe.vercel.app/api/quotes?random"

FALLBACK_QUOTES = [
    {"character": "Kamina", "show": "Gurren Lagann", "quote": "Don't believe in yourself. Believe in me! Believe in the Kamina who believes in you!"},
    {"character": "Itachi Uchiha", "show": "Naruto", "quote": "Those who forgive themselves, and are able to accept their true nature... they are the strong ones."},
    {"character": "Saitama", "show": "One Punch Man", "quote": "The true power of us human beings is that we can change ourselves on our own."},
    {"character": "Monkey D. Luffy", "show": "One Piece", "quote": "If you don't take risks, you can't create a future."},
    {"character": "Eren Yeager", "show": "Attack on Titan", "quote": "If you win, you live. If you lose, you die. If you don't fight, you can't win!"},
    {"character": "Light Yagami", "show": "Death Note", "quote": "I am justice!"},
]


class AnimeQuote(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="animequote", aliases=["aq"], description="Get a random anime quote.")
    async def animequote(self, ctx: commands.Context):
        await ctx.defer()
        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        quote_data = None
        try:
            async with session.get(QUOTE_API, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    if isinstance(data, list) and data:
                        quote_data = random.choice(data)
        except Exception:
            pass
        finally:
            if close_session and session and not session.closed:
                await session.close()

        if not quote_data or not quote_data.get("quote"):
            quote_data = random.choice(FALLBACK_QUOTES)

        embed = discord.Embed(
            title="🎌 Anime Quote",
            description=f"### *\"{quote_data['quote']}\"*",
            color=discord.Color.magenta()
        )
        embed.set_footer(text=f"— {quote_data.get('character', 'Unknown')}, {quote_data.get('show', 'Unknown')}")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(AnimeQuote(bot))
