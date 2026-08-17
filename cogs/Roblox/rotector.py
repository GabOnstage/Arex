import discord
from discord.ext import commands
import aiohttp
import io
import json
import os
from typing import List, Optional

ROTECTOR_BASE = "https://api.rotector.com/v1/lookup"
# Allow API key via environment variable ROTECTOR_API_KEY

def _get_auth_headers() -> dict:
    key = os.getenv('ROTECTOR_API_KEY')
    if not key:
        return {}
    return {"Authorization": f"Bearer {key}"}

def _make_file_from_json(data: dict, name: str = "result.json") -> discord.File:
    s = io.StringIO()
    json.dump(data, s, indent=2)
    s.seek(0)
    return discord.File(fp=io.BytesIO(s.getvalue().encode('utf-8')), filename=name)

class Rotector(commands.Cog):
    """Commands to interact with the Rotector API (roblox/discord flags).

    Note: Do not cache responses >24 hours. The cog will not store responses.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _request(self, method: str, path: str, session: aiohttp.ClientSession, **kwargs):
        url = f"{ROTECTOR_BASE}{path}"
        headers = _get_auth_headers()
        if 'headers' in kwargs:
            headers.update(kwargs.pop('headers'))
        try:
            async with session.request(method, url, headers=headers, timeout=10, **kwargs) as r:
                if r.status == 429:
                    retry = r.headers.get('Retry-After') or 'slow down'
                    return {'error': f'Rate limited: retry after {retry}', 'status': r.status}
                text = await r.text()
                try:
                    return json.loads(text)
                except Exception:
                    return {'raw': text}
        except Exception as e:
            return {'error': str(e)}

    # --- Roblox User endpoints ---
    @commands.hybrid_command(name='rotector_user', description='Get Rotector flag info for a Roblox user by ID')
    async def rotector_user(self, ctx: commands.Context, user_id: int):
        await ctx.defer()
        session = getattr(self.bot, 'session', None) or aiohttp.ClientSession()
        close = getattr(self.bot, 'session', None) is None
        try:
            resp = await self._request('GET', f'/roblox/user/{user_id}', session)
            if isinstance(resp, dict) and ('error' in resp):
                await ctx.send(f"Error: {resp['error']}")
                return
            # send JSON as file if large
            out = json.dumps(resp, indent=2)
            if len(out) > 1000:
                await ctx.send(file=_make_file_from_json(resp, f'roblox_user_{user_id}.json'))
            else:
                embed = discord.Embed(title=f'Rotector — Roblox User {user_id}', color=discord.Color.red())
                embed.description = f"```json\n{out}\n```"
                await ctx.send(embed=embed)
        finally:
            if close:
                await session.close()

    @commands.hybrid_command(name='rotector_user_plain', description='Get only flag status for Roblox user (plaintext)')
    async def rotector_user_plain(self, ctx: commands.Context, user_id: int):
        await ctx.defer()
        session = getattr(self.bot, 'session', None) or aiohttp.ClientSession()
        close = getattr(self.bot, 'session', None) is None
        try:
            resp = await self._request('GET', f'/roblox/user/{user_id}/plaintext', session)
            await ctx.send(f'User {user_id} status: {resp}')
        finally:
            if close:
                await session.close()

    @commands.hybrid_command(name='rotector_user_batch', description='Batch lookup Roblox users (comma or space separated IDs)')
    async def rotector_user_batch(self, ctx: commands.Context, *, ids: str):
        await ctx.defer()
        id_list = [int(x) for x in ids.replace(',', ' ').split()[:50]]
        if not id_list:
            await ctx.send('Provide at least one user ID (max 50).')
            return
        session = getattr(self.bot, 'session', None) or aiohttp.ClientSession()
        close = getattr(self.bot, 'session', None) is None
        try:
            payload = {'ids': id_list}
            resp = await self._request('POST', '/roblox/user', session, json=payload)
            if isinstance(resp, dict) and ('error' in resp):
                await ctx.send(f"Error: {resp['error']}")
                return
            await ctx.send(file=_make_file_from_json(resp, 'roblox_users_batch.json'))
        finally:
            if close:
                await session.close()

    @commands.hybrid_command(name='rotector_user_status_batch', description='Batch user flag statuses (status only)')
    async def rotector_user_status_batch(self, ctx: commands.Context, *, ids: str):
        await ctx.defer()
        id_list = [int(x) for x in ids.replace(',', ' ').split()[:100]]
        if not id_list:
            await ctx.send('Provide at least one user ID (max 100).')
            return
        session = getattr(self.bot, 'session', None) or aiohttp.ClientSession()
        close = getattr(self.bot, 'session', None) is None
        try:
            payload = {'ids': id_list}
            resp = await self._request('POST', '/roblox/user/status', session, json=payload)
            if isinstance(resp, dict) and ('error' in resp):
                await ctx.send(f"Error: {resp['error']}")
                return
            await ctx.send(file=_make_file_from_json(resp, 'roblox_users_status_batch.json'))
        finally:
            if close:
                await session.close()

    @commands.hybrid_command(name='rotector_user_discord', description='Get Discord accounts linked to a Roblox user')
    async def rotector_user_discord(self, ctx: commands.Context, user_id: int):
        await ctx.defer()
        session = getattr(self.bot, 'session', None) or aiohttp.ClientSession()
        close = getattr(self.bot, 'session', None) is None
        try:
            resp = await self._request('GET', f'/roblox/user/{user_id}/discord', session)
            if isinstance(resp, dict) and ('error' in resp):
                await ctx.send(f"Error: {resp['error']}")
                return
            await ctx.send(file=_make_file_from_json(resp, f'roblox_user_{user_id}_discord.json'))
        finally:
            if close:
                await session.close()

    # --- Roblox Group endpoints ---
    @commands.hybrid_command(name='rotector_group', description='Get Rotector flag info for a Roblox group by ID')
    async def rotector_group(self, ctx: commands.Context, group_id: int):
        await ctx.defer()
        session = getattr(self.bot, 'session', None) or aiohttp.ClientSession()
        close = getattr(self.bot, 'session', None) is None
        try:
            resp = await self._request('GET', f'/roblox/group/{group_id}', session)
            if isinstance(resp, dict) and ('error' in resp):
                await ctx.send(f"Error: {resp['error']}")
                return
            out = json.dumps(resp, indent=2)
            if len(out) > 1000:
                await ctx.send(file=_make_file_from_json(resp, f'roblox_group_{group_id}.json'))
            else:
                embed = discord.Embed(title=f'Rotector — Roblox Group {group_id}', description=f"```json\n{out}\n```", color=discord.Color.dark_green())
                await ctx.send(embed=embed)
        finally:
            if close:
                await session.close()

    @commands.hybrid_command(name='rotector_group_plain', description='Get only flag status for Roblox group (plaintext)')
    async def rotector_group_plain(self, ctx: commands.Context, group_id: int):
        await ctx.defer()
        session = getattr(self.bot, 'session', None) or aiohttp.ClientSession()
        close = getattr(self.bot, 'session', None) is None
        try:
            resp = await self._request('GET', f'/roblox/group/{group_id}/plaintext', session)
            await ctx.send(f'Group {group_id} status: {resp}')
        finally:
            if close:
                await session.close()

    @commands.hybrid_command(name='rotector_group_batch', description='Batch lookup Roblox groups (comma or space separated IDs)')
    async def rotector_group_batch(self, ctx: commands.Context, *, ids: str):
        await ctx.defer()
        id_list = [int(x) for x in ids.replace(',', ' ').split()[:50]]
        if not id_list:
            await ctx.send('Provide at least one group ID (max 50).')
            return
        session = getattr(self.bot, 'session', None) or aiohttp.ClientSession()
        close = getattr(self.bot, 'session', None) is None
        try:
            payload = {'ids': id_list}
            resp = await self._request('POST', '/roblox/group', session, json=payload)
            if isinstance(resp, dict) and ('error' in resp):
                await ctx.send(f"Error: {resp['error']}")
                return
            await ctx.send(file=_make_file_from_json(resp, 'roblox_groups_batch.json'))
        finally:
            if close:
                await session.close()

    @commands.hybrid_command(name='rotector_group_tracked', description='Get tracked users in a Roblox group')
    async def rotector_group_tracked(self, ctx: commands.Context, group_id: int):
        await ctx.defer()
        session = getattr(self.bot, 'session', None) or aiohttp.ClientSession()
        close = getattr(self.bot, 'session', None) is None
        try:
            resp = await self._request('GET', f'/roblox/group/{group_id}/tracked-users', session)
            if isinstance(resp, dict) and ('error' in resp):
                await ctx.send(f"Error: {resp['error']}")
                return
            await ctx.send(file=_make_file_from_json(resp, f'group_{group_id}_tracked_users.json'))
        finally:
            if close:
                await session.close()

    # --- Discord User endpoints ---
    @commands.hybrid_command(name='rotector_discord', description='Get Rotector info for a Discord user by ID')
    async def rotector_discord(self, ctx: commands.Context, discord_id: int):
        await ctx.defer()
        session = getattr(self.bot, 'session', None) or aiohttp.ClientSession()
        close = getattr(self.bot, 'session', None) is None
        try:
            resp = await self._request('GET', f'/discord/user/{discord_id}', session)
            if isinstance(resp, dict) and ('error' in resp):
                await ctx.send(f"Error: {resp['error']}")
                return
            await ctx.send(file=_make_file_from_json(resp, f'discord_user_{discord_id}.json'))
        finally:
            if close:
                await session.close()

    @commands.hybrid_command(name='rotector_discord_batch', description='Batch lookup Discord users (IDs comma/space separated)')
    async def rotector_discord_batch(self, ctx: commands.Context, *, ids: str):
        await ctx.defer()
        id_list = [int(x) for x in ids.replace(',', ' ').split()[:100]]
        if not id_list:
            await ctx.send('Provide at least one Discord ID (max 100).')
            return
        session = getattr(self.bot, 'session', None) or aiohttp.ClientSession()
        close = getattr(self.bot, 'session', None) is None
        try:
            payload = {'ids': id_list}
            resp = await self._request('POST', '/discord/user', session, json=payload)
            if isinstance(resp, dict) and ('error' in resp):
                await ctx.send(f"Error: {resp['error']}")
                return
            await ctx.send(file=_make_file_from_json(resp, 'discord_users_batch.json'))
        finally:
            if close:
                await session.close()

async def setup(bot: commands.Bot):
    await bot.add_cog(Rotector(bot))
