import logging
import re
from urllib.parse import quote, urlsplit

from discord.ext import commands

from ._embed_common import (
    DISCORD_BOT_UA,
    RichLinkPlatform,
    _clean_url,
    _format_duration,
    fetch_json,
    fetch_text,
    log_embed,
    make_post,
    parse_og,
    resolve_redirect,
)

log = logging.getLogger("arex.tiktok_embed")



TIKTOK_URL_PATTERN = re.compile(
    r"https?://(?:[a-z0-9-]+\.)*(?:tiktok\.com)(?:/[^\s<>`]*)?",
    re.IGNORECASE,
)
TIKTOK_POST_PATH = re.compile(r"/@([^/]+)/(video|photo)/(\d+)", re.IGNORECASE)
TIKTOK_OLD_VIDEO_PATH = re.compile(r"/v/(\d+)\.html", re.IGNORECASE)


class TikTokEmbed(RichLinkPlatform):
    """Render TikTok posts as native cards, with a proxy-link fallback."""

    DOMAIN = "tiktok.com"
    PLATFORM = "TikTok"
    COLOR = 0xFE2C55
    URL_PATTERN = TIKTOK_URL_PATTERN

    def parse_link(self, url: str):
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        path = parts.path or ""

        if host in ("vm.tiktok.com", "vt.tiktok.com") or path.startswith("/t/"):
            return {"kind": "short"}

        match = TIKTOK_POST_PATH.search(path)
        if match:
            return {
                "kind": "video",
                "post_type": match.group(2).lower(),
                "username": match.group(1),
                "id": match.group(3),
            }

        match = TIKTOK_OLD_VIDEO_PATH.search(path)
        if match:
            return {"kind": "video", "post_type": "video", "id": match.group(1)}

        return None

    def canonical_url(self, info: dict):
        if info.get("username") and info.get("id"):
            post_type = info.get("post_type") or "video"
            return f"https://www.tiktok.com/@{info['username']}/{post_type}/{info['id']}"
        return None

    async def fetch_post(self, session, url: str, info: dict):
        if info.get("kind") == "short" or not info.get("id"):
            resolved = await resolve_redirect(
                session,
                url,
                self.PLATFORM,
                headers={"User-Agent": DISCORD_BOT_UA},
                label="TikTok short link",
            )
            if resolved:
                url = resolved
                info = self.parse_link(resolved) or info

        if not info.get("id"):
            log_embed(self.PLATFORM, "could not find a video ID in that link.")
            return None

        canonical = self.canonical_url(info) or url

        # Primary: tikwm exposes captions, stats, author info and a direct MP4.
        payload = await fetch_json(
            session,
            f"https://tikwm.com/api/?url={quote(canonical, safe='')}",
            self.PLATFORM,
            headers={"User-Agent": DISCORD_BOT_UA},
            label="tikwm API",
            timeout=10,
        )
        if isinstance(payload, dict) and payload.get("code") == 0:
            data = payload.get("data")
            if isinstance(data, dict):
                return self._from_tikwm(data, canonical)
            log_embed(self.PLATFORM, "tikwm API returned no post data.")
        elif isinstance(payload, dict):
            log_embed(
                self.PLATFORM,
                f"tikwm API error: {payload.get('msg') or payload.get('code')}",
            )

        # Fallback 1: TikTok oEmbed. Some responses include a title/thumbnail.
        oembed = await fetch_json(
            session,
            f"https://www.tiktok.com/oembed?url={quote(canonical, safe='')}",
            self.PLATFORM,
            headers={"User-Agent": DISCORD_BOT_UA},
            label="TikTok oEmbed",
        )
        if isinstance(oembed, dict):
            post = self._from_oembed(oembed, canonical, info)
            if post:
                return post
            log_embed(self.PLATFORM, "TikTok oEmbed returned no usable fields.")

        # Fallback 2: scrape the public OpenGraph tags with a bot user agent.
        page = await fetch_text(
            session,
            canonical,
            self.PLATFORM,
            headers={"User-Agent": DISCORD_BOT_UA},
            label="TikTok page",
        )
        if page:
            post = self._from_og(parse_og(page), canonical, info)
            if post:
                return post

        return None

    def _from_tikwm(self, data: dict, canonical: str):
        author = data.get("author") or {}
        username = author.get("unique_id") or ""
        post_url = canonical or self.canonical_url(
            {"username": username, "id": data.get("id")}
        )

        music_info = data.get("music_info") or {}
        music_title = music_info.get("title") or ""
        music_author = music_info.get("author") or ""
        music = " — ".join(part for part in (music_title, music_author) if part)

        fields = []
        duration = _format_duration(data.get("duration"))
        if duration:
            fields.append(("Duration", duration, True))
        if music:
            fields.append(("Music", music, False))

        return make_post(
            platform=self.PLATFORM,
            url=post_url,
            id=str(data.get("id") or ""),
            author_name=author.get("nickname") or username or self.PLATFORM,
            author_handle=username,
            author_url=f"https://www.tiktok.com/@{username}" if username else "",
            author_avatar=_clean_url(author.get("avatar")),
            body=_clean_url(data.get("title") or ""),
            video_url=_clean_url(data.get("play") or data.get("wmplay") or ""),
            video_thumbnail=_clean_url(
                data.get("cover") or data.get("origin_cover") or ""
            ),
            media_headers={"Referer": "https://www.tiktok.com/"},
            stats=[
                ("❤️", data.get("digg_count")),
                ("💬", data.get("comment_count")),
                ("🔁", data.get("share_count")),
                ("▶️", data.get("play_count")),
            ],
            fields=fields,
            created=data.get("create_time"),
            footer="TikTok",
            color=self.COLOR,
        )

    def _from_oembed(self, data: dict, canonical: str, info: dict):
        title = _clean_url(data.get("title") or "")
        thumbnail = _clean_url(data.get("thumbnail_url") or "")
        author = data.get("author_name") or ""
        if not title and not thumbnail:
            return None

        username = info.get("username") or ""
        author_url = data.get("author_url") or (
            f"https://www.tiktok.com/@{username}" if username else ""
        )

        return make_post(
            platform=self.PLATFORM,
            url=canonical,
            id=str(info.get("id") or ""),
            author_name=author or username or self.PLATFORM,
            author_handle=username,
            author_url=author_url,
            body=title,
            video_thumbnail=thumbnail,
            created=None,
            footer="TikTok",
            color=self.COLOR,
        )

    def _from_og(self, og: dict, canonical: str, info: dict):
        title = og.get("title") or ""
        description = og.get("description") or ""
        image = _clean_url(og.get("image") or "")
        video = _clean_url(og.get("video") or "")

        author = ""
        if "·" in title:
            author = title.split("·", 1)[1].strip()
        elif "|" in title:
            author = title.split("|", 1)[0].strip()

        if not (author or description or image or video):
            return None

        username = info.get("username") or ""
        return make_post(
            platform=self.PLATFORM,
            url=canonical,
            id=str(info.get("id") or ""),
            author_name=author or username or self.PLATFORM,
            author_handle=username,
            author_url=f"https://www.tiktok.com/@{username}" if username else "",
            body=description,
            video_url=video,
            video_thumbnail=image,
            media_headers={"Referer": "https://www.tiktok.com/"},
            created=None,
            footer="TikTok",
            color=self.COLOR,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(TikTokEmbed(bot))
