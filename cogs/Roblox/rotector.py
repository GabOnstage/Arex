import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import io
import json
import os
from typing import Optional, Union

ROTECTOR_BASE = "https://roscoe.rotector.com/v1/lookup"
ROTECTOR_TOS_URL = "https://rotector.com/terms"

FLAG_TYPES = {
    0: ("Unflagged", discord.Color.green()),
    1: ("Flagged", discord.Color.orange()),
    2: ("Confirmed", discord.Color.red()),
    3: ("Queued", discord.Color.blurple()),
    4: ("Provisional Flag", discord.Color.yellow()),
    5: ("Mixed", discord.Color.gold()),
    6: ("Past Offender", discord.Color.purple()),
    8: ("Redacted", discord.Color.dark_grey()),
}

CONTENT_CATEGORIES = {
    1: "CSAM",
    2: "Sexual",
    3: "Kink",
    4: "Raceplay",
    5: "Condo",
    6: "Other",
}


def _get_auth_headers() -> dict:
    key = os.getenv('ROTECTOR_API_KEY')
    if not key:
        return {}
    return {"Authorization": f"Bearer {key}"}


def _make_file_from_json(data, name: str = "result.json") -> discord.File:
    s = io.StringIO()
    json.dump(data, s, indent=2)
    s.seek(0)
    return discord.File(fp=io.BytesIO(s.getvalue().encode('utf-8')), filename=name)


def _flag_embed(kind: str, target_id: Union[int, str], data: dict) -> discord.Embed:
    flag_type = data.get('flagType', 0)
    name, color = FLAG_TYPES.get(flag_type, (f"Unknown ({flag_type})", discord.Color.dark_grey()))
    embed = discord.Embed(
        title=f"Rotector — {kind} {target_id}: {name}",
        color=color,
        url="https://rotector.com"
    )

    category = data.get('category')
    if category in CONTENT_CATEGORIES:
        embed.add_field(name="Category", value=CONTENT_CATEGORIES[category], inline=True)

    confidence = data.get('confidence')
    if isinstance(confidence, (int, float)):
        embed.add_field(name="Confidence", value=f"{confidence:.0%}", inline=True)

    reasons = data.get('reasons') or {}
    if isinstance(reasons, dict) and reasons:
        lines = []
        for reason_key, info in list(reasons.items())[:5]:
            message = info.get('message', '') if isinstance(info, dict) else str(info)
            lines.append(f"**{reason_key}**: {message[:300]}")
        embed.add_field(name="Reasons", value="\n".join(lines)[:1024], inline=False)

    reviewer = data.get('reviewer')
    if isinstance(reviewer, dict) and reviewer.get('username'):
        embed.add_field(name="Reviewed By", value=str(reviewer['username']), inline=True)

    last_updated = data.get('lastUpdated')
    if isinstance(last_updated, int):
        embed.add_field(name="Last Updated", value=f"<t:{last_updated}:R>", inline=True)

    # Per Rotector ToS: Unflagged must not be presented as "Safe".
    embed.set_footer(text="Data by rotector.com • Unflagged ≠ Safe • Do not cache >24h")
    return embed


