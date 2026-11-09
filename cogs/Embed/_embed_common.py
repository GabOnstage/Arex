import logging
import asyncio
import html as html_module
import io
import json
import re
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit, urlunsplit

import aiohttp
import discord
from discord.ext import commands

log = logging.getLogger("arex.embed_common")



PRIMARY_DOMAINS = {
    "x.com": "fixupx.com",
    "twitter.com": "fixupx.com",
    "tiktok.com": "tnktok.com",
    "instagram.com": "vxinstagram.com",
    "reddit.com": "vxreddit.com",
    "threads.net": "vxthreads.net",
}

BACKUP_DOMAINS = {
    "x.com": "twitterez.com",
    "twitter.com": "twitterez.com",
    "tiktok.com": "tiktokez.com",
    "instagram.com": "axinstagram.com",
    "reddit.com": "redditez.com",
    "threads.net": "threadsez.net",
}

SUPPORTED_PLATFORMS = "X/Twitter, TikTok, Instagram, Reddit, Threads"

# External embed fixers used by the non-X platforms.  FixEmbed is preferred
# because it renders rich previews for every supported site; the per-platform
# proxy domains below are the fallback chain.
FIXEMBED_URL = "https://fixembed.app/embed?url={url}"

# FixEmbed generates its preview on demand and regularly takes a few seconds
# to answer, so it needs a longer budget than the lightweight proxy probes.
FIXEMBED_TIMEOUT = 10
PROXY_TIMEOUT = 4
FIXEMBED_HEAD_BYTES = 16384

MAX_VIDEO_BYTES = 10 * 1024 * 1024

OTHER_URL_PATTERN = re.compile(
    r"https?://(?:[a-z0-9-]+\.)*(?P<domain>"
    r"tiktok\.com|instagram\.com|instagr\.am|reddit\.com|redd\.it|threads\.net|threads\.com"
    r")(?:/[^\s<>`]*)?",
    re.IGNORECASE,
)

# Domains that belong to the same platform. Used so short/alternate domains
# still dispatch to the right rich-embed cog.
DOMAIN_ALIASES = {
    "redd.it": "reddit.com",
    "instagr.am": "instagram.com",
    "threads.com": "threads.net",
}

TRAILING_PUNCTUATION = ".,;:!?)}]>\"'"

MAX_TRACKED_REPLIES = 5000

# Bot crawler user agents. Discord's own crawler is accepted by most social
# sites, while Meta properties also expose public OpenGraph data to their own
# crawler. We try these before falling back to a proxy link.
DISCORD_BOT_UA = "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)"
FACEBOOK_BOT_UA = (
    "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"
)
GOOGLEBOT_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"

# Components V2 (discord.py 2.6+) lets a bot render video/GIF media inside a
# card via MediaGallery. Classic embeds cannot contain a video.
COMPONENTS_V2 = (
    hasattr(discord.ui, "LayoutView")
    and hasattr(discord.ui, "MediaGallery")
    and hasattr(discord.ui, "Container")
    and hasattr(discord.ui, "ActionRow")
)

_LayoutViewBase = getattr(discord.ui, "LayoutView", discord.ui.View)


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


def _format_exact(value) -> str:
    try:
        return f"{int(value or 0):,}"
    except (TypeError, ValueError):
        return "0"


