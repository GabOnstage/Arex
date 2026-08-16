import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from datetime import datetime, timezone
from typing import Optional

class Robloxbadge(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def find_roblox_id(self, username: str) -> Optional[int]:
        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            api_url = "https://users.roblox.com/v1/usernames/users"
            params = {"usernames": [username], "excludeBannedUsers": False}
            async with session.post(api_url, json=params, timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    users = data.get("data", [])
                    if users:
                        return users[0].get("id")
        except Exception:
            return None
        finally:
            if close_session and session and not session.closed:
                await session.close()
        return None

    @commands.hybrid_command(name="badge", description="Fetch badges owned by a Roblox user.")
    @app_commands.describe(user="Roblox username or numerical User ID")
    async def badge(self, ctx: commands.Context, user: str):
        await ctx.defer()
        target = user.strip()

        if target.isdigit():
            userid = int(target)
        else:
            userid = await self.find_roblox_id(target)

        if userid is None:
            await ctx.send(f"Invalid username or ID `{user}`.", ephemeral=True)
            return

        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            url = f'https://badges.roblox.com/v1/users/{userid}/badges?limit=10&sortOrder=Desc'
            async with session.get(url, timeout=6) as response:
                if response.status != 200:
                    await ctx.send("Failed to retrieve badges from Roblox API.")
                    return
                badges_data = await response.json()

            badge_list = badges_data.get('data', [])

            embed = discord.Embed(
                title=f"🏅 Badges for {user}",
                url=f"https://www.roblox.com/users/{userid}/profile",
                color=discord.Color.blue()
            )

            if not badge_list:
                embed.description = "This user does not have any public badges."
            else:
                for badge in badge_list:
                    b_name = badge.get('name', 'Unnamed Badge')
                    b_id = badge.get('id')
                    b_desc = badge.get('description', 'No description') or "No description"
                    badge_url = f"https://www.roblox.com/badges/{b_id}" if b_id else "https://www.roblox.com"
                    embed.add_field(
                        name=f"🎖️ {b_name}",
                        value=f"[View Badge on Roblox]({badge_url})\n*{b_desc[:200]}*",
                        inline=False
                    )

            embed.set_footer(text=f"Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
            await ctx.send(embed=embed)

        except Exception as e:
            await ctx.send(f"An error occurred: {e}")
        finally:
            if close_session and session and not session.closed:
                await session.close()

async def setup(bot: commands.Bot):
    await bot.add_cog(Robloxbadge(bot))