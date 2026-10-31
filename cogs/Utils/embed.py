import os
import re
import asyncio
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from urllib.parse import urlsplit, urlunsplit
from datetime import datetime, timezone


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

FX_API = "https://api.fxtwitter.com/2/status/{id}"

X_URL_PATTERN = re.compile(
    r"https?://(?:[a-z0-9-]+\.)*(?:x|twitter|fixupx|fxtwitter|vxtwitter|twitterez|xfixup)\.com(?:/[^\s<>`]*)?",
    re.IGNORECASE,
)

OTHER_URL_PATTERN = re.compile(
    r"https?://(?:[a-z0-9-]+\.)*(?P<domain>tiktok\.com|instagram\.com|reddit\.com|threads\.net)(?:/[^\s<>`]*)?",
    re.IGNORECASE,
)

STATUS_PATH_PATTERN = re.compile(r"/(?:status|statuses)/(\d+)", re.IGNORECASE)

TRAILING_PUNCTUATION = ".,;:!?)}]>\"'"

MAX_TRACKED_REPLIES = 5000

LANGUAGES = [
    ("English", "en"),
    ("Spanish", "es"),
    ("French", "fr"),
    ("German", "de"),
    ("Portuguese", "pt"),
    ("Italian", "it"),
    ("Japanese", "ja"),
    ("Korean", "ko"),
    ("Chinese (Simplified)", "zh-cn"),
    ("Chinese (Traditional)", "zh-tw"),
    ("Russian", "ru"),
    ("Arabic", "ar"),
    ("Hindi", "hi"),
    ("Turkish", "tr"),
    ("Indonesian", "id"),
    ("Dutch", "nl"),
    ("Polish", "pl"),
    ("Thai", "th"),
    ("Vietnamese", "vi"),
    ("Ukrainian", "uk"),
    ("Swedish", "sv"),
]

LANGUAGE_NAMES = {code: label for label, code in LANGUAGES}


def _parse_guild_ids() -> frozenset:
    raw = os.getenv("Guilds", "")
    return frozenset(int(g.strip()) for g in raw.split(",") if g.strip().isdigit())


def _swap_domain(url: str, new_domain: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme or "https", new_domain, parts.path, "", ""))


def _format_count(value) -> str:
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return "0"
    if number < 1000:
        return str(number)
    if number < 1_000_000:
        text = f"{number / 1000:.1f}".rstrip("0").rstrip(".")
        return f"{text}K"
    text = f"{number / 1_000_000:.1f}".rstrip("0").rstrip(".")
    return f"{text}M"