def _truncate(text: str, limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def is_wrapped(content: str, match: re.Match) -> bool:
    start, end = match.span()
    before = content[start - 1] if start > 0 else ""
    after = content[end] if end < len(content) else ""
    return before == "<" and after == ">"


def get_session(bot):
    session = getattr(bot, "session", None)
    if session is None or session.closed:
        return aiohttp.ClientSession(), True
    return session, False


async def resolve_link(session, url: str, primary_domain: str, backup_domain: str = None) -> str:
    primary = _swap_domain(url, primary_domain)
    if backup_domain is None:
        return primary
    backup = _swap_domain(url, backup_domain)

    for candidate in (primary, backup):
        try:
            async with session.get(
                candidate,
                headers={"User-Agent": DISCORD_BOT_UA},
                timeout=aiohttp.ClientTimeout(total=4),
            ) as resp:
                if resp.status < 500:
                    return candidate
        except (aiohttp.ClientError, asyncio.TimeoutError):
            continue
    return primary


def fixembed_url(url: str) -> str:
    """Return a FixEmbed URL for *url*."""

    return FIXEMBED_URL.format(url=quote(url, safe=""))


async def resolve_embed_site(session, url: str, domain: str) -> str:
    """Resolve a non-X link to an external embed site.

    FixEmbed is tried first; the platform-specific proxy domains are used as
    fallbacks.  The FixEmbed URL is validated with the same Discordbot user
    agent Discord uses when unfurling links.  FixEmbed is slow by design, so a
    timeout is not treated as a failure: the URL is still returned because
    Discord will fetch it later.
    """

    primary_domain = PRIMARY_DOMAINS.get(domain)
    backup_domain = BACKUP_DOMAINS.get(domain)

    candidates = [fixembed_url(url)]
    if primary_domain:
        candidates.append(_swap_domain(url, primary_domain))
    if backup_domain:
        candidates.append(_swap_domain(url, backup_domain))

    fixembed = candidates[0]
    for attempt in range(2):
        try:
            async with session.get(
                fixembed,
                headers={"User-Agent": DISCORD_BOT_UA},
                timeout=aiohttp.ClientTimeout(total=FIXEMBED_TIMEOUT),
            ) as resp:
                if resp.status < 500:
                    # The metadata lives in <head>; no need to download the
                    # whole preview page.
                    body = await resp.content.read(FIXEMBED_HEAD_BYTES)
                    head = body.decode("utf-8", "ignore")
                    if "og:title" in head or "twitter:title" in head:
                        return fixembed
        except asyncio.TimeoutError:
            # FixEmbed is reachable but slow.  It is still the preferred
            # embedder, so let Discord try it instead of downgrading.
            return fixembed
        except aiohttp.ClientError:
            break

        # A normal HTTP response without preview metadata usually means
        # FixEmbed could not resolve the link.  Retry once, since the first
        # request is occasionally a generic/rate-limited page.
        if attempt == 0:
            await asyncio.sleep(0.5)

    for candidate in candidates[1:]:
        try:
            async with session.get(
                candidate,
                headers={"User-Agent": DISCORD_BOT_UA},
                timeout=aiohttp.ClientTimeout(total=PROXY_TIMEOUT),
            ) as resp:
                if resp.status < 500:
                    return candidate
        except (aiohttp.ClientError, asyncio.TimeoutError):
            continue

    # Everything failed: still prefer FixEmbed over the raw link.
    return fixembed


class LinkPlatform(commands.Cog):
    """Base for platforms that resolve to an external embed site."""

    DOMAIN = ""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def resolve(self, session: aiohttp.ClientSession, url: str) -> str:
        return await resolve_embed_site(session, url, self.DOMAIN)


class ReplyTracker:
    """Shared reply bookkeeping so every platform can suppress/delete its cards."""

    def __init__(self, bot):
        self.bot = bot
        self._replies = {}
        self._warned_manage_messages = False

    def bot_permissions(self, channel, guild):
        if guild is None:
            return None
        me = guild.me or guild.get_member(self.bot.user.id)
        if me is None:
            return None
        return channel.permissions_for(me)

    @staticmethod
    def can_delete(interaction: discord.Interaction, author_id: int) -> bool:
        permissions = getattr(interaction.user, "guild_permissions", None)
        is_mod = bool(permissions and (permissions.manage_messages or permissions.administrator))
        return interaction.user.id == author_id or is_mod

    def track_reply(self, original_id: int, channel_id: int, *reply_ids: int):
        new_ids = [reply_id for reply_id in reply_ids if reply_id]
        if not new_ids:
            return

        entry = self._replies.get(original_id)
        existing = []
        if entry is not None:
            stored = entry[1] if isinstance(entry[1], (list, tuple)) else (entry[1],)
            existing = list(stored)
        merged = tuple(dict.fromkeys(existing + new_ids))

        self._replies[original_id] = (channel_id, merged)
        while len(self._replies) > MAX_TRACKED_REPLIES:
            del self._replies[next(iter(self._replies))]

    def forget(self, original_id: int):
        self._replies.pop(original_id, None)

    def find_original_by_reply(self, reply_id: int):
        for original_id, entry in self._replies.items():
            stored = entry[1] if isinstance(entry[1], (list, tuple)) else (entry[1],)
            if reply_id in stored:
                return original_id
        return None

    async def delete_reply_entry(self, entry):
        channel = self.bot.get_channel(entry[0])
        if channel is None:
            return
        stored = entry[1] if isinstance(entry[1], (list, tuple)) else (entry[1],)
        for reply_id in stored:
            try:
                await channel.get_partial_message(reply_id).delete()
            except discord.HTTPException:
                pass

    async def delete_tracked_reply(self, original_id: int, exclude_id: int = None):
        entry = self._replies.pop(original_id, None)
        if entry is None:
            return
        channel = self.bot.get_channel(entry[0])
        if channel is None:
            return
        stored = entry[1] if isinstance(entry[1], (list, tuple)) else (entry[1],)
        for reply_id in stored:
            if reply_id == exclude_id:
                continue
            try:
                await channel.get_partial_message(reply_id).delete()
            except discord.HTTPException:
                pass

    async def set_suppressed(self, message: discord.Message, suppress: bool):
        try:
            await message.edit(suppress=suppress)
        except TypeError:
            try:
                await discord.PartialMessage.edit(message, suppress=suppress)
            except TypeError:
                pass
        except discord.HTTPException:
            pass

    async def suppress(self, message: discord.Message):
        perms = self.bot_permissions(message.channel, message.guild)
        if perms is None or not perms.manage_messages:
            if not self._warned_manage_messages:
                self._warned_manage_messages = True
                print("EmbedFix: missing Manage Messages — original embeds will not be suppressed.")
            return
        await self.set_suppressed(message, True)


def get_tracker(bot) -> ReplyTracker:
    tracker = getattr(bot, "_embed_reply_tracker", None)
    if tracker is None:
        tracker = ReplyTracker(bot)
        bot._embed_reply_tracker = tracker
    return tracker


# ---------------------------------------------------------------------------
# Shared rich-embed helpers
# ---------------------------------------------------------------------------

_META_TAG_RE = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_META_ATTR_RE = re.compile(
    r"""([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))""",
    re.IGNORECASE,
)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _safe_console_write(text: str):
    try:
        print(text)
    except UnicodeEncodeError:
        # Windows consoles often use cp1252; never let a diagnostic crash a task.
        print(text.encode("ascii", "backslashreplace").decode("ascii"))


def log_embed(platform: str, message: str):
    """Write embed diagnostics to the console, as requested for fallbacks."""
    _safe_console_write(f"EmbedFix [{platform}]: {message}")


def log_embed_error(platform: str, label: str, exc: BaseException):
    _safe_console_write(f"EmbedFix [{platform}]: {label} failed: {exc!r}")


def _clean_url(url: str) -> str:
    if not url:
        return ""
    return html_module.unescape(str(url)).replace("&amp;", "&").strip()


def _format_duration(seconds) -> str:
    try:
        total = int(float(seconds))
    except (TypeError, ValueError):
        return ""
    if total <= 0:
        return ""
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _format_stat_value(value) -> str:
    if isinstance(value, str):
        return value
    return _format_count(value)


def _format_stats(post: dict) -> str:
    parts = []
    for emoji, value in post.get("stats") or []:
        if value is None or value == "":
            continue
        parts.append(f"{emoji} {_format_stat_value(value)}")
    return "   ".join(parts)


def _parse_meta(html_text: str) -> dict:
    """Extract OpenGraph/Twitter metadata from an HTML document."""
    meta = {}
    for match in _META_TAG_RE.finditer(html_text or ""):
        attrs = {}
        for attr in _META_ATTR_RE.finditer(match.group(0)):
            value = attr.group(2) or attr.group(3) or attr.group(4) or ""
            attrs[attr.group(1).lower()] = html_module.unescape(value)
        key = attrs.get("property") or attrs.get("name")
        if key and attrs.get("content"):
            meta[key.lower()] = attrs["content"].strip()

    page_title = ""
    title_match = _TITLE_RE.search(html_text or "")
    if title_match:
        page_title = html_module.unescape(title_match.group(1)).strip()

    def pick(*keys):
        for key in keys:
            if meta.get(key):
                return meta[key]
        return ""

    return {
        "title": pick("og:title", "twitter:title") or page_title,
        "description": pick("og:description", "twitter:description", "description"),
        "image": pick("og:image", "og:image:secure_url", "twitter:image"),
        "video": pick("og:video", "og:video:secure_url", "twitter:player:stream"),
        "url": pick("og:url", "twitter:url"),
        "site_name": pick("og:site_name"),
        "page_title": page_title,
    }


def parse_og(html_text: str) -> dict:
    return _parse_meta(html_text)


async def fetch_text(
    session: aiohttp.ClientSession,
    url: str,
    platform: str,
    *,
    headers: dict = None,
    label: str = "request",
    timeout: float = 8,
):
    try:
        async with session.get(
            url,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout),
            allow_redirects=True,
        ) as resp:
            if resp.status != 200:
                log_embed(platform, f"{label} returned HTTP {resp.status}")
                return None
            return await resp.text()
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, UnicodeError) as exc:
        log_embed_error(platform, label, exc)
        return None