class Rotector(commands.Cog):
    """Commands to interact with the Rotector API (roscoe.rotector.com).

    Note: Do not cache responses for longer than 24 hours (API terms).
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
                    retry = r.headers.get('Retry-After') or 'a moment'
                    return {'error': f'Rate limited. Retry after {retry}s.'}
                text = await r.text()
                try:
                    body = json.loads(text)
                except Exception:
                    body = text
                if r.status != 200:
                    msg = body.get('message') if isinstance(body, dict) else None
                    return {'error': f'HTTP {r.status}: {msg or text[:200]}'}
                return body
        except Exception as e:
            return {'error': str(e)}

    async def _unwrap(self, resp):
        """Extract the data payload from the {"success": ..., "data": ...} envelope."""
        if isinstance(resp, dict):
            if 'error' in resp:
                return None, str(resp['error'])
            if resp.get('success') is True and 'data' in resp:
                return resp['data'], None
            return resp, None
        # Bare values (e.g. plaintext endpoints return a plain flag number).
        return resp, None

    async def _send_lookup(self, ctx: commands.Context, kind: str, target_id, path: str, session: aiohttp.ClientSession):
        resp = await self._request('GET', path, session)
        data, err = await self._unwrap(resp)
        if err:
            await ctx.send(f"Error: {err}")
            return
        out = json.dumps(data, indent=2)
        if len(out) > 950:
            await ctx.send(file=_make_file_from_json(data, f'{kind}_{target_id}.json'))
        else:
            label = 'Roblox User' if kind == 'roblox_user' else 'Roblox Group'
            await ctx.send(embed=_flag_embed(label, target_id, data if isinstance(data, dict) else {}))

    async def _parse_ids(self, ctx: commands.Context, ids: str, max_ids: int, label: str) -> Optional[list]:
        raw = [x for x in ids.replace(',', ' ').split() if x.strip()]
        id_list = []
        for x in raw[:max_ids]:
            if not x.isdigit():
                await ctx.send(f"Invalid ID: `{x}`. IDs must be numeric.")
                return None
            id_list.append(x)
        if not id_list:
            await ctx.send(f'Provide at least one {label} ID (max {max_ids}).')
            return None
        if len(raw) > max_ids:
            await ctx.send(f"⚠️ Truncated to the first {max_ids} IDs.")
        return id_list

    # --- Roblox User endpoints ---
    @commands.hybrid_command(name='rotector_user', description='Get Rotector flag info for a Roblox user by ID')
    async def rotector_user(self, ctx: commands.Context, user_id: int):
        await ctx.defer()
        session = getattr(self.bot, 'session', None) or aiohttp.ClientSession()
        close = getattr(self.bot, 'session', None) is None
        try:
            await self._send_lookup(ctx, 'roblox_user', user_id, f'/roblox/user/{user_id}', session)
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
            flag, err = await self._unwrap(resp)
            if err:
                await ctx.send(f"Error: {err}")
                return
            name, _ = FLAG_TYPES.get(flag, (str(flag), None))
            await ctx.send(f'Roblox user {user_id} status: **{name}** ({flag})')
        finally:
            if close:
                await session.close()

    @commands.hybrid_command(name='rotector_user_batch', description='Batch lookup Roblox users (comma/space separated IDs, max 100)')
    async def rotector_user_batch(self, ctx: commands.Context, *, ids: str):
        await ctx.defer()
        id_list = await self._parse_ids(ctx, ids, 100, 'user')
        if not id_list:
            return
        session = getattr(self.bot, 'session', None) or aiohttp.ClientSession()
        close = getattr(self.bot, 'session', None) is None
        try:
            payload = {'ids': [int(x) for x in id_list]}
            resp = await self._request('POST', '/roblox/user', session, json=payload)
            data, err = await self._unwrap(resp)
            if err:
                await ctx.send(f"Error: {err}")
                return
            await ctx.send(file=_make_file_from_json(data, 'roblox_users_batch.json'))
        finally:
            if close:
                await session.close()

    @commands.hybrid_command(name='rotector_user_status_batch', description='Batch user flag statuses, status only (max 100)')
    async def rotector_user_status_batch(self, ctx: commands.Context, *, ids: str):
        await ctx.defer()
        id_list = await self._parse_ids(ctx, ids, 100, 'user')
        if not id_list:
            return
        session = getattr(self.bot, 'session', None) or aiohttp.ClientSession()
        close = getattr(self.bot, 'session', None) is None
        try:
            payload = {'ids': [int(x) for x in id_list]}
            resp = await self._request('POST', '/roblox/user/status', session, json=payload)
            data, err = await self._unwrap(resp)
            if err:
                await ctx.send(f"Error: {err}")
                return
            await ctx.send(file=_make_file_from_json(data, 'roblox_users_status_batch.json'))
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
            data, err = await self._unwrap(resp)
            if err:
                await ctx.send(f"Error: {err}")
                return
            await ctx.send(file=_make_file_from_json(data, f'roblox_user_{user_id}_discord.json'))
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
            await self._send_lookup(ctx, 'roblox_group', group_id, f'/roblox/group/{group_id}', session)
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
            flag, err = await self._unwrap(resp)
            if err:
                await ctx.send(f"Error: {err}")
                return
            name, _ = FLAG_TYPES.get(flag, (str(flag), None))
            await ctx.send(f'Roblox group {group_id} status: **{name}** ({flag})')
        finally:
            if close:
                await session.close()

    @commands.hybrid_command(name='rotector_group_batch', description='Batch lookup Roblox groups (comma/space separated IDs, max 100)')
    async def rotector_group_batch(self, ctx: commands.Context, *, ids: str):
        await ctx.defer()
        id_list = await self._parse_ids(ctx, ids, 100, 'group')
        if not id_list:
            return
        session = getattr(self.bot, 'session', None) or aiohttp.ClientSession()
        close = getattr(self.bot, 'session', None) is None
        try:
            payload = {'ids': [int(x) for x in id_list]}
            resp = await self._request('POST', '/roblox/group', session, json=payload)
            data, err = await self._unwrap(resp)
            if err:
                await ctx.send(f"Error: {err}")
                return
            await ctx.send(file=_make_file_from_json(data, 'roblox_groups_batch.json'))
        finally:
            if close:
                await session.close()

    @commands.hybrid_command(name='rotector_group_tracked', description='Get tracked (flagged) users in a Roblox group')
    @app_commands.describe(group_id="Roblox group ID", limit="Results per page (1-100)")
    async def rotector_group_tracked(self, ctx: commands.Context, group_id: int, limit: int = 20):
        await ctx.defer()
        limit = max(1, min(100, limit))
        session = getattr(self.bot, 'session', None) or aiohttp.ClientSession()
        close = getattr(self.bot, 'session', None) is None
        try:
            resp = await self._request('GET', f'/roblox/group/{group_id}/tracked-users?limit={limit}', session)
            data, err = await self._unwrap(resp)
            if err:
                await ctx.send(f"Error: {err}")
                return
            await ctx.send(file=_make_file_from_json(data, f'group_{group_id}_tracked_users.json'))
        finally:
            if close:
                await session.close()

    # --- Discord User endpoints ---
    @commands.hybrid_command(name='rotector_discord', description='Get Rotector info for a Discord user by ID')
    async def rotector_discord(self, ctx: commands.Context, discord_id: str):
        await ctx.defer()
        discord_id = discord_id.strip()
        if not discord_id.isdigit():
            await ctx.send("Provide a valid numeric Discord user ID.")
            return
        session = getattr(self.bot, 'session', None) or aiohttp.ClientSession()
        close = getattr(self.bot, 'session', None) is None
        try:
            resp = await self._request('GET', f'/discord/user/{discord_id}', session)
            data, err = await self._unwrap(resp)
            if err:
                await ctx.send(f"Error: {err}")
                return
            await ctx.send(file=_make_file_from_json(data, f'discord_user_{discord_id}.json'))
        finally:
            if close:
                await session.close()

    @commands.hybrid_command(name='rotector_discord_batch', description='Batch lookup Discord users (IDs comma/space separated, max 100)')
    async def rotector_discord_batch(self, ctx: commands.Context, *, ids: str):
        await ctx.defer()
        id_list = await self._parse_ids(ctx, ids, 100, 'Discord')
        if not id_list:
            return
        session = getattr(self.bot, 'session', None) or aiohttp.ClientSession()
        close = getattr(self.bot, 'session', None) is None
        try:
            payload = {'ids': id_list}  # Discord batch expects string IDs
            resp = await self._request('POST', '/discord/user', session, json=payload)
            data, err = await self._unwrap(resp)
            if err:
                await ctx.send(f"Error: {err}")
                return
            await ctx.send(file=_make_file_from_json(data, 'discord_users_batch.json'))
        finally:
            if close:
                await session.close()


async def setup(bot: commands.Bot):
    await bot.add_cog(Rotector(bot))
