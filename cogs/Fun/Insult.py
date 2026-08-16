import aiohttp
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
import html

API_URL_INSULT = "https://evilinsult.com/generate_insult.php?lang=en&type=json"

class Insult(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ctx_menu = app_commands.ContextMenu(
            name='Insult User',
            callback=self.handle_insult_context_menu,
            allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True),
            allowed_installs=app_commands.AppInstallationType(guild=True, user=True)
        )
        try:
            self.bot.tree.add_command(self.ctx_menu)
        except Exception:
            pass

    def cog_unload(self):
        try:
            self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)
        except Exception:
            pass

    async def _fetch_insult(self) -> Optional[str]:
        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            async with session.get(API_URL_INSULT, timeout=5) as response:
                if response.status == 200:
                    insult_data = await response.json()
                    return html.unescape(insult_data.get('insult', ''))
                return None
        except Exception:
            return None
        finally:
            if close_session and session and not session.closed:
                await session.close()

    async def handle_insult_context_menu(self, interaction: discord.Interaction, user: discord.User):
        await interaction.response.defer()
        insult = await self._fetch_insult()
        if insult:
            await interaction.followup.send(f"{user.mention}, {insult}")
        else:
            await interaction.followup.send("Failed to fetch an insult. Please try again later.", ephemeral=True)

    @commands.hybrid_command(name="insult", description="Generate and send a playful insult.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(user="Select a user to insult")
    async def insult(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        insult = await self._fetch_insult()
        if insult:
            if user:
                await ctx.send(f"{user.mention}, {insult}")
            else:
                await ctx.send(insult)
        else:
            error_embed = discord.Embed(
                title="Error",
                description="Failed to fetch an insult from EvilInsult API. Please try again later.",
                color=discord.Color.red()
            )
            await ctx.send(embed=error_embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Insult(bot))