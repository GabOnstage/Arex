import logging
import re
from urllib.parse import urlsplit

from discord.ext import commands

from ._embed_common import (
    DISCORD_BOT_UA,
    RichLinkPlatform,
    _clean_url,
    fetch_json,
    log_embed,
    make_post,
)

log = logging.getLogger("arex.reddit_embed")



REDDIT_URL_PATTERN = re.compile(
    r"https?://(?:[a-z0-9-]+\.)*(?:reddit\.com|redd\.it)(?:/[^\s<>`]*)?",
    re.IGNORECASE,
)
REDDIT_COMMENT_PATH = re.compile(r"/comments/([A-Za-z0-9]+)", re.IGNORECASE)
REDDIT_SHORT_PATH = re.compile(r"^/([A-Za-z0-9]+)", re.IGNORECASE)


class RedditEmbed(RichLinkPlatform):
    """Render Reddit posts as native cards using the public JSON endpoints."""

    DOMAIN = "reddit.com"
    PLATFORM = "Reddit"
    COLOR = 0xFF4500
    URL_PATTERN = REDDIT_URL_PATTERN

    def parse_link(self, url: str):
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        path = parts.path or ""

        if host == "redd.it" or host.endswith(".redd.it"):
            match = REDDIT_SHORT_PATH.search(path)
            if match:
                return {"kind": "post", "id": match.group(1)}
            return None

        match = REDDIT_COMMENT_PATH.search(path)
        if match:
            return {"kind": "post", "id": match.group(1)}
        return None

    def canonical_url(self, info: dict):
        post_id = info.get("id")
        return f"https://www.reddit.com/comments/{post_id}" if post_id else None

    async def fetch_post(self, session, url: str, info: dict):
        post_id = info.get("id")
        if not post_id:
            return None

        endpoints = [
            (
                f"https://old.reddit.com/comments/{post_id}.json?raw_json=1",
                "Reddit JSON (old.reddit.com)",
            ),
            (
                f"https://api.reddit.com/comments/{post_id}?raw_json=1",
                "Reddit JSON (api.reddit.com)",
            ),
            (
                f"https://www.reddit.com/comments/{post_id}.json?raw_json=1",
                "Reddit JSON (www.reddit.com)",
            ),
        ]

        data = None
        for endpoint, label in endpoints:
            data = await fetch_json(
                session,
                endpoint,
                self.PLATFORM,
                headers={"User-Agent": DISCORD_BOT_UA},
                label=label,
                timeout=10,
            )
            if isinstance(data, list):
                break
            data = None

        if not data:
            log_embed(self.PLATFORM, "all Reddit JSON endpoints failed.")
            return None

        try:
            post = data[0]["data"]["children"][0]["data"]
        except (IndexError, KeyError, TypeError):
            log_embed(self.PLATFORM, "Reddit returned an unexpected JSON shape.")
            return None

        if not isinstance(post, dict):
            log_embed(self.PLATFORM, "Reddit returned no post data.")
            return None

        return self._build_post(post)

    def _build_post(self, data: dict):
        post_id = data.get("id") or ""
        permalink = data.get("permalink") or f"/comments/{post_id}/"
        post_url = f"https://www.reddit.com{permalink}"
        subreddit = data.get("subreddit_name_prefixed") or (
            f"r/{data.get('subreddit')}" if data.get("subreddit") else ""
        )
        author = data.get("author") or "unknown"

        images, video_url, video_thumbnail = self._extract_media(data)

        fields = []
        flair = data.get("link_flair_text")
        if flair:
            fields.append(("Flair", flair, True))

        ratio = data.get("upvote_ratio")
        if isinstance(ratio, (int, float)):
            fields.append(("Upvote ratio", f"{round(ratio * 100)}%", True))

        if data.get("over_18"):
            fields.append(("NSFW", "🔞", True))
        if data.get("spoiler"):
            fields.append(("Spoiler", "⚠️", True))

        if not data.get("is_self") and not images and not video_url:
            link = data.get("url_overridden_by_dest") or data.get("url")
            if link and link != post_url:
                fields.append(("Link", link, False))

        return make_post(
            platform=self.PLATFORM,
            url=post_url,
            id=post_id,
            author_name=author,
            author_url=f"https://www.reddit.com/user/{author}" if author else "",
            context=subreddit,
            context_label="Subreddit",
            headline=data.get("title") or "",
            body=data.get("selftext") or "",
            images=images,
            video_url=video_url,
            video_thumbnail=video_thumbnail,
            stats=[
                ("⬆️", data.get("score")),
                ("💬", data.get("num_comments")),
            ],
            fields=fields,
            created=data.get("created_utc"),
            footer="Reddit",
            color=self.COLOR,
            nsfw=bool(data.get("over_18")),
            spoiler=bool(data.get("spoiler")),
        )

    def _extract_media(self, data: dict):
        source = data
        crossposts = data.get("crosspost_parent_list") or []
        if crossposts and not (
            data.get("is_video")
            or data.get("is_gallery")
            or data.get("post_hint") in ("image", "rich:video")
        ):
            source = crossposts[0] or data

        images = []
        video_url = ""
        video_thumbnail = ""

        # Gallery posts: keep the author's ordering from gallery_data.
        if source.get("is_gallery"):
            metadata = source.get("media_metadata") or {}
            items = (source.get("gallery_data") or {}).get("items") or []
            for item in items:
                media = metadata.get(item.get("media_id")) or {}
                if media.get("status") == "failed":
                    continue
                url = self._metadata_url(media)
                if url:
                    images.append(url)

        # Reddit-hosted video.
        reddit_video = (
            ((source.get("secure_media") or {}).get("reddit_video"))
            or ((source.get("media") or {}).get("reddit_video"))
            or {}
        )
        if reddit_video:
            video_url = _clean_url(reddit_video.get("fallback_url") or "")
            video_thumbnail = self._preview_url(source)

        # Image posts / link previews.
        if not video_url and not images:
            direct = source.get("url_overridden_by_dest") or source.get("url") or ""
            if self._looks_like_image(direct):
                direct = _clean_url(direct)
                if direct:
                    images.append(direct)
            else:
                preview = self._preview_url(source)
                if preview:
                    images.append(preview)

        if not images and not video_thumbnail:
            thumbnail = source.get("thumbnail")
            if thumbnail and thumbnail.startswith("http"):
                video_thumbnail = _clean_url(thumbnail)

        return images[:10], video_url, video_thumbnail

    @staticmethod
    def _metadata_url(media: dict) -> str:
        source = media.get("s") or {}
        for key in ("u", "gif"):
            url = source.get(key)
            if url:
                return _clean_url(url)

        previews = media.get("p") or []
        if previews:
            return _clean_url((previews[-1] or {}).get("u") or "")
        return ""

    @staticmethod
    def _preview_url(data: dict) -> str:
        for image in (data.get("preview") or {}).get("images") or []:
            url = (image.get("source") or {}).get("url")
            if url:
                return _clean_url(url)
        return ""

    @staticmethod
    def _looks_like_image(url: str) -> bool:
        if not url:
            return False
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        path = (parts.path or "").lower()
        if host in ("i.redd.it", "preview.redd.it", "i.imgur.com"):
            return True
        return path.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif"))


async def setup(bot: commands.Bot):
    await bot.add_cog(RedditEmbed(bot))
