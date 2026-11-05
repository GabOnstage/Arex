import logging
import asyncio
import io
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urlunsplit

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from ._embed_common import (
    MAX_VIDEO_BYTES,
    TRAILING_PUNCTUATION,
    _format_count,
    _format_exact,
    _swap_domain,
    _truncate,
    get_session,
    get_tracker,
    is_wrapped,
    resolve_link,
)

log = logging.getLogger("arex.x_embed")



FX_API = "https://api.fxtwitter.com/2/status/{id}"
THREAD_API = "https://api.fxtwitter.com/2/thread/{id}"
PROFILE_API = "https://api.fxtwitter.com/2/profile/{username}"

# Thread cards stay interactive long enough to read a long thread, then expire
# instead of keeping stale navigation buttons around forever.
THREAD_VIEW_TIMEOUT = 5 * 60

# Components V2 (discord.py 2.6+) lets a bot render video/GIF media inside a
# card via MediaGallery. Classic embeds cannot contain a video.
COMPONENTS_V2 = (
    hasattr(discord.ui, "LayoutView")
    and hasattr(discord.ui, "MediaGallery")
    and hasattr(discord.ui, "Container")
    and hasattr(discord.ui, "ActionRow")
)

_LayoutViewBase = getattr(discord.ui, "LayoutView", discord.ui.View)

RESERVED_X_PATHS = frozenset({
    "i", "status", "home", "explore", "notifications", "messages", "settings",
    "compose", "search", "hashtag", "login", "logout", "signup", "tos",
    "privacy", "download", "jobs", "about", "share", "intent", "account",
    "following", "followers", "lists", "bookmarks", "communities", "premium",
    "verified", "topics", "business", "help", "rules", "safety", "accessibility",
})

X_URL_PATTERN = re.compile(
    r"https?://(?:[a-z0-9-]+\.)*(?:x|twitter|fixupx|fxtwitter|vxtwitter|twitterez|xfixup)\.com(?:/[^\s<>`]*)?",
    re.IGNORECASE,
)

STATUS_PATH_PATTERN = re.compile(r"/(?:status|statuses)/(\d+)", re.IGNORECASE)

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


def _animated_gif_url(url: str) -> str:
    """Route tweet GIFs through FxTwitter's .gif host so Discord autoplays them.

    X exposes animated GIFs as silent MP4s on video.twimg.com. Discord's
    MediaGallery shows those with video controls instead of looping them, so we
    swap the host/path for the matching animated GIF when it is available.
    """
    parts = urlsplit(url)
    if (parts.hostname or "").lower() != "video.twimg.com":
        return url
    if not re.fullmatch(r"/tweet_video/[^/]+\.mp4", parts.path, re.IGNORECASE):
        return url
    return urlunsplit(
        ("https", "gif.fxtwitter.com", f"{parts.path[:-4]}.gif", "", "")
    )


class LanguageSelect(discord.ui.Select):
    def __init__(self, view, selected: str = None, row: int = 0):
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
            row=row,
        )
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        await self.view_ref.handle_translate(interaction, self.values[0])


class ReplyActionsMixin:
    """Shared author/moderator delete behavior for reply cards."""

    cog: "XEmbed"
    author_id: int
    original_message_id: int

    async def handle_delete(self, interaction: discord.Interaction):
        tracker = self.cog.tracker
        if not tracker.can_delete(interaction, self.author_id):
            await interaction.response.send_message(
                "Only the original author or moderators can delete this.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        # Keep the author's original preview suppressed: deleting the bot embed
        # must not re-embed the original message.
        if self.original_message_id:
            await tracker.delete_tracked_reply(
                self.original_message_id,
                exclude_id=getattr(interaction.message, "id", None),
            )

        try:
            await interaction.message.delete()
        except discord.HTTPException:
            try:
                await interaction.followup.send("I couldn't delete the embed.", ephemeral=True)
            except discord.HTTPException:
                pass

    def _make_delete_button(self, row: int = None):
        delete_button = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            emoji="🗑️",
            row=row,
            custom_id="fx:delete",
        )
        delete_button.callback = self.handle_delete
        return delete_button


