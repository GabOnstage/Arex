import discord
from discord.ext import commands
from discord import app_commands
from dateutil import parser
import aiohttp
import asyncio
from datetime import datetime, timezone
from typing import Optional

class AdvancedMenu(discord.ui.View):
    def __init__(self, user_id=None, thumbnail_url=None, display_name=None, username=None, created_time_unix=None, bio=None, ban_status=None, html_url=None, full_body_avatar_url=None, timeout=180):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.thumbnail_url = thumbnail_url
        self.display_name = display_name
        self.username = username
        self.created_time_unix = created_time_unix
        self.bio = bio
        self.ban_status = ban_status
        self.html_url = html_url
        self.full_body_avatar_url = full_body_avatar_url
        self.last_online_str = "Unknown"
        self.user_presence_type = "Offline"
        self.friend_count = 0
        self.follower_count = 0
        self.message = None

    async def fetch_additional_data(self):
        async with aiohttp.ClientSession() as session:
            # Presence
            try:
                data = {"userIds": [int(self.user_id)]}
                async with session.post("https://presence.roblox.com/v1/presence/users", json=data, timeout=5) as resp:
                    if resp.status == 200:
                        presences = (await resp.json()).get("userPresences", [])
                        if presences:
                            p = presences[0]
                            last_online_raw = p.get("lastOnline")
                            if last_online_raw:
                                try:
                                    dt = parser.isoparse(last_online_raw)
                                    self.last_online_str = f"<t:{int(dt.timestamp())}:R>"
                                except Exception:
                                    self.last_online_str = "Unknown"
                            
                            ptype = p.get("userPresenceType", 0)
                            presence_map = {0: "Offline", 1: "Online", 2: "In Game", 3: "In Studio", 4: "Invisible"}
                            self.user_presence_type = presence_map.get(ptype, "Unknown")
            except Exception:
                pass

            # Friends & Followers
            try:
                async with session.get(f"https://friends.roblox.com/v1/users/{self.user_id}/friends/count", timeout=5) as resp:
                    if resp.status == 200:
                        self.friend_count = (await resp.json()).get("count", 0)
                async with session.get(f"https://friends.roblox.com/v1/users/{self.user_id}/followers/count", timeout=5) as resp:
                    if resp.status == 200:
                        self.follower_count = (await resp.json()).get("count", 0)
            except Exception:
                pass

    def build_basic_embed(self) -> discord.Embed:
        embed = discord.Embed(title=f"Roblox User: {self.username}", color=discord.Color.blue(), url=self.html_url)
        embed.add_field(name="Display Name", value=self.display_name or self.username, inline=True)
        embed.add_field(name="User ID", value=f"`{self.user_id}`", inline=True)
        embed.add_field(name="Ban Status", value=self.ban_status, inline=True)
        embed.add_field(name="Account Created", value=f"<t:{self.created_time_unix}:F>", inline=False)
        embed.add_field(name="Bio", value=self.bio[:1000], inline=False)
        embed.set_author(name=self.display_name or self.username, icon_url=self.thumbnail_url)
        embed.set_image(url=self.full_body_avatar_url)
        embed.set_thumbnail(url=self.thumbnail_url)
        return embed

    def build_advanced_embed(self) -> discord.Embed:
        embed = discord.Embed(title=f"Roblox User: {self.username} (Detailed)", color=discord.Color.blue(), url=self.html_url)
        embed.add_field(name="Display Name", value=self.display_name or self.username, inline=True)
        embed.add_field(name="User ID", value=f"`{self.user_id}`", inline=True)
        embed.add_field(name="Ban Status", value=self.ban_status, inline=True)
        embed.add_field(name="Account Created", value=f"<t:{self.created_time_unix}:F>", inline=False)
        embed.add_field(name="Presence Status", value=self.user_presence_type, inline=True)
        embed.add_field(name="Last Online", value=self.last_online_str, inline=True)
        embed.add_field(name="Friends Count", value=f"`{self.friend_count:,}`", inline=True)
        embed.add_field(name="Followers Count", value=f"`{self.follower_count:,}`", inline=True)
        embed.add_field(name="Bio", value=self.bio[:1000], inline=False)
        embed.set_author(name=self.display_name or self.username, icon_url=self.thumbnail_url)
        embed.set_image(url=self.full_body_avatar_url)
        embed.set_thumbnail(url=self.thumbnail_url)
        return embed

    @discord.ui.button(label="Basic Info", style=discord.ButtonStyle.secondary, emoji="◀️", custom_id="basic_btn", disabled=True)
    async def basic_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.disabled = True
        for child in self.children:
            if getattr(child, 'custom_id', None) == "adv_btn":
                child.disabled = False
        embed = self.build_basic_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Detailed Info", style=discord.ButtonStyle.primary, emoji="🔍", custom_id="adv_btn")
    async def adv_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.disabled = True
        for child in self.children:
            if getattr(child, 'custom_id', None) == "basic_btn":
                child.disabled = False

        await interaction.response.defer()
        await self.fetch_additional_data()
        embed = self.build_advanced_embed()
        await interaction.message.edit(embed=embed, view=self)

    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.style != discord.ButtonStyle.link:
                item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

