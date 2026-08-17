import discord
from discord.ext import commands
import aiohttp
from urllib.parse import quote_plus

class Minecraft(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="mcserver", description="Get Minecraft server status via api.mcsrvstat.us")
    async def mcserver(self, ctx: commands.Context, server: str):
        await ctx.defer()
        server = server.strip()
        if not server:
            await ctx.send('Provide a Minecraft server address.')
            return
        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True
        try:
            url = f'https://api.mcsrvstat.us/2/{quote_plus(server)}'
            async with session.get(url, timeout=8) as r:
                if r.status != 200:
                    await ctx.send('Failed to fetch server info.')
                    return
                data = await r.json()
                online = data.get('online')
                motd = data.get('motd', {}).get('clean', [])
                players = data.get('players', {})
                version = data.get('version')
                ip = data.get('ip') or server
                embed = discord.Embed(title=f'Minecraft Server: {ip}', color=discord.Color.dark_green())
                embed.add_field(name='Online', value=str(online), inline=True)
                embed.add_field(name='Version', value=str(version), inline=True)
                if players:
                    embed.add_field(name='Players', value=f"{players.get('online',0)}/{players.get('max','?')}", inline=True)
                if motd:
                    embed.add_field(name='MOTD', value='\n'.join(motd)[:1024], inline=False)
                await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f'Error fetching server: {e}')
        finally:
            if close_session and session and not session.closed:
                await session.close()

    @commands.hybrid_command(name="mcskin", description="Show Minecraft user skin and avatar.")
    async def mcskin(self, ctx: commands.Context, username: str):
        await ctx.defer()
        username = username.strip()
        if not username:
            await ctx.send('Provide a Minecraft username.')
            return
        head = f'https://minotar.net/avatar/{quote_plus(username)}/100.png'
        body = f'https://minotar.net/armor/body/{quote_plus(username)}/300.png'
        embed = discord.Embed(title=f'Minecraft Skin — {username}', color=discord.Color.dark_magenta())
        embed.set_thumbnail(url=head)
        embed.set_image(url=body)
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Minecraft(bot))