async def fetch_json(
    session: aiohttp.ClientSession,
    url: str,
    platform: str,
    *,
    headers: dict = None,
    label: str = "request",
    timeout: float = 8,
):
    try:
        async with session.get(
            url,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout),
            allow_redirects=True,
        ) as resp:
            if resp.status != 200:
                log_embed(platform, f"{label} returned HTTP {resp.status}")
                return None
            try:
                return await resp.json(content_type=None)
            except ValueError as exc:
                log_embed_error(platform, f"{label} (invalid JSON)", exc)
                return None
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, UnicodeError) as exc:
        log_embed_error(platform, label, exc)
        return None


async def resolve_redirect(
    session: aiohttp.ClientSession,
    url: str,
    platform: str,
    *,
    headers: dict = None,
    label: str = "redirect",
    timeout: float = 8,
):
    try:
        async with session.get(
            url,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout),
            allow_redirects=True,
        ) as resp:
            final_url = str(resp.url)
            resp.release()
            if resp.status >= 400:
                log_embed(platform, f"{label} returned HTTP {resp.status}")
                return None
            return final_url if final_url and final_url != url else None
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        log_embed_error(platform, label, exc)
        return None


def extract_json_object(text: str, start_index: int = 0):
    """Return the first balanced ``{...}`` object at/after ``start_index``."""
    brace = text.find("{", start_index)
    if brace < 0:
        return None

    depth = 0
    in_string = False
    escaped = False
    for index in range(brace, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[brace : index + 1]
    return None


def find_nested_key(obj, key: str):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for value in obj.values():
            found = find_nested_key(value, key)
            if found is not None:
                return found
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            found = find_nested_key(value, key)
            if found is not None:
                return found
    return None


def deep_unescape(text: str, rounds: int = 8) -> str:
    """Collapse the multiple escaping layers Instagram/Threads pages use."""
    for _ in range(rounds):
        updated = re.sub(r'\\(["\\/])', r"\1", text)
        if updated == text:
            break
        text = updated
    return text


def make_post(**kwargs) -> dict:
    post = {
        "platform": "",
        "url": "",
        "id": "",
        "author_name": "",
        "author_handle": "",
        "author_url": "",
        "author_avatar": "",
        "author_verified": False,
        "context": "",
        "context_label": "",
        "headline": "",
        "body": "",
        "images": [],
        "videos": [],
        "video_url": "",
        "video_thumbnail": "",
        "media_headers": None,
        "stats": [],
        "fields": [],
        "created": None,
        "footer": "",
        "color": 0,
        "nsfw": False,
        "spoiler": False,
    }
    post.update({key: value for key, value in kwargs.items() if value is not None})
    post["images"] = [url for url in (post.get("images") or []) if url]
    post["stats"] = [
        (emoji, value)
        for emoji, value in (post.get("stats") or [])
        if value is not None and value != ""
    ]
    post["fields"] = [
        tuple(field[:3]) if len(field) >= 3 else (field[0], field[1], False)
        for field in (post.get("fields") or [])
        if field and len(field) >= 2
    ]
    return post


def _plain_author_name(post: dict) -> str:
    name = post.get("author_name") or post.get("author_handle") or post.get("platform") or "Unknown"
    handle = post.get("author_handle")
    text = str(name)
    if handle:
        handle = str(handle)
        # Avoid "pschrager (@pschrager)" when the API only gives a username.
        if handle.lstrip("@").lower() != text.lower():
            prefix = "" if handle.startswith(("u/", "@")) else "@"
            text += f" ({prefix}{handle})"
    if post.get("author_verified"):
        text += " ✔️"
    return text


def _author_identity(post: dict) -> str:
    name = post.get("author_name") or post.get("author_handle") or post.get("platform") or "Unknown"
    handle = post.get("author_handle")
    identity = f"**{discord.utils.escape_markdown(str(name))}**"
    if handle:
        handle = str(handle)
        if handle.lstrip("@").lower() != str(name).lower():
            prefix = "" if handle.startswith(("u/", "@")) else "@"
            identity += f" ({prefix}{discord.utils.escape_markdown(handle)})"
    if post.get("author_verified"):
        identity += " ✔️"
    if post.get("context"):
        identity += f"\n-# {post['context']}"
    return identity


def _post_body(post: dict) -> str:
    parts = []
    if post.get("headline"):
        parts.append(f"**{post['headline']}**")
    if post.get("body"):
        parts.append(str(post["body"]))
    return "\n\n".join(parts)


def _post_field_lines(post: dict) -> list:
    lines = []
    for name, value, _inline in post.get("fields") or []:
        if name and value:
            lines.append(f"**{name}**\n{value}")
    return lines


def _video_entries(post: dict) -> list:
    """Return every video/GIF attached to a post as ``(url, type, thumbnail)``."""
    entries = []
    seen = set()
    for video in post.get("videos") or []:
        if isinstance(video, dict):
            url = video.get("url")
            media_type = str(video.get("type") or "video").lower()
            thumbnail = video.get("thumbnail") or ""
        else:
            url = str(video)
            media_type = "video"
            thumbnail = ""
        if not url or url in seen:
            continue
        seen.add(url)
        entries.append((url, media_type, thumbnail))

    primary = post.get("video_url")
    if primary and primary not in seen:
        entries.insert(0, (primary, "video", post.get("video_thumbnail") or ""))
    return entries


def _gallery_items(post: dict) -> list:
    author = post.get("author_name") or post.get("platform") or "post"
    items = []
    seen = set()

    for video_url, media_type, _thumbnail in _video_entries(post):
        if video_url in seen:
            continue
        seen.add(video_url)
        label = "Animated GIF" if media_type in ("gif", "animated_gif") else "Video"
        items.append(
            discord.MediaGalleryItem(
                video_url,
                description=_truncate(f"{label} from {author}", 256),
            )
        )

    for image in post.get("images") or []:
        if not image or image in seen:
            continue
        seen.add(image)
        items.append(
            discord.MediaGalleryItem(
                image,
                description=_truncate(f"Image from {author}", 256),
            )
        )

    if not items and post.get("video_thumbnail"):
        thumbnail = post["video_thumbnail"]
        items.append(
            discord.MediaGalleryItem(
                thumbnail,
                description=_truncate(f"Preview from {author}", 256),
            )
        )

    return items[:10]


def build_embed(post: dict, color=None) -> discord.Embed:
    accent = color if color is not None else post.get("color") or discord.Color.random()
    if not isinstance(accent, discord.Color):
        accent = discord.Color(accent)

    embed = discord.Embed(color=accent)
    embed.url = post.get("url") or None
    embed.set_author(
        name=_truncate(_plain_author_name(post), 256),
        url=post.get("author_url") or post.get("url") or None,
        icon_url=post.get("author_avatar") or None,
    )

    if post.get("headline"):
        embed.title = _truncate(str(post["headline"]), 256)
    if post.get("body"):
        embed.description = _truncate(str(post["body"]), 4096)

    if post.get("context"):
        embed.add_field(
            name=_truncate(post.get("context_label") or "Info", 256),
            value=_truncate(str(post["context"]), 1024),
            inline=True,
        )

    for name, value, inline in post.get("fields") or []:
        if not name or not value:
            continue
        embed.add_field(
            name=_truncate(str(name), 256),
            value=_truncate(str(value), 1024),
            inline=bool(inline),
        )

    image = (post.get("images") or [None])[0]
    if not image:
        for _url, _type, thumbnail in _video_entries(post):
            if thumbnail:
                image = thumbnail
                break
    if not image:
        image = post.get("video_thumbnail")
    if image:
        embed.set_image(url=image)

    stats = _format_stats(post)
    footer = stats
    if post.get("platform"):
        footer = f"{footer}   •   {post['platform']}" if footer else post["platform"]
    if footer:
        embed.set_footer(text=_truncate(footer, 2048))

    created = post.get("created")
    if created:
        try:
            embed.timestamp = datetime.fromtimestamp(int(created), tz=timezone.utc)
        except (TypeError, ValueError, OSError, OverflowError):
            pass

    return embed


def build_layout_container(post: dict, color=None):
    accent = color if color is not None else post.get("color") or discord.Color.random().value
    if isinstance(accent, discord.Color):
        accent = accent.value

    header = _author_identity(post)
    body = _post_body(post)
    if body:
        header = f"{header}\n\n{body}"
    header = _truncate(header, 3000)

    children = []
    avatar = post.get("author_avatar")
    if avatar:
        children.append(
            discord.ui.Section(
                header,
                accessory=discord.ui.Thumbnail(
                    avatar,
                    description=_truncate(f"{post.get('author_name') or 'Author'} profile photo", 128),
                ),
            )
        )
    else:
        children.append(discord.ui.TextDisplay(header))

    gallery = _gallery_items(post)
    if gallery:
        children.append(discord.ui.MediaGallery(*gallery))

    field_lines = _post_field_lines(post)
    if field_lines:
        children.append(discord.ui.TextDisplay(_truncate("\n".join(field_lines), 1200)))

    stats = _format_stats(post)
    if stats:
        children.append(discord.ui.Separator())
        children.append(discord.ui.TextDisplay(f"-# {stats}"))

    credit = f"-# {post.get('platform') or 'Social'} embed"
    created = post.get("created")
    if created:
        try:
            credit += f" • <t:{int(created)}:R>"
        except (TypeError, ValueError):
            pass
    children.append(discord.ui.TextDisplay(credit))

    return discord.ui.Container(*children, accent_color=accent)


class RichReplyView(discord.ui.View):
    """Classic rich-embed view with a link and author/moderator delete button."""

    def __init__(
        self,
        cog,
        post_url: str,
        author_id: int,
        original_message_id: int = None,
        timeout: float = None,
    ):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.tracker = cog.tracker
        self.author_id = author_id
        self.original_message_id = original_message_id

        if post_url:
            self.add_item(
                discord.ui.Button(
                    label="View post",
                    style=discord.ButtonStyle.link,
                    url=post_url,
                    emoji="🔗",
                    row=0,
                )
            )

        delete_button = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            emoji="🗑️",
            row=0,
        )
        delete_button.callback = self.handle_delete
        self.add_item(delete_button)

    async def handle_delete(self, interaction: discord.Interaction):
        if not self.tracker.can_delete(interaction, self.author_id):
            await interaction.response.send_message(
                "Only the original author or moderators can delete this.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        if self.original_message_id:
            await self.tracker.delete_tracked_reply(
                self.original_message_id,
                exclude_id=getattr(interaction.message, "id", None),
            )
        try:
            await interaction.message.delete()
        except discord.HTTPException as exc:
            log_embed(self.cog.PLATFORM, f"could not delete embed: {exc}")


class RichLayoutView(_LayoutViewBase):
    """Components V2 card whose MediaGallery can play videos inline."""

    def __init__(
        self,
        cog,
        post: dict,
        author_id: int,
        original_message_id: int = None,
        color=None,
    ):
        super().__init__(timeout=None)
        self.cog = cog
        self.tracker = cog.tracker
        self.author_id = author_id
        self.original_message_id = original_message_id

        self.add_item(build_layout_container(post, color))

        row = discord.ui.ActionRow()
        if post.get("url"):
            row.add_item(
                discord.ui.Button(
                    label="View post",
                    style=discord.ButtonStyle.link,
                    url=post["url"],
                    emoji="🔗",
                )
            )
        delete_button = discord.ui.Button(style=discord.ButtonStyle.danger, emoji="🗑️")
        delete_button.callback = self.handle_delete
        row.add_item(delete_button)
        self.add_item(row)

    async def handle_delete(self, interaction: discord.Interaction):
        if not self.tracker.can_delete(interaction, self.author_id):
            await interaction.response.send_message(
                "Only the original author or moderators can delete this.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        if self.original_message_id:
            await self.tracker.delete_tracked_reply(
                self.original_message_id,
                exclude_id=getattr(interaction.message, "id", None),
            )
        try:
            await interaction.message.delete()
        except discord.HTTPException as exc:
            log_embed(self.cog.PLATFORM, f"could not delete embed: {exc}")


def upload_limit(guild) -> int:
    default = 8 * 1024 * 1024
    if guild is None:
        return default
    limit = getattr(guild, "filesize_limit", None) or default
    return min(limit, MAX_VIDEO_BYTES)


def can_attach(ctx) -> bool:
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


async def download_media(
    session: aiohttp.ClientSession,
    url: str,
    limit: int,
    platform: str,
    *,
    headers: dict = None,
):
    try:
        async with session.get(
            url,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status != 200:
                log_embed(platform, f"video download returned HTTP {resp.status}")
                return None
            if resp.content_length and resp.content_length > limit:
                log_embed(
                    platform,
                    f"video is larger than the upload limit "
                    f"({resp.content_length} > {limit} bytes)",
                )
                return None

            buffer = io.BytesIO()
            async for chunk in resp.content.iter_chunked(64 * 1024):
                if not chunk:
                    continue
                buffer.write(chunk)
                if buffer.tell() > limit:
                    log_embed(platform, "video exceeded the upload limit while downloading")
                    return None
            if buffer.tell() == 0:
                log_embed(platform, "video download was empty")
                return None
            buffer.seek(0)
            return buffer
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        log_embed_error(platform, "video download", exc)
        return None


class RichLinkPlatform(LinkPlatform):
    """Base class for platforms that render a native Discord card.

    Subclasses only need to provide ``PLATFORM``, ``COLOR``, ``URL_PATTERN``,
    ``parse_link`` and ``fetch_post``. Fetch failures automatically fall back
    to the FixEmbed/proxy embed-site behavior.
    """

    PLATFORM = ""
    COLOR = 0
    URL_PATTERN = None

    def __init__(self, bot):
        super().__init__(bot)
        self.tracker = get_tracker(bot)

    def find_link(self, content: str, allow_wrapped: bool = False):
        if self.URL_PATTERN is None:
            return None
        for match in self.URL_PATTERN.finditer(content or ""):
            if not allow_wrapped and is_wrapped(content, match):
                continue
            url = match.group(0).rstrip(TRAILING_PUNCTUATION)
            info = self.parse_link(url)
            if info:
                return url, info
        return None

    def parse_link(self, url: str):
        return None

    def canonical_url(self, info: dict):
        return None

    async def fetch_post(self, session: aiohttp.ClientSession, url: str, info: dict):
        raise NotImplementedError

    async def fallback_url(self, session: aiohttp.ClientSession, url: str) -> str:
        return await resolve_embed_site(session, url, self.DOMAIN)

    async def _reply_with_fallback(self, message, session, url: str):
        fixed = await self.fallback_url(session, url)
        try:
            reply = await message.reply(
                content=fixed,
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException as exc:
            log_embed(self.PLATFORM, f"could not send fallback link: {exc}")
            return
        self.tracker.track_reply(message.id, message.channel.id, reply.id)

    async def _send_post(
        self,
        sender,
        post: dict,
        *,
        guild,
        session,
        allow_file: bool = True,
        author_id: int = 0,
        original_message_id: int = None,
        color=None,
    ):
        accent = color if color is not None else post.get("color")

        if COMPONENTS_V2:
            try:
                view = RichLayoutView(
                    self,
                    post,
                    author_id,
                    original_message_id,
                    accent,
                )
                reply = await sender(
                    view=view,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                return reply, None
            except discord.HTTPException as exc:
                log_embed(
                    self.PLATFORM,
                    f"Components V2 card failed, falling back to a classic embed ({exc}).",
                )
            except Exception as exc:
                log_embed_error(self.PLATFORM, "Components V2 card", exc)

        embed = build_embed(post, accent)
        view = RichReplyView(
            self,
            post.get("url"),
            author_id,
            original_message_id,
        )

        file = None
        video_entries = _video_entries(post)
        video_url = video_entries[0][0] if video_entries else None
        if video_url and allow_file:
            buffer = await download_media(
                session,
                video_url,
                upload_limit(guild),
                self.PLATFORM,
                headers=post.get("media_headers"),
            )
            if buffer is not None:
                file = discord.File(buffer, filename="video.mp4")

        payload = {
            "embed": embed,
            "view": view,
            "allowed_mentions": discord.AllowedMentions.none(),
        }

        reply = None
        if file is not None:
            try:
                reply = await sender(file=file, **payload)
            except discord.HTTPException as exc:
                log_embed(
                    self.PLATFORM,
                    f"video attachment failed, retrying without it ({exc}).",
                )
                reply = None

        if reply is None:
            try:
                reply = await sender(**payload)
            except discord.HTTPException as exc:
                log_embed(self.PLATFORM, f"could not send classic embed: {exc}")
                return None, None

        video_post = None
        if video_url and file is None:
            try:
                video_post = await sender(
                    content=video_url,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException as exc:
                log_embed(self.PLATFORM, f"could not post direct video link: {exc}")

        return reply, video_post

    async def handle_message(self, message: discord.Message, url: str = None, info: dict = None):
        if url is None:
            found = self.find_link(message.content)
            if not found:
                return False
            url, info = found
        elif info is None:
            info = self.parse_link(url)

        if not info:
            return False

        perms = self.tracker.bot_permissions(message.channel, message.guild)
        if perms is None or not perms.send_messages:
            return True

        session, close_session = get_session(self.bot)
        try:
            if not perms.embed_links:
                log_embed(
                    self.PLATFORM,
                    "missing Embed Links permission; using proxy link fallback.",
                )
                await self._reply_with_fallback(message, session, url)
                return True

            async with message.channel.typing():
                try:
                    post = await self.fetch_post(session, url, info)
                except Exception as exc:
                    log_embed_error(self.PLATFORM, "rich embed fetch", exc)
                    post = None

                if post is None:
                    log_embed(
                        self.PLATFORM,
                        f"could not build a rich card for {url}; using proxy link fallback.",
                    )
                    await self._reply_with_fallback(message, session, url)
                    return True

                fallback_target = post.get("url") or url
                try:
                    reply, video_post = await self._send_post(
                        lambda **kwargs: message.reply(mention_author=False, **kwargs),
                        post,
                        guild=message.guild,
                        session=session,
                        allow_file=bool(getattr(perms, "attach_files", False)),
                        author_id=message.author.id,
                        original_message_id=message.id,
                    )
                except Exception as exc:
                    log_embed_error(self.PLATFORM, "sending rich embed", exc)
                    await self._reply_with_fallback(message, session, fallback_target)
                    return True

                if reply is None:
                    await self._reply_with_fallback(message, session, fallback_target)
                    return True

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

        return True

    async def handle_command(self, ctx: commands.Context, url: str = None, info: dict = None):
        if url is None:
            found = self.find_link(ctx.message.content if ctx.message else "", allow_wrapped=True)
            if not found:
                return False
            url, info = found
        elif info is None:
            info = self.parse_link(url)

        if not info:
            return False

        session, close_session = get_session(self.bot)
        try:
            perms = self.tracker.bot_permissions(ctx.channel, ctx.guild)
            if perms is not None and not perms.embed_links:
                log_embed(
                    self.PLATFORM,
                    "missing Embed Links permission; using proxy link fallback.",
                )
                fixed = await self.fallback_url(session, url)
                await ctx.send(fixed)
                return True

            try:
                post = await self.fetch_post(session, url, info)
            except Exception as exc:
                log_embed_error(self.PLATFORM, "rich embed fetch", exc)
                post = None

            if post is None:
                log_embed(
                    self.PLATFORM,
                    f"could not build a rich card for {url}; using proxy link fallback.",
                )
                fixed = await self.fallback_url(session, url)
                await ctx.send(fixed)
                return True

            try:
                reply, _ = await self._send_post(
                    ctx.send,
                    post,
                    guild=ctx.guild,
                    session=session,
                    allow_file=can_attach(ctx),
                    author_id=ctx.author.id,
                )
            except Exception as exc:
                log_embed_error(self.PLATFORM, "sending rich embed", exc)
                reply = None

            if reply is None:
                fixed = await self.fallback_url(session, post.get("url") or url)
                await ctx.send(fixed)
        finally:
            if close_session and session and not session.closed:
                await session.close()

        return True
