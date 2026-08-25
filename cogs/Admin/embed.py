import os
import re
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from urllib.parse import urlsplit, urlunsplit


PRIMARY_DOMAINS = {
    "x.com": "fixupx.com",
    "twitter.com": "fixupx.com",
    "tiktok.com": "tnktok.com",
    "instagram.com": "axinstagram.com",
    "reddit.com": "vxreddit.com",
    "threads.net": "vxthreads.net",
}

BACKUP_DOMAINS = {
    "x.com": "twitterez.com",
    "twitter.com": "twitterez.com",
    "tiktok.com": "tiktokez.com",
    "instagram.com": "instagramez.com",
    "reddit.com": "redditez.com",
    "threads.net": "threadsez.net",
}

SUPPORTED_PLATFORMS = "X/Twitter, TikTok, Instagram, Reddit, Threads"

URL_PATTERN = re.compile(
    r"https?://(?:[a-z0-9-]+\.)*(?P<domain>(?:x|twitter)\.com|tiktok\.com|instagram\.com|reddit\.com|threads\.net)(?:/[^\s<>`]*)?",
    re.IGNORECASE,
)

TRAILING_PUNCTUATION = ".,;:!?)}]>\"'"

MAX_TRACKED_REPLIES = 5000


def _parse_guild_ids() -> frozenset:
    raw = os.getenv("Guilds", "")
    return frozenset(int(g.strip()) for g in raw.split(",") if g.strip().isdigit())


def _swap_domain(url: str, new_domain: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme or "https", new_domain, parts.path, "", ""))


class EmbedFix(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.allowed_guilds = _parse_guild_ids()
        self._replies = {}
        if not self.allowed_guilds:
            print("EmbedFix: Guilds is not set in .env — beta auto-fix is disabled everywhere.")

    async def _resolve(self, session: aiohttp.ClientSession, base_domain: str, url: str) -> str:
        primary = _swap_domain(url, PRIMARY_DOMAINS[base_domain])
        backup_base = BACKUP_DOMAINS.get(base_domain)
        if backup_base is None:
            return primary
        backup = _swap_domain(url, backup_base)

        for candidate in (primary, backup):
            try:
                async with session.get(candidate, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                    if resp.status < 500:
                        return candidate
            except (aiohttp.ClientError, TimeoutError):
                continue
        return primary

    @staticmethod
    def _is_wrapped(content: str, match: re.Match) -> bool:
        start, end = match.span()
        before = content[start - 1] if start > 0 else ""
        after = content[end] if end < len(content) else ""
        return before == "<" and after == ">"

    def _track_reply(self, original_id: int, channel_id: int, reply_id: int):
        self._replies[original_id] = (channel_id, reply_id)
        while len(self._replies) > MAX_TRACKED_REPLIES:
            del self._replies[next(iter(self._replies))]

    async def _delete_tracked_reply(self, original_id: int):
        entry = self._replies.pop(original_id, None)
        if entry is None:
            return
        channel = self.bot.get_channel(entry[0])
        if channel is None:
            return
        try:
            await channel.get_partial_message(entry[1]).delete()
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        if message.guild.id not in self.allowed_guilds:
            return

        prefixes = await self.bot.get_prefix(message)
        if isinstance(prefixes, str):
            prefixes = [prefixes]
        if any(message.content.startswith(p) for p in prefixes):
            return

        if message.flags.suppress_embeds:
            return

        found = []
        seen = set()
        for match in URL_PATTERN.finditer(message.content):
            if self._is_wrapped(message.content, match):
                continue
            url = match.group(0).rstrip(TRAILING_PUNCTUATION)
            domain = match.group("domain").lower()
            key = url.lower()
            if key in seen:
                continue
            seen.add(key)
            found.append((url, domain))

        if not found:
            return

        session = getattr(self.bot, "session", None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            fixed_links = []
            for url, domain in found:
                fixed_links.append(await self._resolve(session, domain, url))
            try:
                reply = await message.reply(content="\n".join(fixed_links), mention_author=False)
            except discord.HTTPException:
                return
            self._track_reply(message.id, message.channel.id, reply.id)
        finally:
            if close_session and session and not session.closed:
                await session.close()

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if after.author.bot or after.guild is None:
            return
        if after.guild.id not in self.allowed_guilds:
            return
        await self._delete_tracked_reply(after.id)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild is None or message.guild.id not in self.allowed_guilds:
            return
        await self._delete_tracked_reply(message.id)

    @commands.hybrid_command(name="embed", description="Fix a social media link so it embeds properly in Discord.")
    @app_commands.describe(link=f"Link to fix ({SUPPORTED_PLATFORMS})")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def embed(self, ctx: commands.Context, link: str):
        link = link.strip()
        match = URL_PATTERN.search(link)
        if match is None:
            await ctx.send(f"Unsupported link. Supported platforms: {SUPPORTED_PLATFORMS}.")
            return

        domain = match.group("domain").lower()
        session = getattr(self.bot, "session", None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            url = link[match.start():match.end()].rstrip(TRAILING_PUNCTUATION)
            fixed = await self._resolve(session, domain, url)
            await ctx.send(fixed)
        finally:
            if close_session and session and not session.closed:
                await session.close()


async def setup(bot: commands.Bot):
    await bot.add_cog(EmbedFix(bot))