class Find(commands.Cog):
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

    @commands.hybrid_command(name="find", description="Retrieve detailed information about a Roblox user.")
    @app_commands.describe(roblox_user="Enter a Roblox username or User ID")
    async def find_roblox_user(self, ctx: commands.Context, roblox_user: str):
        await ctx.defer()
        target = roblox_user.strip()

        if target.isdigit():
            user_id = int(target)
        else:
            user_id = await self.find_roblox_id(target)

        if user_id is None:
            embed_notfound = discord.Embed(
                title="User Not Found",
                description=f"Could not locate a Roblox account with username or ID `{roblox_user}`.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed_notfound, ephemeral=True)
            return

        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            # 1. User main details
            async with session.get(f"https://users.roblox.com/v1/users/{user_id}", timeout=6) as resp:
                if resp.status != 200:
                    await ctx.send(f"Roblox API returned error (Status: {resp.status}) for user ID `{user_id}`.")
                    return
                user_data = await resp.json()

            display_name = user_data.get("displayName", "")
            username = user_data.get("name", "")
            created_iso = user_data.get("created", "")
            bio = user_data.get("description", "").strip() or "No biography provided."
            ban_status = "Banned ❌" if user_data.get("isBanned") else "Active ✅"

            try:
                created_dt = parser.isoparse(created_iso)
                created_unix = int(created_dt.timestamp())
            except Exception:
                created_unix = int(datetime.now(timezone.utc).timestamp())

            # 2. Thumbnail & Full body avatar
            thumb_url = None
            full_body_url = None

            async with session.get(f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=150x150&format=png&isCircular=false", timeout=5) as t_resp:
                if t_resp.status == 200:
                    t_data = await t_resp.json()
                    t_list = t_data.get("data", [])
                    if t_list:
                        thumb_url = t_list[0].get("imageUrl")

            async with session.get(f"https://thumbnails.roblox.com/v1/users/avatar?userIds={user_id}&size=720x720&format=png&isCircular=false", timeout=5) as b_resp:
                if b_resp.status == 200:
                    b_data = await b_resp.json()
                    b_list = b_data.get("data", [])
                    if b_list:
                        full_body_url = b_list[0].get("imageUrl")

            html_url = f"https://www.roblox.com/users/{user_id}/profile"

            view = AdvancedMenu(
                user_id=user_id,
                thumbnail_url=thumb_url,
                display_name=display_name,
                username=username,
                created_time_unix=created_unix,
                bio=bio,
                ban_status=ban_status,
                html_url=html_url,
                full_body_avatar_url=full_body_url
            )
            view.add_item(discord.ui.Button(label="Open Roblox Profile", style=discord.ButtonStyle.link, url=html_url, emoji="🎮"))

            embed = view.build_basic_embed()
            msg = await ctx.send(embed=embed, view=view)
            view.message = msg

        except Exception as e:
            await ctx.send(f"An error occurred while fetching Roblox user information: {e}")
        finally:
            if close_session and session and not session.closed:
                await session.close()

async def setup(bot: commands.Bot):
    await bot.add_cog(Find(bot))