class ThreadNavigationMixin:
    """Up/down buttons for stepping through a fetched thread."""

    thread: list
    index: int

    def _has_thread(self) -> bool:
        return bool(self.thread) and len(self.thread) > 1

    def _nav_buttons(self, row: int = None):
        previous = discord.ui.Button(
            emoji="⬆️",
            style=discord.ButtonStyle.secondary,
            disabled=self.index <= 0,
            row=row,
        )
        previous.callback = self._previous_post
        following = discord.ui.Button(
            emoji="⬇️",
            style=discord.ButtonStyle.secondary,
            disabled=self.index >= len(self.thread) - 1,
            row=row,
        )
        following.callback = self._next_post
        return previous, following

    async def _previous_post(self, interaction: discord.Interaction):
        await self._navigate(interaction, -1)

    async def _next_post(self, interaction: discord.Interaction):
        await self._navigate(interaction, 1)

    async def _navigate(self, interaction: discord.Interaction, delta: int):
        # Respond before doing any work so we stay inside Discord's 3 second
        # interaction window, even on slower connections.
        await interaction.response.defer()

        new_index = self.index + delta
        if not 0 <= new_index < len(self.thread):
            return

        view = self._rebuild(index=new_index)
        payload = self._navigate_payload(new_index)
        try:
            await interaction.message.edit(view=view, **payload)
        except discord.HTTPException:
            pass


class ReplyView(ReplyActionsMixin, discord.ui.View):
    """Classic rich-embed view with a shared author/moderator delete button."""

    def __init__(
        self,
        cog: "XEmbed",
        author_id: int,
        original_message_id: int = None,
        timeout: float = None,
    ):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.author_id = author_id
        self.original_message_id = original_message_id

    def _add_delete_button(self, row: int = 1):
        self.add_item(self._make_delete_button(row=row))


class TweetView(ThreadNavigationMixin, ReplyView):
    def __init__(
        self,
        cog: "XEmbed",
        base_status: dict,
        tweet_id: str,
        post_url: str,
        author_id: int,
        original_message_id: int = None,
        color: int = None,
        selected: str = None,
        thread: list = None,
        index: int = 0,
    ):
        self.thread = list(thread) if thread else [base_status]
        self.index = max(0, min(index, len(self.thread) - 1))
        is_thread = len(self.thread) > 1

        super().__init__(
            cog,
            author_id,
            original_message_id,
            timeout=THREAD_VIEW_TIMEOUT if is_thread else None,
        )
        self.base_status = base_status
        self.tweet_id = tweet_id
        self.post_url = post_url
        self.color = color if color is not None else discord.Color.random().value

        self.add_item(LanguageSelect(self, selected, row=0))
        self.add_item(
            discord.ui.Button(
                label="Go to post",
                style=discord.ButtonStyle.link,
                url=post_url,
                emoji="🔗",
                row=1,
            )
        )
        self._add_delete_button(row=1)

        if is_thread:
            previous, following = self._nav_buttons(row=2)
            self.add_item(previous)
            self.add_item(following)

    def _rebuild(self, selected: str = None, index: int = None) -> "TweetView":
        index = self.index if index is None else index
        base = self.base_status if index == self.index else self.thread[index]
        return TweetView(
            self.cog,
            base,
            base.get("id") or self.tweet_id,
            self.cog._canonical_post_url(base),
            self.author_id,
            self.original_message_id,
            self.color,
            selected,
            thread=self.thread,
            index=index,
        )

    def _navigate_payload(self, index: int):
        return {
            "embed": self.cog._build_embed(
                self.thread[index],
                color=self.color,
                thread=self.thread,
            ),
            # Drop the previous post's downloaded video so it doesn't linger
            # under a different post in the classic (non-Components V2) fallback.
            "attachments": [],
        }

    async def handle_translate(self, interaction: discord.Interaction, language: str):
        await interaction.response.defer()

        if language == "original":
            embed = self.cog._build_embed(
                self.base_status,
                color=self.color,
                thread=self.thread,
            )
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

        embed = self.cog._build_embed(status, color=self.color, thread=self.thread)
        try:
            await interaction.message.edit(embed=embed, view=self._rebuild(language))
        except discord.HTTPException:
            pass


