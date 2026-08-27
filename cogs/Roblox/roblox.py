import discord
from discord.ext import commands
from discord import app_commands
from dateutil import parser
import aiohttp
import io
import json
import os
from datetime import datetime, timezone
from time import monotonic
from typing import List, Optional, Union

SEARCH_CACHE_TTL = 300
SEARCH_CACHE_MAX = 200
_search_cache: dict = {}

ROTECTOR_BASE = "https://roscoe.rotector.com/v1/lookup"

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


def _get_rotector_auth() -> dict:
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

    embed.set_footer(text="Data by rotector.com • Unflagged ≠ Safe • Do not cache >24h")
    return embed


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


class Roblox(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._search_inflight = set()

    async def _get_session(self):
        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True
        return session, close_session

    async def find_roblox_id(self, username: str) -> Optional[int]:
        session, close_session = await self._get_session()
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

    async def _rotector_request(self, method: str, path: str, session: aiohttp.ClientSession, **kwargs):
        url = f"{ROTECTOR_BASE}{path}"
        headers = _get_rotector_auth()
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

    async def _rotector_unwrap(self, resp):
        if isinstance(resp, dict):
            if 'error' in resp:
                return None, str(resp['error'])
            if resp.get('success') is True and 'data' in resp:
                return resp['data'], None
            return resp, None
        return resp, None

    async def _rotector_send_lookup(self, ctx: commands.Context, kind: str, target_id, path: str, session: aiohttp.ClientSession):
        resp = await self._rotector_request('GET', path, session)
        data, err = await self._rotector_unwrap(resp)
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

    # ════════════════════════════════════════════════════════════════════════
    # /roblox parent group
    # ════════════════════════════════════════════════════════════════════════
    @commands.hybrid_group(name="roblox", description="Roblox-related commands.")
    async def roblox_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("Usage: `/roblox user`, `/roblox badge`, `/roblox rotector-*`")

    # ── /roblox user ─────────────────────────────────────────────────────
    @roblox_group.command(name="user", description="Retrieve detailed information about a Roblox user.")
    @app_commands.describe(roblox_user="Enter a Roblox username or User ID")
    async def roblox_user_cmd(self, ctx: commands.Context, roblox_user: str):
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

        session, close_session = await self._get_session()
        try:
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

    @roblox_user_cmd.autocomplete("roblox_user")
    async def roblox_user_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        query = current.strip().lower()
        if len(query) < 3 or query.isdigit():
            return []

        now = monotonic()
        cached = _search_cache.get(query)
        if cached is not None:
            ts, choices = cached
            if now - ts <= SEARCH_CACHE_TTL:
                return [c for c in choices if query in c.value.lower()][:25]
            del _search_cache[query]

        if query in self._search_inflight:
            return []
        self._search_inflight.add(query)

        session, close_session = await self._get_session()
        try:
            async with session.get(
                "https://users.roblox.com/v1/users/search",
                params={"keyword": query, "limit": 10},
                timeout=aiohttp.ClientTimeout(total=2.5),
            ) as resp:
                if resp.status != 200:
                    return []
                users = (await resp.json()).get("data", [])

            choices = []
            for user in users[:10]:
                name = user.get("name")
                if not name:
                    continue
                display = user.get("displayName") or name
                label = f"{name} — {display}"[:100]
                choices.append(app_commands.Choice(name=label, value=name))

            while len(_search_cache) >= SEARCH_CACHE_MAX:
                del _search_cache[next(iter(_search_cache))]
            _search_cache[query] = (now, choices)
            return choices
        except Exception:
            return []
        finally:
            self._search_inflight.discard(query)
            if close_session and session and not session.closed:
                await session.close()

    # ── /roblox badge ────────────────────────────────────────────────────
    @roblox_group.command(name="badge", description="Fetch badges owned by a Roblox user.")
    @app_commands.describe(user="Roblox username or numerical User ID")
    async def roblox_badge_cmd(self, ctx: commands.Context, user: str):
        await ctx.defer()
        target = user.strip()

        if target.isdigit():
            userid = int(target)
        else:
            userid = await self.find_roblox_id(target)

        if userid is None:
            await ctx.send(f"Invalid username or ID `{user}`.", ephemeral=True)
            return

        session, close_session = await self._get_session()
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

    # ── /roblox rotector-user ────────────────────────────────────────────
    @roblox_group.command(name="rotector-user", description="Get Rotector flag info for a Roblox user by ID")
    async def rotector_user_info(self, ctx: commands.Context, user_id: int):
        await ctx.defer()
        session, close_session = await self._get_session()
        try:
            await self._rotector_send_lookup(ctx, 'roblox_user', user_id, f'/roblox/user/{user_id}', session)
        finally:
            if close_session:
                await session.close()

    @roblox_group.command(name="rotector-user-plain", description="Get only flag status for Roblox user (plaintext)")
    async def rotector_user_plain(self, ctx: commands.Context, user_id: int):
        await ctx.defer()
        session, close_session = await self._get_session()
        try:
            resp = await self._rotector_request('GET', f'/roblox/user/{user_id}/plaintext', session)
            flag, err = await self._rotector_unwrap(resp)
            if err:
                await ctx.send(f"Error: {err}")
                return
            name, _ = FLAG_TYPES.get(flag, (str(flag), None))
            await ctx.send(f'Roblox user {user_id} status: **{name}** ({flag})')
        finally:
            if close_session:
                await session.close()

    @roblox_group.command(name="rotector-user-batch", description="Batch lookup Roblox users (comma/space separated IDs, max 100)")
    async def rotector_user_batch(self, ctx: commands.Context, *, ids: str):
        await ctx.defer()
        id_list = await self._parse_ids(ctx, ids, 100, 'user')
        if not id_list:
            return
        session, close_session = await self._get_session()
        try:
            payload = {'ids': [int(x) for x in id_list]}
            resp = await self._rotector_request('POST', '/roblox/user', session, json=payload)
            data, err = await self._rotector_unwrap(resp)
            if err:
                await ctx.send(f"Error: {err}")
                return
            await ctx.send(file=_make_file_from_json(data, 'roblox_users_batch.json'))
        finally:
            if close_session:
                await session.close()

    @roblox_group.command(name="rotector-user-status-batch", description="Batch user flag statuses, status only (max 100)")
    async def rotector_user_status_batch(self, ctx: commands.Context, *, ids: str):
        await ctx.defer()
        id_list = await self._parse_ids(ctx, ids, 100, 'user')
        if not id_list:
            return
        session, close_session = await self._get_session()
        try:
            payload = {'ids': [int(x) for x in id_list]}
            resp = await self._rotector_request('POST', '/roblox/user/status', session, json=payload)
            data, err = await self._rotector_unwrap(resp)
            if err:
                await ctx.send(f"Error: {err}")
                return
            await ctx.send(file=_make_file_from_json(data, 'roblox_users_status_batch.json'))
        finally:
            if close_session:
                await session.close()

    @roblox_group.command(name="rotector-user-discord", description="Get Discord accounts linked to a Roblox user")
    async def rotector_user_discord(self, ctx: commands.Context, user_id: int):
        await ctx.defer()
        session, close_session = await self._get_session()
        try:
            resp = await self._rotector_request('GET', f'/roblox/user/{user_id}/discord', session)
            data, err = await self._rotector_unwrap(resp)
            if err:
                await ctx.send(f"Error: {err}")
                return
            await ctx.send(file=_make_file_from_json(data, f'roblox_user_{user_id}_discord.json'))
        finally:
            if close_session:
                await session.close()

    # ── /roblox rotector-group ───────────────────────────────────────────
    @roblox_group.command(name="rotector-group", description="Get Rotector flag info for a Roblox group by ID")
    async def rotector_group_info(self, ctx: commands.Context, group_id: int):
        await ctx.defer()
        session, close_session = await self._get_session()
        try:
            await self._rotector_send_lookup(ctx, 'roblox_group', group_id, f'/roblox/group/{group_id}', session)
        finally:
            if close_session:
                await session.close()

    @roblox_group.command(name="rotector-group-plain", description="Get only flag status for Roblox group (plaintext)")
    async def rotector_group_plain(self, ctx: commands.Context, group_id: int):
        await ctx.defer()
        session, close_session = await self._get_session()
        try:
            resp = await self._rotector_request('GET', f'/roblox/group/{group_id}/plaintext', session)
            flag, err = await self._rotector_unwrap(resp)
            if err:
                await ctx.send(f"Error: {err}")
                return
            name, _ = FLAG_TYPES.get(flag, (str(flag), None))
            await ctx.send(f'Roblox group {group_id} status: **{name}** ({flag})')
        finally:
            if close_session:
                await session.close()

    @roblox_group.command(name="rotector-group-batch", description="Batch lookup Roblox groups (comma/space separated IDs, max 100)")
    async def rotector_group_batch(self, ctx: commands.Context, *, ids: str):
        await ctx.defer()
        id_list = await self._parse_ids(ctx, ids, 100, 'group')
        if not id_list:
            return
        session, close_session = await self._get_session()
        try:
            payload = {'ids': [int(x) for x in id_list]}
            resp = await self._rotector_request('POST', '/roblox/group', session, json=payload)
            data, err = await self._rotector_unwrap(resp)
            if err:
                await ctx.send(f"Error: {err}")
                return
            await ctx.send(file=_make_file_from_json(data, 'roblox_groups_batch.json'))
        finally:
            if close_session:
                await session.close()

    @roblox_group.command(name="rotector-group-tracked", description="Get tracked (flagged) users in a Roblox group")
    @app_commands.describe(group_id="Roblox group ID", limit="Results per page (1-100)")
    async def rotector_group_tracked(self, ctx: commands.Context, group_id: int, limit: int = 20):
        await ctx.defer()
        limit = max(1, min(100, limit))
        session, close_session = await self._get_session()
        try:
            resp = await self._rotector_request('GET', f'/roblox/group/{group_id}/tracked-users?limit={limit}', session)
            data, err = await self._rotector_unwrap(resp)
            if err:
                await ctx.send(f"Error: {err}")
                return
            await ctx.send(file=_make_file_from_json(data, f'group_{group_id}_tracked_users.json'))
        finally:
            if close_session:
                await session.close()

    # ── /roblox rotector-discord ─────────────────────────────────────────
    @roblox_group.command(name="rotector-discord", description="Get Rotector info for a Discord user by ID")
    async def rotector_discord_info(self, ctx: commands.Context, discord_id: str):
        await ctx.defer()
        discord_id = discord_id.strip()
        if not discord_id.isdigit():
            await ctx.send("Provide a valid numeric Discord user ID.")
            return
        session, close_session = await self._get_session()
        try:
            resp = await self._rotector_request('GET', f'/discord/user/{discord_id}', session)
            data, err = await self._rotector_unwrap(resp)
            if err:
                await ctx.send(f"Error: {err}")
                return
            await ctx.send(file=_make_file_from_json(data, f'discord_user_{discord_id}.json'))
        finally:
            if close_session:
                await session.close()

    @roblox_group.command(name="rotector-discord-batch", description="Batch lookup Discord users (IDs comma/space separated, max 100)")
    async def rotector_discord_batch(self, ctx: commands.Context, *, ids: str):
        await ctx.defer()
        id_list = await self._parse_ids(ctx, ids, 100, 'Discord')
        if not id_list:
            return
        session, close_session = await self._get_session()
        try:
            payload = {'ids': id_list}
            resp = await self._rotector_request('POST', '/discord/user', session, json=payload)
            data, err = await self._rotector_unwrap(resp)
            if err:
                await ctx.send(f"Error: {err}")
                return
            await ctx.send(file=_make_file_from_json(data, 'discord_users_batch.json'))
        finally:
            if close_session:
                await session.close()


async def setup(bot: commands.Bot):
    await bot.add_cog(Roblox(bot))
