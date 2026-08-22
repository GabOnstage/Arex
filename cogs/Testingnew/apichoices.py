import discord
from discord.ext import commands
from discord import app_commands
from typing import List
import aiohttp

ROBLOX_USER_CACHE: dict = {}

class ChoiceApi(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name='dynachoiceapi', description="Demonstration of dynamic API choices autocomplete.")
    async def fruits(self, ctx: commands.Context, username: str):
        await ctx.send(f'Selected username: `{username}`')

    @fruits.autocomplete('username')
    async def fruits_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        query = current.strip().lower()
        if not query:
            return []

        # Check cache
        if cached := ROBLOX_USER_CACHE.get(query):
            return cached

        # Make API request
        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            async with session.get(f'https://users.roblox.com/v1/users/search?keyword={query}&limit=10', timeout=aiohttp.ClientTimeout(total=2)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    users = data.get('data', [])
                    choices = [
                        app_commands.Choice(name=user['name'], value=user['name'])
                        for user in users if 'name' in user
                    ][:10]

                    if choices:
                        ROBLOX_USER_CACHE[query] = choices
                    return choices
                return []
        except Exception:
            return []
        finally:
            if close_session and session and not session.closed:
                await session.close()

async def setup(bot: commands.Bot):
    await bot.add_cog(ChoiceApi(bot))