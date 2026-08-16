import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import socket
from urllib.parse import urlparse
import re
import asyncio

class ConfirmationView(discord.ui.View):
    def __init__(self, target: str, timeout=60):
        super().__init__(timeout=timeout)
        self.target = target

    @discord.ui.button(label="Proceed", style=discord.ButtonStyle.green, emoji="✅")
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            target = self.target.strip()
            # If target has a scheme, parse netloc; otherwise check if it's a domain
            if target.startswith("http://") or target.startswith("https://"):
                parsed = urlparse(target)
                query_host = parsed.netloc.split(':')[0]
            else:
                query_host = target.split('/')[0].split(':')[0]

            # Asynchronous DNS resolution if it's a domain
            ip_pattern = r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$"
            if not re.match(ip_pattern, query_host):
                loop = asyncio.get_running_loop()
                try:
                    query_host = await loop.run_in_executor(None, socket.gethostbyname, query_host)
                except socket.gaierror:
                    embed_err = discord.Embed(
                        title="DNS Resolution Failed",
                        description=f"Could not resolve the domain `{self.target}` to a valid IP address.",
                        color=discord.Color.red()
                    )
                    await interaction.message.edit(embed=embed_err, view=None)
                    return

            # Request geolocation data
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://ip-api.com/json/{query_host}?fields=66846719", timeout=8) as response:
                    data = await response.json()

            if data.get("status") == "success":
                embed = discord.Embed(title=f"🌐 Geolocation: {self.target}", color=discord.Color.green())
                embed.add_field(name="Query Target / IP", value=data.get("query", "N/A"), inline=True)
                embed.add_field(name="Country", value=f"{data.get('country', 'N/A')} ({data.get('countryCode', 'N/A')})", inline=True)
                embed.add_field(name="Region / City", value=f"{data.get('regionName', 'N/A')}, {data.get('city', 'N/A')}", inline=True)
                embed.add_field(name="Coordinates", value=f"Lat: `{data.get('lat', 'N/A')}`, Lon: `{data.get('lon', 'N/A')}`", inline=True)
                embed.add_field(name="Timezone", value=data.get("timezone", "N/A"), inline=True)
                embed.add_field(name="ISP / Org", value=f"{data.get('isp', 'N/A')} / {data.get('org', 'N/A')}", inline=True)
                embed.add_field(name="AS Info", value=f"{data.get('as', 'N/A')}", inline=False)
                
                is_proxy = "Yes" if data.get("proxy") else "No"
                is_hosting = "Yes" if data.get("hosting") else "No"
                is_mobile = "Yes" if data.get("mobile") else "No"
                embed.add_field(name="Network Flags", value=f"Proxy/VPN: `{is_proxy}` | Hosting: `{is_hosting}` | Mobile: `{is_mobile}`", inline=False)

                await interaction.message.edit(embed=embed, view=None)
            else:
                msg = data.get("message", "Unknown error")
                failed_embed = discord.Embed(
                    title="Lookup Failed",
                    description=f"Could not retrieve geolocation for `{self.target}`. Reason: {msg}",
                    color=discord.Color.red()
                )
                await interaction.message.edit(embed=failed_embed, view=None)

        except Exception as e:
            error_embed = discord.Embed(title="Error", description=str(e), color=discord.Color.red())
            await interaction.message.edit(embed=error_embed, view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, emoji="✖️")
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        decline_embed = discord.Embed(title="Cancelled", description="Location lookup was cancelled.", color=discord.Color.red())
        await interaction.response.edit_message(embed=decline_embed, view=None)

class Loc(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="locate", description="Gets approximate geolocation information of a Website or IP.")
    @app_commands.describe(url_or_ip="Enter a Website URL, Domain, or IP Address")
    async def locate(self, ctx: commands.Context, url_or_ip: str):
        target = url_or_ip.strip()
        # Basic validation for domain or IP
        if not target:
            await ctx.send("Please provide a valid IP address or domain name.", ephemeral=True)
            return

        view = ConfirmationView(target)
        confirmation_embed = discord.Embed(
            title="🔍 Geolocation Lookup Confirmation",
            description=f"Are you sure you want to search for geolocation data on `{target}`?",
            color=discord.Color.blue()
        )
        await ctx.send(embed=confirmation_embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(Loc(bot))