def _truncate(text: str, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


class LanguageSelect(discord.ui.Select):
    def __init__(self, view: "TweetView", selected: str = None):
        options = [
            discord.SelectOption(
                label=label,
                value=code,
                default=(selected == code),
            )
            for label, code in LANGUAGES
        ]
        options.append(
            discord.SelectOption(
                label="Original post",
                value="original",
                default=(selected == "original"),
            )
        )
        super().__init__(
            placeholder="🌐 Translate post…",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="fx:translate",
            row=0,
        )
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        await self.view_ref.handle_translate(interaction, self.values[0])


class TweetView(discord.ui.View):
    def __init__(
        self,
        cog: "EmbedFix",
        base_status: dict,
        tweet_id: str,
        post_url: str,
        author_id: int,
        original_message_id: int = None,
        color: int = None,
        selected: str = None,
    ):
        super().__init__(timeout=None)
        self.cog = cog
        self.base_status = base_status
        self.tweet_id = tweet_id
        self.post_url = post_url
        self.author_id = author_id
        self.original_message_id = original_message_id
        self.color = color if color is not None else discord.Color.random().value

        self.add_item(LanguageSelect(self, selected))
        self.add_item(
            discord.ui.Button(
                label="Go to post",
                style=discord.ButtonStyle.link,
                url=post_url,
                emoji="🔗",
                row=1,
            )
        )

        delete_button = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            emoji="🗑️",
            row=1,
            custom_id="fx:delete",
        )
        delete_button.callback = self.handle_delete
        self.add_item(delete_button)

    def _rebuild(self, selected: str = None) -> "TweetView":
        return TweetView(
            self.cog,
            self.base_status,
            self.tweet_id,
            self.post_url,
            self.author_id,
            self.original_message_id,
            self.color,
            selected,
        )

    async def handle_translate(self, interaction: discord.Interaction, language: str):
        await interaction.response.defer()

        if language == "original":
            embed = self.cog._build_embed(self.base_status, color=self.color)
            try:
                await interaction.message.edit(embed=embed, view=self._rebuild("original"))
            except discord.HTTPException:
                pass
            return

        post_language = (self.base_status.get("lang") or "").lower()
        if language == post_language:
            await interaction.followup.send(
                f"This post is already in {LANGUAGE_NAMES.get(language, language)}.",
                ephemeral=True,
            )
            return

        status = await self.cog._fetch_status(self.tweet_id, lang=language)
        translation = (status or {}).get("translation") or {}
        if not translation.get("text"):
            await interaction.followup.send(
                "Translation isn't available for this post.",
                ephemeral=True,
            )
            return

        embed = self.cog._build_embed(status, color=self.color)
        try:
            await interaction.message.edit(embed=embed, view=self._rebuild(language))
        except discord.HTTPException:
            pass

    async def handle_delete(self, interaction: discord.Interaction):
        permissions = getattr(interaction.user, "guild_permissions", None)
        is_mod = bool(permissions and (permissions.manage_messages or permissions.administrator))
        if interaction.user.id != self.author_id and not is_mod:
            await interaction.response.send_message(
                "Only the original author or moderators can delete this.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        if self.original_message_id:
            try:
                original = await interaction.channel.fetch_message(self.original_message_id)
                await self.cog._unsuppress(original)
            except (discord.HTTPException, AttributeError):
                pass
            self.cog._replies.pop(self.original_message_id, None)

        try:
            await interaction.message.delete()
        except discord.HTTPException:
            try:
                await interaction.followup.send("I couldn't delete the embed.", ephemeral=True)
            except discord.HTTPException:
                pass


class EmbedFix(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.allowed_guilds = _parse_guild_ids()
        self._replies = {}
        self._warned_manage_messages = False
        if not self.allowed_guilds:
            print("EmbedFix: Guilds is not set in .env — beta auto-fix is disabled everywhere.")

    def _bot_permissions(self, channel, guild):
        if guild is None:
            return None
        me = guild.me or guild.get_member(self.bot.user.id)
        if me is None:
            return None
        return channel.permissions_for(me)

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
            except (aiohttp.ClientError, asyncio.TimeoutError):
                continue
        return primary

    async def _fetch_status(self, tweet_id: str, lang: str = None):
        session = getattr(self.bot, "session", None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        params = {"lang": lang} if lang else None
        data = None
        try:
            async with session.get(
                FX_API.format(id=tweet_id),
                params=params,
                timeout=aiohttp.ClientTimeout(total=6),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            data = None
        finally:
            if close_session and session and not session.closed:
                await session.close()

        if not isinstance(data, dict) or data.get("code") != 200:
            return None
        status = data.get("status")
        if not isinstance(status, dict) or status.get("type") != "status":
            return None
        return status

    @staticmethod
    def _is_wrapped(content: str, match: re.Match) -> bool:
        start, end = match.span()
        before = content[start - 1] if start > 0 else ""
        after = content[end] if end < len(content) else ""
        return before == "<" and after == ">"

    def _find_x_link(self, content: str, allow_wrapped: bool = False):
        for match in X_URL_PATTERN.finditer(content):
            if not allow_wrapped and self._is_wrapped(content, match):
                continue
            url = match.group(0).rstrip(TRAILING_PUNCTUATION)
            status_match = STATUS_PATH_PATTERN.search(urlsplit(url).path)
            if status_match:
                return url, status_match.group(1)
        return None

    def _find_other_links(self, content: str):
        found = []
        seen = set()
        for match in OTHER_URL_PATTERN.finditer(content):
            if self._is_wrapped(content, match):
                continue
            url = match.group(0).rstrip(TRAILING_PUNCTUATION)
            domain = match.group("domain").lower()
            key = url.lower()
            if key in seen:
                continue
            seen.add(key)
            found.append((url, domain))
        return found

    @staticmethod
    def _canonical_post_url(status: dict) -> str:
        author = status.get("author") or {}
        screen_name = author.get("screen_name")
        tweet_id = status.get("id")
        if screen_name and tweet_id:
            return f"https://x.com/{screen_name}/status/{tweet_id}"
        parts = urlsplit(status.get("url") or "")
        if parts.path:
            return urlunsplit(("https", "x.com", parts.path, "", ""))
        return f"https://x.com/i/status/{tweet_id}"

    @staticmethod
    def _profile_url(author: dict):
        screen_name = author.get("screen_name")
        if screen_name:
            return f"https://x.com/{screen_name}"
        parts = urlsplit(author.get("url") or "")
        if parts.path:
            return urlunsplit(("https", "x.com", parts.path, "", ""))
        return None

    @staticmethod
    def _quote_block(quote: dict) -> str:
        if not isinstance(quote, dict):
            return ""
        if quote.get("type") == "tombstone":
            return "> *Quoted post unavailable*"

        author = quote.get("author") or {}
        name = author.get("name") or author.get("screen_name") or "Unknown"
        screen_name = author.get("screen_name")
        heading = f"**{discord.utils.escape_markdown(name)}"
        if screen_name:
            heading += f" (@{discord.utils.escape_markdown(screen_name)})"
        heading += "**"

        text = (quote.get("text") or "").strip()
        text = _truncate(text, 600)
        lines = [f"> {heading}"]
        if text:
            lines.extend(f"> {line}" for line in text.splitlines())
        return "\n".join(lines)

    @staticmethod
    def _poll_field(poll: dict):
        if not isinstance(poll, dict):
            return None, None
        choices = poll.get("choices") or []
        if not choices:
            return None, None

        lines = []
        for choice in choices[:10]:
            label = choice.get("label") or "Option"
            percentage = choice.get("percentage", 0)
            count = choice.get("count", 0)
            try:
                bar_length = max(1, round(float(percentage) / 100 * 12))
            except (TypeError, ValueError):
                bar_length = 0
            bar = "█" * bar_length
            lines.append(f"{label}\n{bar} **{percentage}%** ({count} votes)")

        total = poll.get("total_votes", 0)
        time_left = poll.get("time_left_en")
        lines.append(f"*{time_left} left · {total} votes*" if time_left else f"*{total} votes*")
        return "Poll", _truncate("\n".join(lines), 1024)

    @staticmethod
    def _media_url(media: dict):
        if not isinstance(media, dict):
            return None

        mosaic = media.get("mosaic") or {}
        photos = media.get("photos") or []
        videos = media.get("videos") or []
        external = media.get("external") or {}

        if len(photos) > 1:
            formats = mosaic.get("formats") or {}
            if formats.get("jpeg"):
                return formats["jpeg"]
            if mosaic.get("url"):
                return mosaic["url"]

        if photos:
            return photos[0].get("url")
        if videos:
            return videos[0].get("thumbnail_url")
        if external.get("thumbnail_url"):
            return external["thumbnail_url"]
        return None

    def _build_embed(self, status: dict, color: int = None) -> discord.Embed:
        author = status.get("author") or {}
        screen_name = author.get("screen_name") or "i"
        name = author.get("name") or screen_name

        display_name = f"{discord.utils.escape_markdown(name)} (@{discord.utils.escape_markdown(screen_name)})"
        if (author.get("verification") or {}).get("verified"):
            display_name = f"{display_name} ✔️"
        display_name = _truncate(display_name, 256)

        embed = discord.Embed(color=color if color is not None else discord.Color.random())
        embed.set_author(
            name=display_name,
            url=self._profile_url(author),
            icon_url=author.get("avatar_url"),
        )
        embed.url = self._canonical_post_url(status)

        text = (status.get("text") or "").strip()
        translation = status.get("translation") or {}
        translated = (translation.get("text") or "").strip()

        if translated:
            source = translation.get("source_lang_en") or translation.get("source_lang") or "another language"
            body = f"📑 **Translated from {source}**\n\n{translated}"
            if text:
                body += "\n\n> **Original**\n" + "\n".join(f"> {line}" for line in text.splitlines())
        else:
            body = text

        quote = status.get("quote")
        if quote:
            quote_block = self._quote_block(quote)
            if quote_block:
                body = f"{body}\n\n{quote_block}" if body else quote_block

        if body.strip():
            embed.description = _truncate(body, 4096)

        poll = status.get("poll")
        if poll:
            poll_name, poll_value = self._poll_field(poll)
            if poll_name:
                embed.add_field(name=poll_name, value=poll_value, inline=False)

        image = self._media_url(status.get("media") or {})
        if not image and isinstance(quote, dict) and quote.get("type") == "status":
            image = self._media_url(quote.get("media") or {})
        if image:
            embed.set_image(url=image)

        footer = (
            f"💬 {_format_count(status.get('replies'))}   "
            f"🔁 {_format_count(status.get('reposts'))}   "
            f"❤️ {_format_count(status.get('likes'))}   "
            f"👁 {_format_count(status.get('views'))}"
        )
        embed.set_footer(text=footer[:2048])

        created = status.get("created_timestamp")
        if created:
            try:
                embed.timestamp = datetime.fromtimestamp(int(created), tz=timezone.utc)
            except (ValueError, OSError, OverflowError):
                pass

        return embed

    def _track_reply(self, original_id: int, channel_id: int, reply_id: int):
        self._replies[original_id] = (channel_id, reply_id)
        while len(self._replies) > MAX_TRACKED_REPLIES:
            del self._replies[next(iter(self._replies))]

    async def _delete_reply_entry(self, entry):
        channel = self.bot.get_channel(entry[0])
        if channel is None:
            return
        try:
            await channel.get_partial_message(entry[1]).delete()
        except discord.HTTPException:
            pass

    async def _delete_tracked_reply(self, original_id: int):
        entry = self._replies.pop(original_id, None)
        if entry is not None:
            await self._delete_reply_entry(entry)

    def _find_original_by_reply(self, reply_id: int):
        for original_id, entry in self._replies.items():
            if entry[1] == reply_id:
                return original_id
        return None

    async def _set_suppressed(self, message: discord.Message, suppress: bool):
        # discord.py moved the `suppress` keyword between Message.edit and
        # PartialMessage.edit across versions, so try both.
        try:
            await message.edit(suppress=suppress)
        except TypeError:
            try:
                await discord.PartialMessage.edit(message, suppress=suppress)
            except TypeError:
                pass
        except discord.HTTPException:
            pass

    async def _suppress(self, message: discord.Message):
        perms = self._bot_permissions(message.channel, message.guild)
        if perms is None or not perms.manage_messages:
            if not self._warned_manage_messages:
                self._warned_manage_messages = True
                print("EmbedFix: missing Manage Messages — original embeds will not be suppressed.")
            return
        await self._set_suppressed(message, True)

    async def _unsuppress(self, message: discord.Message):
        perms = self._bot_permissions(message.channel, message.guild)
        if perms is None or not perms.manage_messages:
            return
        await self._set_suppressed(message, False)

    async def _reply_fixed_link(self, message: discord.Message, url: str):
        host = (urlsplit(url).netloc or "").lower()
        session = getattr(self.bot, "session", None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            if host == "x.com" or host.endswith(".x.com"):
                fixed = await self._resolve(session, "x.com", url)
            elif host == "twitter.com" or host.endswith(".twitter.com"):
                fixed = await self._resolve(session, "twitter.com", url)
            else:
                fixed = _swap_domain(url, "fixupx.com")

            try:
                reply = await message.reply(
                    content=fixed,
                    mention_author=False,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException:
                return
            self._track_reply(message.id, message.channel.id, reply.id)
        finally:
            if close_session and session and not session.closed:
                await session.close()

    async def _handle_x(self, message: discord.Message, url: str, tweet_id: str):
        perms = self._bot_permissions(message.channel, message.guild)
        if perms is None or not perms.send_messages:
            return
        if not perms.embed_links:
            await self._reply_fixed_link(message, url)
            return

        status = await self._fetch_status(tweet_id)
        if status is None:
            await self._reply_fixed_link(message, url)
            return

        embed = self._build_embed(status)
        view = TweetView(
            self,
            status,
            tweet_id,
            self._canonical_post_url(status),
            message.author.id,
            message.id,
            color=embed.color.value,
        )
        try:
            reply = await message.reply(
                embed=embed,
                view=view,
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException:
            return

        self._track_reply(message.id, message.channel.id, reply.id)
        await self._suppress(message)

    async def _handle_other(self, message: discord.Message, found):
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
                reply = await message.reply(
                    content="\n".join(fixed_links),
                    mention_author=False,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException:
                return
            self._track_reply(message.id, message.channel.id, reply.id)
        finally:
            if close_session and session and not session.closed:
                await session.close()

    async def _handle_message(self, message: discord.Message, allow_suppressed: bool = False):
        if not allow_suppressed and message.flags.suppress_embeds:
            return

        x_link = self._find_x_link(message.content)
        if x_link:
            await self._handle_x(message, x_link[0], x_link[1])
            return

        found = self._find_other_links(message.content)
        if found:
            await self._handle_other(message, found)

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

        await self._handle_message(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if after.author.bot or after.guild is None:
            return
        if after.guild.id not in self.allowed_guilds:
            return
        if before.content == after.content:
            return

        entry = self._replies.pop(after.id, None)
        if entry is not None:
            await self._delete_reply_entry(entry)
            await self._unsuppress(after)

        await self._handle_message(after, allow_suppressed=True)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild is None or message.guild.id not in self.allowed_guilds:
            return

        if message.author.bot:
            original_id = self._find_original_by_reply(message.id)
            if original_id is None:
                return
            self._replies.pop(original_id, None)
            try:
                original = await message.channel.fetch_message(original_id)
            except discord.HTTPException:
                return
            await self._unsuppress(original)
        else:
            await self._delete_tracked_reply(message.id)

    @commands.hybrid_command(name="embed", description="Fix a social media link so it embeds properly in Discord.")
    @app_commands.describe(link=f"Link to fix ({SUPPORTED_PLATFORMS})")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def embed(self, ctx: commands.Context, link: str):
        link = link.strip()

        x_link = self._find_x_link(link, allow_wrapped=True)
        if x_link:
            status = await self._fetch_status(x_link[1])
            if status is None:
                await ctx.send("I couldn't fetch that post.")
                return

            embed = self._build_embed(status)
            view = TweetView(
                self,
                status,
                x_link[1],
                self._canonical_post_url(status),
                ctx.author.id,
                color=embed.color.value,
            )
            try:
                await ctx.send(
                    embed=embed,
                    view=view,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException:
                await ctx.send(self._canonical_post_url(status))
            return

        match = OTHER_URL_PATTERN.search(link)
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
