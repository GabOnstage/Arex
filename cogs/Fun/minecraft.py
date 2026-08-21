import discord
from discord.ext import commands
import aiohttp
from urllib.parse import quote_plus


def _format_uuid(raw_uuid: str) -> str:
    raw = raw_uuid.replace('-', '')
    if len(raw) != 32:
        return raw_uuid
    return f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"


class Minecraft(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="mcserver", description="Get Minecraft server status via api.mcsrvstat.us")
    @commands.cooldown(1, 5, commands.BucketType.user)
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
            url = f'https://api.mcsrvstat.us/3/{quote_plus(server)}'
            async with session.get(url, timeout=8) as r:
                if r.status != 200:
                    await ctx.send('Failed to fetch server info.')
                    return
                data = await r.json()

            if not data.get('online'):
                embed = discord.Embed(
                    title=f'Minecraft Server: {server}',
                    description='❌ Server is **offline** or unreachable.',
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return

            motd = data.get('motd', {}).get('clean', [])
            players = data.get('players', {})
            version = data.get('version')
            ip = data.get('ip') or server
            hostname = data.get('hostname')

            embed = discord.Embed(
                title=f'Minecraft Server: {hostname or ip}',
                url=f'https://mcsrvstat.us/server/{quote_plus(server)}',
                color=discord.Color.dark_green()
            )
            embed.add_field(name='Status', value='🟢 Online', inline=True)
            if version:
                embed.add_field(name='Version', value=str(version)[:200], inline=True)
            if players:
                value = f"{players.get('online', 0)}/{players.get('max', '?')}"
                sample = players.get('list') or []
                if sample:
                    value += "\n" + ", ".join(p.get('name', '?') for p in sample[:10])
                embed.add_field(name='Players', value=value[:1024], inline=True)
            if motd:
                embed.add_field(name='MOTD', value='\n'.join(motd)[:1024], inline=False)
            if data.get('icon'):
                embed.set_thumbnail(url=data['icon'])
            embed.set_footer(text='Data by api.mcsrvstat.us')
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f'Error fetching server: {e}')
        finally:
            if close_session and session and not session.closed:
                await session.close()

    async def _resolve_uuid(self, session: aiohttp.ClientSession, username: str):
        """Resolve a Minecraft username to (name, dashed_uuid) via the Mojang API."""
        url = f'https://api.mojang.com/users/profiles/minecraft/{quote_plus(username)}'
        async with session.get(url, timeout=8) as resp:
            if resp.status != 200:
                return None
            data = await resp.json(content_type=None)
            if not isinstance(data, dict) or 'id' not in data:
                return None
            return data.get('name', username), _format_uuid(data['id'])

    @commands.hybrid_command(name="mcskin", description="Look up a Minecraft user and show their skin and avatar.")
    @app_commands.describe(username="Minecraft username")
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def mcskin(self, ctx: commands.Context, username: str):
        await ctx.defer()
        username = username.strip()
        if not username:
            await ctx.send('Provide a Minecraft username.')
            return

        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True
        try:
            resolved = await self._resolve_uuid(session, username)
            if resolved is None:
                await ctx.send(f"Could not find a Minecraft account named `{username}`.")
                return
            name, uuid = resolved

            embed = discord.Embed(title=f'Minecraft User: {name}', color=discord.Color.dark_magenta())
            embed.add_field(name='Username', value=name, inline=True)
            embed.add_field(name='UUID', value=f"`{uuid}`", inline=False)

            face_url = f'https://crafatar.com/avatars/{uuid}?overlay&size=128'
            body_url = f'https://crafatar.com/renders/body/{uuid}?overlay&scale=6'
            skin_url = f'https://crafatar.com/skins/{uuid}'
            embed.set_thumbnail(url=face_url)
            embed.set_image(url=body_url)
            embed.set_footer(text='Renders by crafatar.com • Data by Mojang API')

            view = discord.ui.View(timeout=180)
            view.add_item(discord.ui.Button(label='NameMC Profile', style=discord.ButtonStyle.link,
                                            url=f'https://namemc.com/profile/{uuid}', emoji='🔍'))
            view.add_item(discord.ui.Button(label='Download Skin', style=discord.ButtonStyle.link,
                                            url=skin_url, emoji='🖼️'))
            await ctx.send(embed=embed, view=view)
        except Exception as e:
            await ctx.send(f'Error fetching user: {e}')
        finally:
            if close_session and session and not session.closed:
                await session.close()


async def setup(bot: commands.Bot):
    await bot.add_cog(Minecraft(bot))
