import logging
import re
from urllib.parse import urlsplit

from discord.ext import commands

from ._embed_common import (
    DISCORD_BOT_UA,
    FACEBOOK_BOT_UA,
    GOOGLEBOT_UA,
    RichLinkPlatform,
    _clean_url,
    fetch_text,
    log_embed,
    make_post,
    parse_og,
    resolve_redirect,
)

log = logging.getLogger("arex.threads_embed")



THREADS_URL_PATTERN = re.compile(
    r"https?://(?:[a-z0-9-]+\.)*(?:threads\.net|threads\.com)(?:/[^\s<>`]*)?",
    re.IGNORECASE,
)
THREADS_POST_PATH = re.compile(
    r"/@([^/]+)/post/([A-Za-z0-9_-]+)", re.IGNORECASE
)
THREADS_SHORT_PATH = re.compile(r"/t/([A-Za-z0-9_-]+)", re.IGNORECASE)
THREADS_TITLE = re.compile(r"^(?P<name>.+?)\s*\(@(?P<handle>[^)]+)\)\s+on\s+Threads$", re.IGNORECASE)

# Threads serves a login wall to regular browsers, but the Meta and Google
# crawlers receive the post's public OpenGraph tags.
THREADS_USER_AGENTS = [
    (FACEBOOK_BOT_UA, "Meta crawler"),
    (GOOGLEBOT_UA, "Googlebot"),
    (DISCORD_BOT_UA, "Discordbot"),
]


class ThreadsEmbed(RichLinkPlatform):
    """Render Threads posts as native cards using public OpenGraph data."""

    DOMAIN = "threads.net"
    PLATFORM = "Threads"
    COLOR = 0x000000
    URL_PATTERN = THREADS_URL_PATTERN

    def parse_link(self, url: str):
        path = urlsplit(url).path or ""

        match = THREADS_POST_PATH.search(path)
        if match:
            return {
                "kind": "post",
                "username": match.group(1),
                "id": match.group(2),
            }

        match = THREADS_SHORT_PATH.search(path)
        if match:
            return {"kind": "short", "id": match.group(1)}

        return None

    def canonical_url(self, info: dict):
        post_id = info.get("id")
        username = info.get("username")
        if not post_id:
            return None
        if username:
            return f"https://www.threads.com/@{username}/post/{post_id}"
        return f"https://www.threads.com/t/{post_id}"

    async def fetch_post(self, session, url: str, info: dict):
        canonical = self.canonical_url(info)
        if not canonical:
            return None

        if info.get("kind") == "short":
            resolved = await resolve_redirect(
                session,
                canonical,
                self.PLATFORM,
                headers={"User-Agent": DISCORD_BOT_UA},
                label="Threads short link",
            )
            if resolved:
                canonical = resolved
                info = self.parse_link(resolved) or info

        for user_agent, label in THREADS_USER_AGENTS:
            page = await fetch_text(
                session,
                canonical,
                self.PLATFORM,
                headers={"User-Agent": user_agent},
                label=f"Threads page ({label})",
            )
            if not page:
                continue

            og = parse_og(page)
            post = self._build_post(og, info, canonical)
            if post:
                return post

            log_embed(self.PLATFORM, f"Threads page ({label}) had no post metadata.")

        return None

    def _build_post(self, og: dict, info: dict, canonical: str):
        title = _clean_url(og.get("title") or "")
        description = _clean_url(og.get("description") or "")
        image = _clean_url(og.get("image") or "")
        video = _clean_url(og.get("video") or "")

        # Meta's login wall also has OpenGraph tags; reject those.
        if "log in" in title.lower() or "join threads to share ideas" in description.lower():
            return None
        if not (description or image or video):
            return None

        name = ""
        handle = info.get("username") or ""
        match = THREADS_TITLE.match(title)
        if match:
            name = match.group("name").strip()
            handle = match.group("handle").strip()

        if not name:
            name = handle or self.PLATFORM

        images = []
        if video:
            thumbnail = image
        else:
            thumbnail = image
            if image:
                images.append(image)

        post_url = _clean_url(og.get("url") or "") or canonical
        if post_url.startswith("https://www.threads.net/"):
            post_url = post_url.replace("https://www.threads.net/", "https://www.threads.com/", 1)

        return make_post(
            platform=self.PLATFORM,
            url=post_url,
            id=str(info.get("id") or ""),
            author_name=name,
            author_handle=handle,
            author_url=f"https://www.threads.com/@{handle}" if handle else "",
            body=description,
            images=images,
            video_url=video,
            video_thumbnail=thumbnail,
            media_headers={"Referer": "https://www.threads.com/"},
            stats=[],
            fields=[],
            created=None,
            footer="Threads",
            color=self.COLOR,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ThreadsEmbed(bot))