class TweetLayoutView(ThreadNavigationMixin, ReplyActionsMixin, _LayoutViewBase):
    """Components V2 card whose MediaGallery plays videos/GIFs inline."""

    def __init__(
        self,
        cog: "XEmbed",
        base_status: dict,
        tweet_id: str,
        post_url: str,
        author_id: int,
        original_message_id: int = None,
        color: int = None,
        selected: str = None,
        thread: list = None,
        index: int = 0,
    ):
        self.thread = list(thread) if thread else [base_status]
        self.index = max(0, min(index, len(self.thread) - 1))
        is_thread = len(self.thread) > 1

        super().__init__(timeout=THREAD_VIEW_TIMEOUT if is_thread else None)
        self.cog = cog
        self.author_id = author_id
        self.original_message_id = original_message_id
        self.base_status = base_status
        self.tweet_id = tweet_id
        self.post_url = post_url
        self.color = color if color is not None else discord.Color.random().value

        self.add_item(cog._build_layout_container(base_status, self.color, thread=self.thread))

        # Components V2 gives a select menu the full width of its Action Row, so
        # it cannot share a row with buttons. Keep the picker on its own row.
        select_row = discord.ui.ActionRow()
        select_row.add_item(LanguageSelect(self, selected, row=None))
        self.add_item(select_row)

        button_row = discord.ui.ActionRow()
        button_row.add_item(
            discord.ui.Button(
                label="Go to post",
                style=discord.ButtonStyle.link,
                url=post_url,
                emoji="🔗",
            )
        )
        button_row.add_item(self._make_delete_button())
        self.add_item(button_row)

        if is_thread:
            nav_row = discord.ui.ActionRow()
            previous, following = self._nav_buttons()
            nav_row.add_item(previous)
            nav_row.add_item(following)
            self.add_item(nav_row)

    def _rebuild(
        self,
        selected: str = None,
        status: dict = None,
        index: int = None,
    ) -> "TweetLayoutView":
        index = self.index if index is None else index
        if status is not None:
            base = status
        elif index == self.index:
            base = self.base_status
        else:
            base = self.thread[index]
        return TweetLayoutView(
            self.cog,
            base,
            base.get("id") or self.tweet_id,
            self.cog._canonical_post_url(base),
            self.author_id,
            self.original_message_id,
            self.color,
            selected,
            thread=self.thread,
            index=index,
        )

    def _navigate_payload(self, index: int):
        return {}

    async def handle_translate(self, interaction: discord.Interaction, language: str):
        await interaction.response.defer()

        if language == "original":
            try:
                await interaction.message.edit(view=self._rebuild("original"))
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

        try:
            await interaction.message.edit(view=self._rebuild(language, status=status))
        except discord.HTTPException:
            pass


class ProfileView(ReplyView):
    def __init__(
        self,
        cog: "XEmbed",
        profile: dict,
        author_id: int,
        original_message_id: int = None,
        color: int = None,
    ):
        super().__init__(cog, author_id, original_message_id)
        self.profile = profile
        self.color = color if color is not None else discord.Color.random().value

        profile_url = cog._profile_url(profile)
        self.add_item(
            discord.ui.Button(
                label="Go to profile",
                style=discord.ButtonStyle.link,
                url=profile_url,
                emoji="🔗",
                row=0,
            )
        )
        self._add_delete_button(row=0)


class XEmbed(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tracker = get_tracker(bot)
        if not COMPONENTS_V2:
            print(
                "EmbedFix: discord.py < 2.6 detected. Inline video/GIF cards need "
                "discord.py>=2.6; running the classic embed + video attachment "
                "fallback instead. Upgrade with: pip install -U \"discord.py>=2.6\""
            )

    @staticmethod
    def _upload_limit(guild) -> int:
        default = 8 * 1024 * 1024
        if guild is None:
            return default
        limit = getattr(guild, "filesize_limit", None) or default
        return min(limit, MAX_VIDEO_BYTES)

    @staticmethod
    def _can_attach(ctx) -> bool:
        guild = getattr(ctx, "guild", None)
        if guild is None:
            return True
        me = getattr(guild, "me", None)
        channel = getattr(ctx, "channel", None)
        if me is None or channel is None:
            return True
        try:
            return channel.permissions_for(me).attach_files
        except AttributeError:
            return True

    async def _fetch_status(self, tweet_id: str, lang: str = None):
        session, close_session = get_session(self.bot)

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

    async def _fetch_thread(self, tweet_id: str):
        """Fetch the focal post plus the unrolled thread it belongs to."""
        session, close_session = get_session(self.bot)

        data = None
        try:
            async with session.get(
                THREAD_API.format(id=tweet_id),
                timeout=aiohttp.ClientTimeout(total=12),
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

        raw_thread = data.get("thread")
        thread = []
        if isinstance(raw_thread, list):
            seen = set()
            for item in raw_thread:
                if not isinstance(item, dict) or item.get("type") != "status":
                    continue
                key = item.get("id")
                if key and key in seen:
                    continue
                if key:
                    seen.add(key)
                thread.append(item)

        if not thread:
            thread = [status]
        elif not any(item.get("id") == status.get("id") for item in thread):
            # The focal post should always be part of the returned thread, but
            # keep navigation sane if the API omits it.
            thread.insert(0, status)

        return status, thread

    async def _fetch_post_with_thread(self, tweet_id: str):
        """Prefer the thread endpoint, falling back to the single-post endpoint."""
        fetched = await self._fetch_thread(tweet_id)
        if fetched is not None:
            return fetched

        status = await self._fetch_status(tweet_id)
        if status is None:
            return None
        return status, [status]

    @staticmethod
    def _thread_index(thread: list, status: dict) -> int:
        status_id = status.get("id")
        for index, item in enumerate(thread or []):
            if item.get("id") == status_id:
                return index
        return 0

    @staticmethod
    def _thread_position(thread: list, status: dict):
        if not thread or len(thread) <= 1:
            return None
        status_id = status.get("id")
        for index, item in enumerate(thread):
            if item.get("id") == status_id:
                return index + 1, len(thread)
        return None

    async def _fetch_profile(self, username: str):
        session, close_session = get_session(self.bot)
        data = None
        try:
            async with session.get(
                PROFILE_API.format(username=username),
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
        user = data.get("user")
        if not isinstance(user, dict) or user.get("type") != "profile":
            return None
        return user

    def find_x_link(self, content: str, allow_wrapped: bool = False):
        for match in X_URL_PATTERN.finditer(content):
            if not allow_wrapped and is_wrapped(content, match):
                continue
            url = match.group(0).rstrip(TRAILING_PUNCTUATION)
            status_match = STATUS_PATH_PATTERN.search(urlsplit(url).path)
            if status_match:
                return url, status_match.group(1)
        return None

    def find_x_profile_link(self, content: str, allow_wrapped: bool = False):
        for match in X_URL_PATTERN.finditer(content):
            if not allow_wrapped and is_wrapped(content, match):
                continue
            url = match.group(0).rstrip(TRAILING_PUNCTUATION)
            segments = [segment for segment in urlsplit(url).path.split("/") if segment]
            if len(segments) != 1:
                continue
            username = segments[0].lstrip("@")
            if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", username):
                continue
            if username.lower() in RESERVED_X_PATHS:
                continue
            return url, username
        return None

    def parse_username(self, raw: str):
        raw = (raw or "").strip()
        if not raw:
            return None
        if re.match(r"^(?:www\.)?(?:x|twitter|fixupx|fxtwitter)\.com/", raw, re.IGNORECASE):
            raw = "https://" + raw
        found = self.find_x_profile_link(raw, allow_wrapped=True)
        if found:
            return found[1]
        raw = raw.lstrip("@").strip()
        if re.fullmatch(r"[A-Za-z0-9_]{1,15}", raw):
            return raw
        return None

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

    @staticmethod
    def _video_media(media: dict):
        """Return each video/GIF attachment once, across fxtwitter's buckets.

        Depending on the post, fxtwitter can expose videos in ``videos``,
        only in ``all``, or as an ``external`` video. The gallery must consider
        all three, otherwise the card silently drops the video.
        """
        external = media.get("external")
        buckets = [media.get("videos"), media.get("all")]
        if isinstance(external, dict):
            buckets.append([external])

        videos = []
        seen = set()
        for bucket in buckets:
            for item in bucket or []:
                if not isinstance(item, dict):
                    continue
                if item is not external and item.get("type") not in (
                    "video",
                    "gif",
                    "animated_gif",
                ):
                    continue
                key = item.get("id") or item.get("url")
                if key and key in seen:
                    continue
                if key:
                    seen.add(key)
                videos.append(item)
        return videos

    @staticmethod
    def _best_video_url(video: dict):
        best_url = None
        best_bitrate = -1
        for fmt in video.get("formats") or []:
            if not isinstance(fmt, dict) or fmt.get("container") != "mp4":
                continue
            url = fmt.get("url")
            if not url:
                continue
            bitrate = fmt.get("bitrate") or 0
            if bitrate > best_bitrate:
                best_url, best_bitrate = url, bitrate
        url = best_url or video.get("url")
        if not url or ".m3u8" in url:
            return None
        return url

    def _primary_video_url(self, status: dict):
        media = status.get("media") or {}
        for video in self._video_media(media):
            url = self._best_video_url(video)
            if url:
                return url
        return None

    async def _download_media(self, session: aiohttp.ClientSession, url: str, limit: int):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return None
                if resp.content_length and resp.content_length > limit:
                    return None
                buffer = io.BytesIO()
                async for chunk in resp.content.iter_chunked(64 * 1024):
                    buffer.write(chunk)
                    if buffer.tell() > limit:
                        return None
                if buffer.tell() == 0:
                    return None
                buffer.seek(0)
                return buffer
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return None

    def _gallery_items(self, status: dict):
        media = status.get("media") or {}
        author = status.get("author") or {}
        name = author.get("name") or author.get("screen_name") or "X"
        name = _truncate(str(name), 180)

        items = []
        seen = set()

        for video in self._video_media(media):
            url = self._best_video_url(video)
            if not url:
                continue
            media_type = str(video.get("type") or "video").lower()
            is_gif = media_type in ("gif", "animated_gif")
            if is_gif:
                url = _animated_gif_url(url)
            if url in seen:
                continue
            seen.add(url)
            label = "Animated GIF" if is_gif else "Video"
            items.append(
                discord.MediaGalleryItem(
                    url,
                    description=_truncate(f"{label} from {name}", 256),
                )
            )

        photos = media.get("photos") or [
            item for item in (media.get("all") or [])
            if isinstance(item, dict) and item.get("type") == "photo"
        ]
        for photo in photos:
            if not isinstance(photo, dict):
                continue
            url = photo.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            items.append(
                discord.MediaGalleryItem(
                    url,
                    description=_truncate(f"Image from {name}", 256),
                )
            )

        return items[:10]

    def _build_body(self, status: dict) -> str:
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

        return body

    def _build_layout_container(self, status: dict, color: int = None, thread: list = None):
        author = status.get("author") or {}
        screen_name = author.get("screen_name") or "i"
        name = author.get("name") or screen_name

        identity = f"**{discord.utils.escape_markdown(name)}** (@{discord.utils.escape_markdown(screen_name)})"
        if (author.get("verification") or {}).get("verified"):
            identity += " ✔️"

        body = self._build_body(status)
        poll = status.get("poll")
        if poll:
            poll_name, poll_value = self._poll_field(poll)
            if poll_name:
                block = f"**{poll_name}**\n{poll_value}"
                body = f"{body}\n\n{block}" if body else block

        header = identity + (f"\n\n{body}" if body else "")
        # Components V2 allows 4000 display characters across the whole card;
        # leave room for the stats and footer lines so long posts still render
        # as a card (instead of failing and falling back to a classic embed).
        header = _truncate(header, 3000)

        children = []
        avatar = author.get("avatar_url")
        if avatar:
            children.append(
                discord.ui.Section(
                    header,
                    accessory=discord.ui.Thumbnail(
                        avatar,
                        description=f"{name} profile photo",
                    ),
                )
            )
        else:
            children.append(discord.ui.TextDisplay(header))

        gallery = self._gallery_items(status)
        if gallery:
            children.append(discord.ui.MediaGallery(*gallery))

        footer = (
            f"💬 {_format_count(status.get('replies'))}   "
            f"🔁 {_format_count(status.get('reposts'))}   "
            f"❤️ {_format_count(status.get('likes'))}   "
            f"👁 {_format_count(status.get('views'))}"
        )
        children.append(discord.ui.Separator())
        children.append(discord.ui.TextDisplay(f"-# {footer}"))

        credit = "-# X / Twitter"
        position = self._thread_position(thread, status)
        if position:
            credit += f" • Post {position[0]}/{position[1]}"
        created = status.get("created_timestamp")
        if created:
            credit += f" • <t:{int(created)}:R>"
        children.append(discord.ui.TextDisplay(credit))

        return discord.ui.Container(
            *children,
            accent_color=color if color is not None else discord.Color.random().value,
        )

    def _build_embed(self, status: dict, color: int = None, thread: list = None) -> discord.Embed:
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

        body = self._build_body(status)
        quote = status.get("quote")

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
        position = self._thread_position(thread, status)
        if position:
            footer += f"   •   Post {position[0]}/{position[1]}"
        embed.set_footer(text=footer[:2048])

        # Let Discord render/localize the post time in the footer.
        created = status.get("created_timestamp")
        if created:
            try:
                embed.timestamp = datetime.fromtimestamp(int(created), tz=timezone.utc)
            except (ValueError, OSError, OverflowError):
                pass

        return embed

    @staticmethod
    def _joined_timestamp(raw):
        if not raw:
            return None
        try:
            return int(parsedate_to_datetime(raw).timestamp())
        except (TypeError, ValueError, OverflowError):
            return None

    def _build_profile_embed(self, user: dict, color: int = None) -> discord.Embed:
        screen_name = user.get("screen_name") or "unknown"
        name = user.get("name") or screen_name

        display_name = f"{discord.utils.escape_markdown(name)} (@{discord.utils.escape_markdown(screen_name)})"
        if (user.get("verification") or {}).get("verified"):
            display_name = f"{display_name} ✔️"
        display_name = _truncate(display_name, 256)

        profile_url = self._profile_url(user)
        embed = discord.Embed(color=color if color is not None else discord.Color.random())
        embed.set_author(
            name=display_name,
            url=profile_url,
            icon_url=user.get("avatar_url"),
        )
        embed.url = profile_url

        description = (user.get("description") or "").strip()
        if description:
            embed.description = _truncate(description, 4096)

        banner = user.get("banner_url")
        if banner:
            embed.set_image(url=banner)

        avatar = user.get("avatar_url")
        if avatar:
            embed.set_thumbnail(url=avatar.replace("_normal.", "_200x200."))

        embed.add_field(name="Followers", value=_format_exact(user.get("followers")), inline=True)
        embed.add_field(name="Following", value=_format_exact(user.get("following")), inline=True)
        embed.add_field(name="Posts", value=_format_exact(user.get("statuses")), inline=True)
        embed.add_field(name="Likes", value=_format_exact(user.get("likes")), inline=True)
        embed.add_field(name="Media", value=_format_exact(user.get("media_count")), inline=True)
        if user.get("protected"):
            embed.add_field(name="Account", value="🔒 Protected", inline=True)

        location = user.get("location")
        if location:
            embed.add_field(name="Location", value=_truncate(location, 1024), inline=True)

        joined = self._joined_timestamp(user.get("joined"))
        if joined:
            embed.add_field(name="Joined", value=f"<t:{joined}:D>", inline=True)

        website = user.get("website")
        if isinstance(website, dict) and website.get("url"):
            display = website.get("display_url") or website.get("url")
            embed.add_field(
                name="Website",
                value=f"[{discord.utils.escape_markdown(str(display))}]({website['url']})",
                inline=True,
            )

        embed.set_footer(text="X / Twitter profile")
        return embed

    async def _reply_fixed_link(self, message: discord.Message, url: str):
        host = (urlsplit(url).netloc or "").lower()
        session, close_session = get_session(self.bot)

        try:
            if host == "x.com" or host.endswith(".x.com"):
                fixed = await resolve_link(session, url, "fixupx.com", "twitterez.com")
            elif host == "twitter.com" or host.endswith(".twitter.com"):
                fixed = await resolve_link(session, url, "fixupx.com", "twitterez.com")
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
            self.tracker.track_reply(message.id, message.channel.id, reply.id)
        finally:
            if close_session and session and not session.closed:
                await session.close()

    @staticmethod
    def _drop_video_thumbnail(embed: discord.Embed, status: dict):
        videos = (status.get("media") or {}).get("videos") or []
        if not videos or not isinstance(videos[0], dict):
            return
        thumbnail = videos[0].get("thumbnail_url")
        if thumbnail and getattr(embed.image, "url", None) == thumbnail:
            embed.set_image(url=None)

    async def _send_tweet(self, sender, status: dict, embed: discord.Embed, view, guild, session, allow_file: bool = True):
        video_url = self._primary_video_url(status)
        file = None
        if video_url and allow_file:
            buffer = await self._download_media(session, video_url, self._upload_limit(guild))
            if buffer is not None:
                file = discord.File(buffer, filename="video.mp4")
                self._drop_video_thumbnail(embed, status)

        payload = {
            "embed": embed,
            "view": view,
            "allowed_mentions": discord.AllowedMentions.none(),
        }

        reply = None
        if file is not None:
            try:
                reply = await sender(file=file, **payload)
            except discord.HTTPException:
                reply = None

        if reply is None:
            try:
                reply = await sender(**payload)
            except discord.HTTPException:
                return None, None

        video_post = None
        if file is None and video_url:
            try:
                video_post = await sender(content=video_url)
            except discord.HTTPException:
                video_post = None

        return reply, video_post

    async def handle_message(self, message: discord.Message, url: str, tweet_id: str):
        perms = self.tracker.bot_permissions(message.channel, message.guild)
        if perms is None or not perms.send_messages:
            return
        if not perms.embed_links:
            await self._reply_fixed_link(message, url)
            return

        session, close_session = get_session(self.bot)
        try:
            async with message.channel.typing():
                fetched = await self._fetch_post_with_thread(tweet_id)
                if fetched is None:
                    await self._reply_fixed_link(message, url)
                    return
                status, thread = fetched
                index = self._thread_index(thread, status)
                focal = thread[index]

                if COMPONENTS_V2:
                    try:
                        view = TweetLayoutView(
                            self,
                            focal,
                            focal.get("id") or tweet_id,
                            self._canonical_post_url(focal),
                            message.author.id,
                            message.id,
                            thread=thread,
                            index=index,
                        )
                        reply = await message.reply(
                            view=view,
                            mention_author=False,
                            allowed_mentions=discord.AllowedMentions.none(),
                        )
                        self.tracker.track_reply(message.id, message.channel.id, reply.id)
                        await self.tracker.suppress(message)
                        return
                    except discord.HTTPException as exc:
                        print(
                            "EmbedFix: Components V2 card failed, falling back to "
                            f"a classic embed ({exc})."
                        )

                embed = self._build_embed(focal, thread=thread)
                view = TweetView(
                    self,
                    focal,
                    focal.get("id") or tweet_id,
                    self._canonical_post_url(focal),
                    message.author.id,
                    message.id,
                    color=embed.color.value,
                    thread=thread,
                    index=index,
                )

                reply, video_post = await self._send_tweet(
                    lambda **kwargs: message.reply(mention_author=False, **kwargs),
                    focal,
                    embed,
                    view,
                    message.guild,
                    session,
                    allow_file=bool(getattr(perms, "attach_files", False)),
                )
                if reply is None:
                    return

                self.tracker.track_reply(
                    message.id,
                    message.channel.id,
                    reply.id,
                    video_post.id if video_post is not None else None,
                )
                await self.tracker.suppress(message)
        finally:
            if close_session and session and not session.closed:
                await session.close()

    async def handle_profile_message(self, message: discord.Message, url: str, username: str):
        perms = self.tracker.bot_permissions(message.channel, message.guild)
        if perms is None or not perms.send_messages:
            return
        if not perms.embed_links:
            await self._reply_fixed_link(message, url)
            return

        async with message.channel.typing():
            profile = await self._fetch_profile(username)
            if profile is None:
                await self._reply_fixed_link(message, url)
                return

            embed = self._build_profile_embed(profile)
            view = ProfileView(
                self,
                profile,
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

            self.tracker.track_reply(message.id, message.channel.id, reply.id)
            await self.tracker.suppress(message)

    async def handle_command_post(self, ctx: commands.Context, url: str, tweet_id: str):
        session, close_session = get_session(self.bot)
        try:
            fetched = await self._fetch_post_with_thread(tweet_id)
            if fetched is None:
                await ctx.send("I couldn't fetch that post.")
                return
            status, thread = fetched
            index = self._thread_index(thread, status)
            focal = thread[index]

            if COMPONENTS_V2:
                try:
                    view = TweetLayoutView(
                        self,
                        focal,
                        focal.get("id") or tweet_id,
                        self._canonical_post_url(focal),
                        ctx.author.id,
                        thread=thread,
                        index=index,
                    )
                    await ctx.send(
                        view=view,
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                    return
                except discord.HTTPException as exc:
                    print(
                        "EmbedFix: Components V2 card failed, falling back to "
                        f"a classic embed ({exc})."
                    )

            embed = self._build_embed(focal, thread=thread)
            view = TweetView(
                self,
                focal,
                focal.get("id") or tweet_id,
                self._canonical_post_url(focal),
                ctx.author.id,
                color=embed.color.value,
                thread=thread,
                index=index,
            )
            reply, _ = await self._send_tweet(
                ctx.send,
                focal,
                embed,
                view,
                ctx.guild,
                session,
                allow_file=self._can_attach(ctx),
            )
            if reply is None:
                await ctx.send(self._canonical_post_url(focal))
        finally:
            if close_session and session and not session.closed:
                await session.close()

    async def handle_command_profile(self, ctx: commands.Context, url: str, username: str):
        profile = await self._fetch_profile(username)
        if profile is None:
            await ctx.send("I couldn't fetch that profile.")
            return

        embed = self._build_profile_embed(profile)
        view = ProfileView(
            self,
            profile,
            ctx.author.id,
            color=embed.color.value,
        )
        try:
            await ctx.send(embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            await ctx.send(self._profile_url(profile))

    @commands.hybrid_command(name="xinfo", description="Look up an X/Twitter profile.")
    @app_commands.describe(username="X username, @handle, or profile URL")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def xinfo(self, ctx: commands.Context, username: str):
        await ctx.defer()
        parsed = self.parse_username(username)
        if parsed is None:
            await ctx.send("Give me an X username, @handle, or profile URL.")
            return

        profile = await self._fetch_profile(parsed)
        if profile is None:
            await ctx.send("I couldn't fetch that profile.")
            return

        embed = self._build_profile_embed(profile)
        view = ProfileView(
            self,
            profile,
            ctx.author.id,
            color=embed.color.value,
        )
        try:
            await ctx.send(embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            await ctx.send(self._profile_url(profile))


async def setup(bot: commands.Bot):
    await bot.add_cog(XEmbed(bot))
