import logging
import base64
import html as html_module
import json
import re
from urllib.parse import quote, urlsplit

from discord.ext import commands

from ._embed_common import (
    DISCORD_BOT_UA,
    RichLinkPlatform,
    _clean_url,
    _format_duration,
    deep_unescape,
    extract_json_object,
    fetch_json,
    fetch_text,
    find_nested_key,
    log_embed,
    log_embed_error,
    make_post,
    parse_og,
    resolve_redirect,
)

log = logging.getLogger("arex.insta_embed")



INSTAGRAM_URL_PATTERN = re.compile(
    r"https?://(?:[a-z0-9-]+\.)*(?:instagram\.com|instagr\.am)(?:/[^\s<>`]*)?",
    re.IGNORECASE,
)
INSTAGRAM_PATH_PATTERN = re.compile(
    r"/(p|reel|reels|tv|share)/([A-Za-z0-9_-]+)", re.IGNORECASE
)

# vxinstagram (https://github.com/Lainmode/InstagramEmbed-vxinstagram) does the
# Instagram scraping on its own server and exposes the result as ActivityPub
# JSON. The "d." host is the details variant it uses for crawlers, and the
# /offload route proxies the original CDN media. Hitting that JSON endpoint
# gives us the caption, author, avatar, likes, comments and every media item
# without fighting Instagram's login wall ourselves.
VXINSTAGRAM_DETAILS_HOST = "d.vxinstagram.com"
VXINSTAGRAM_API = f"https://{VXINSTAGRAM_DETAILS_HOST}"
VXINSTAGRAM_MEDIA = f"{VXINSTAGRAM_API}/offload"
VX_MEDIA_BATCH = 4
VX_MEDIA_LIMIT = 10

VX_HEADERS = {
    "User-Agent": DISCORD_BOT_UA,
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
}


def _base64url(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def _activity_url(canonical: str, shortcode: str, order: int = 0) -> str:
    context = _base64url(f"{shortcode}&{order}&{canonical}")
    return f"{VXINSTAGRAM_API}/users/username/statuses/{context}"


def _activity_index(url: str):
    match = re.search(r"[?&]order=(\d+)", url or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _parse_count(value):
    if value is None:
        return None
    text = str(value).replace(",", "").strip()
    match = re.match(r"^([\d.]+)\s*([KMB])?$", text, re.IGNORECASE)
    if not match:
        return None
    try:
        number = float(match.group(1))
    except ValueError:
        return None
    multiplier = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(
        (match.group(2) or "").upper(),
        1,
    )
    return int(number * multiplier)


def _html_to_text(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value or "", flags=re.IGNORECASE)
    value = re.sub(r"</p\s*>", "\n", value, flags=re.IGNORECASE)
    value = re.sub(r"<[^>]+>", "", value)
    value = html_module.unescape(value).replace("\xa0", " ")
    lines = [line.rstrip() for line in value.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _split_caption(content: str):
    text = _html_to_text(content)

    def stat(emoji):
        match = re.search(rf"{emoji}\s*([\d.,]+(?:\s*[KMB])?)", text, re.IGNORECASE)
        return _parse_count(match.group(1)) if match else None

    likes = stat("❤️")
    comments = stat("💬")

    caption = re.sub(r"(?:\n|^)[ \t]*❤️[^\n]*$", "", text, flags=re.DOTALL).strip()
    caption = re.sub(r"(?:\n|^)[ \t]*💬[^\n]*$", "", caption, flags=re.DOTALL).strip()
    return caption, likes, comments


class InstaEmbed(RichLinkPlatform):
    """Render Instagram posts/reels as native cards."""

    DOMAIN = "instagram.com"
    PLATFORM = "Instagram"
    COLOR = 0xE1306C
    URL_PATTERN = INSTAGRAM_URL_PATTERN

    def parse_link(self, url: str):
        path = urlsplit(url).path or ""
        match = INSTAGRAM_PATH_PATTERN.search(path)
        if not match:
            return None

        kind = match.group(1).lower()
        code = match.group(2)
        if kind == "share":
            return {"kind": "short", "shortcode": code}
        if kind == "reels":
            kind = "reel"
        return {"kind": kind, "shortcode": code}

    def canonical_url(self, info: dict):
        kind = info.get("kind")
        code = info.get("shortcode")
        if not code or kind == "short":
            return None
        return f"https://www.instagram.com/{kind}/{code}/"

    async def fetch_post(self, session, url: str, info: dict):
        if info.get("kind") == "short":
            resolved = await resolve_redirect(
                session,
                url,
                self.PLATFORM,
                headers={"User-Agent": DISCORD_BOT_UA},
                label="Instagram short link",
            )
            if resolved:
                url = resolved
                info = self.parse_link(resolved) or info

        canonical = self.canonical_url(info)
        if not canonical:
            log_embed(self.PLATFORM, "could not find a post/reel code in that link.")
            return None

        # Primary: let vxinstagram do the scraping and hand us its ActivityPub
        # JSON (caption, author, avatar, likes/comments and all media items).
        vx_post = await self._fetch_vx_post(session, canonical, info)
        if vx_post:
            return vx_post

        oembed = await fetch_json(
            session,
            f"https://www.instagram.com/api/v1/oembed/?url={quote(canonical, safe='')}",
            self.PLATFORM,
            headers={"User-Agent": DISCORD_BOT_UA},
            label="Instagram oEmbed",
        )
        media = await self._fetch_embed_media(session, info)

        if isinstance(oembed, dict) or media:
            post = self._build_post(
                oembed if isinstance(oembed, dict) else {},
                media or {},
                canonical,
                info,
            )
            if post:
                return post
            log_embed(self.PLATFORM, "Instagram oEmbed/embed page returned no usable fields.")

        # Last resort: scrape the public OpenGraph tags with a bot user agent.
        page = await fetch_text(
            session,
            canonical,
            self.PLATFORM,
            headers={"User-Agent": DISCORD_BOT_UA},
            label="Instagram page",
        )
        if page:
            post = self._from_og(parse_og(page), canonical)
            if post:
                return post

        return None

    async def _fetch_vx_batch(self, session, canonical: str, shortcode: str, order: int):
        data = await fetch_json(
            session,
            _activity_url(canonical, shortcode, order),
            self.PLATFORM,
            headers=VX_HEADERS,
            label=f"vxinstagram ActivityPub (order {order})",
            timeout=20,
        )
        if not isinstance(data, dict):
            return None
        return data

    async def _fetch_vx_post(self, session, canonical: str, info: dict):
        shortcode = info.get("shortcode")
        if not shortcode:
            return None

        first = await self._fetch_vx_batch(session, canonical, shortcode, 0)
        if first is None:
            return None

        attachments = list(first.get("media_attachments") or [])
        ordered = []
        seen = set()

        def collect(items):
            added = 0
            for attachment in items:
                if not isinstance(attachment, dict):
                    continue
                index = _activity_index(attachment.get("url") or "")
                key = index if index is not None else attachment.get("url")
                if key is None or key in seen:
                    continue
                seen.add(key)
                ordered.append((index, attachment))
                added += 1
            return added

        collect(attachments)

        # The ActivityPub endpoint only returns four media items per request.
        # Walk the album in batches until it wraps around or Discord's gallery
        # limit is reached.
        next_order = VX_MEDIA_BATCH
        while (
            len(ordered) < VX_MEDIA_LIMIT
            and len(attachments) >= VX_MEDIA_BATCH
            and next_order < 20
        ):
            batch = await self._fetch_vx_batch(session, canonical, shortcode, next_order)
            if batch is None:
                break
            batch_media = list(batch.get("media_attachments") or [])
            if collect(batch_media) == 0:
                break
            next_order += VX_MEDIA_BATCH

        post = self._build_vx_post(first, ordered, canonical, info)
        if post is None:
            log_embed(self.PLATFORM, "vxinstagram returned no usable post fields.")
        return post

    def _build_vx_post(self, data: dict, media_items: list, canonical: str, info: dict):
        account = data.get("account") or {}
        username = account.get("username") or info.get("username") or ""
        name = account.get("display_name") or username
        avatar = _clean_url(account.get("avatar") or account.get("avatar_static") or "")
        author_url = account.get("url") or (
            f"https://www.instagram.com/{username}/" if username else ""
        )

        caption, likes, comments = _split_caption(data.get("content") or "")

        images = []
        videos = []
        for index, attachment in media_items:
            if index is None:
                index = len(images) + len(videos)
            media_type = str(attachment.get("type") or "image").lower()
            if media_type == "video":
                videos.append(
                    {
                        "url": f"{VXINSTAGRAM_MEDIA}/{quote(str(info.get('shortcode')), safe='')}/{index}.mp4",
                        "thumbnail": _clean_url(
                            attachment.get("preview_url")
                            or f"{VXINSTAGRAM_MEDIA}/{quote(str(info.get('shortcode')), safe='')}/{index}?thumbnail=true"
                        ),
                        "type": "video",
                    }
                )
            else:
                images.append(
                    f"{VXINSTAGRAM_MEDIA}/{quote(str(info.get('shortcode')), safe='')}/{index}"
                )

        if not (username or caption or images or videos):
            return None

        video_url = videos[0]["url"] if videos else ""
        video_thumbnail = videos[0]["thumbnail"] if videos else ""

        return make_post(
            platform=self.PLATFORM,
            url=canonical,
            id=str(info.get("shortcode") or ""),
            author_name=name or self.PLATFORM,
            author_handle=username,
            author_url=author_url,
            author_avatar=avatar,
            body=caption,
            images=images[:VX_MEDIA_LIMIT],
            videos=videos[:VX_MEDIA_LIMIT],
            video_url=video_url,
            video_thumbnail=video_thumbnail,
            media_headers={"Referer": "https://www.instagram.com/"},
            stats=[("❤️", likes), ("💬", comments)],
            footer="Instagram",
            color=self.COLOR,
        )

    async def _fetch_embed_media(self, session, info: dict):
        kind = info.get("kind") or "p"
        code = info.get("shortcode")
        if not code:
            return None

        embed_url = f"https://www.instagram.com/{kind}/{code}/embed/captioned/"
        text = await fetch_text(
            session,
            embed_url,
            self.PLATFORM,
            headers={"User-Agent": DISCORD_BOT_UA},
            label="Instagram embed page",
        )
        if not text:
            return None

        try:
            media = self._parse_bootloader(text)
        except Exception as exc:
            log_embed_error(self.PLATFORM, "Instagram embed JSON", exc)
            media = None

        if media:
            return media

        log_embed(
            self.PLATFORM,
            "embed page JSON could not be parsed; trying text extraction.",
        )
        return self._parse_embed_text(text)

    @staticmethod
    def _parse_bootloader(html_text: str):
        index = html_text.rfind("s.handle(")
        if index < 0:
            return None
        payload = extract_json_object(html_text, index)
        if not payload:
            return None

        bootloader = json.loads(payload)
        context = find_nested_key(bootloader, "contextJSON")
        if not isinstance(context, str):
            return None

        data = json.loads(context)
        media = (data.get("gql_data") or {}).get("shortcode_media")
        if not isinstance(media, dict):
            return None
        return InstaEmbed._normalize_media(media)

    @staticmethod
    def _normalize_media(media: dict):
        owner = media.get("owner") or {}
        children = []
        for edge in (media.get("edge_sidecar_to_children") or {}).get("edges") or []:
            node = (edge or {}).get("node") or {}
            if node:
                children.append(node)

        images = []
        video_url = _clean_url(media.get("video_url") or "")
        for child in children:
            if child.get("is_video") and not video_url:
                video_url = _clean_url(child.get("video_url") or "")
            image = _clean_url(child.get("display_url") or "")
            if image:
                images.append(image)

        display_url = _clean_url(media.get("display_url") or "")
        if not images and display_url:
            images.append(display_url)

        likes = (media.get("edge_media_preview_like") or {}).get("count")
        if likes is None:
            likes = (media.get("edge_liked_by") or {}).get("count")

        caption = ""
        caption_edges = (media.get("edge_media_to_caption") or {}).get("edges") or []
        if caption_edges:
            caption = (
                ((caption_edges[0] or {}).get("node") or {}).get("text") or ""
            )

        return {
            "caption": _clean_url(caption),
            "owner_username": owner.get("username") or "",
            "owner_name": owner.get("full_name") or "",
            "owner_avatar": _clean_url(owner.get("profile_pic_url") or ""),
            "verified": bool(owner.get("is_verified")),
            "video_url": video_url,
            "display_url": display_url,
            "images": images,
            "likes": likes,
            "comments": (media.get("edge_media_to_comment") or {}).get("count"),
            "views": media.get("video_view_count"),
            "created": media.get("taken_at_timestamp"),
            "duration": media.get("video_duration"),
        }

    @staticmethod
    def _parse_embed_text(html_text: str):
        text = deep_unescape(html_text)

        def first(pattern):
            match = re.search(pattern, text, re.DOTALL)
            return match.group(1) if match else ""

        display_url = _clean_url(first(r'"display_url"\s*:\s*"([^"]+)"'))
        video_url = _clean_url(first(r'"video_url"\s*:\s*"([^"]+)"'))
        owner_match = re.search(
            r'"owner"\s*:\s*\{[^{}]*?"id"\s*:\s*"[^"]*"[^{}]*?'
            r'"username"\s*:\s*"([^"]*)"[^{}]*?'
            r'"is_verified"\s*:\s*(true|false)',
            text,
            re.DOTALL,
        )
        username = owner_match.group(1) if owner_match else ""
        verified = bool(owner_match and owner_match.group(2) == "true")

        likes = first(r'"edge_media_preview_like"\s*:\s*\{[^{}]*?"count"\s*:\s*(\d+)')
        if not likes:
            likes = first(r'"edge_liked_by"\s*:\s*\{[^{}]*?"count"\s*:\s*(\d+)')
        comments = first(r'"edge_media_to_comment"\s*:\s*\{[^{}]*?"count"\s*:\s*(\d+)')
        views = first(r'"video_view_count"\s*:\s*(\d+)')
        duration = first(r'"video_duration"\s*:\s*([\d.]+)')
        created = first(r'"taken_at_timestamp"\s*:\s*(\d+)')

        if not (display_url or video_url or username):
            return None

        return {
            "caption": "",
            "owner_username": username,
            "owner_name": username,
            "owner_avatar": "",
            "verified": verified,
            "video_url": video_url,
            "display_url": display_url,
            "images": [display_url] if display_url else [],
            "likes": int(likes) if likes else None,
            "comments": int(comments) if comments else None,
            "views": int(views) if views else None,
            "created": int(created) if created else None,
            "duration": float(duration) if duration else None,
        }

    def _build_post(self, oembed: dict, media: dict, canonical: str, info: dict):
        username = (
            media.get("owner_username")
            or oembed.get("author_name")
            or info.get("username")
            or ""
        )
        name = media.get("owner_name") or oembed.get("author_name") or username
        author_url = oembed.get("author_url") or (
            f"https://www.instagram.com/{username}/" if username else ""
        )

        caption = media.get("caption") or _clean_url(oembed.get("title") or "")
        thumbnail = media.get("display_url") or _clean_url(
            oembed.get("thumbnail_url") or ""
        )
        images = list(media.get("images") or [])
        if not images and thumbnail:
            images = [thumbnail]

        video_url = media.get("video_url") or ""
        if video_url:
            # The first image is usually the video poster; the video item
            # already carries that preview in Discord's gallery.
            images = [image for image in images if image != thumbnail]

        if not (name or caption or images or video_url):
            return None

        fields = []
        duration = _format_duration(media.get("duration"))
        if duration:
            fields.append(("Duration", duration, True))

        stats = [
            ("❤️", media.get("likes")),
            ("💬", media.get("comments")),
            ("▶️", media.get("views")),
        ]

        return make_post(
            platform=self.PLATFORM,
            url=canonical,
            id=str(info.get("shortcode") or ""),
            author_name=name or self.PLATFORM,
            author_handle=username,
            author_url=author_url,
            author_avatar=media.get("owner_avatar") or "",
            author_verified=bool(media.get("verified")),
            body=caption,
            images=images,
            video_url=video_url,
            video_thumbnail=thumbnail,
            media_headers={"Referer": "https://www.instagram.com/"},
            stats=stats,
            fields=fields,
            created=media.get("created"),
            footer="Instagram",
            color=self.COLOR,
        )

    def _from_og(self, og: dict, canonical: str):
        description = _clean_url(og.get("description") or "")
        image = _clean_url(og.get("image") or "")
        video = _clean_url(og.get("video") or "")
        if not (description or image or video):
            return None

        username = ""
        body = description
        likes = comments = None
        match = re.match(
            r"([\d,]+)\s+likes?,\s*([\d,]+)\s+comments?\s*-\s*"
            r"([^\s]+)\s+on\s+([^:]+):\s*(.*)",
            description,
            re.DOTALL,
        )
        if match:
            likes = int(match.group(1).replace(",", ""))
            comments = int(match.group(2).replace(",", ""))
            username = match.group(3)
            body = match.group(5)

        return make_post(
            platform=self.PLATFORM,
            url=canonical,
            author_name=username or self.PLATFORM,
            author_handle=username,
            author_url=f"https://www.instagram.com/{username}/" if username else "",
            body=body,
            images=[image] if image else [],
            video_url=video,
            video_thumbnail=image,
            media_headers={"Referer": "https://www.instagram.com/"},
            stats=[("❤️", likes), ("💬", comments)],
            footer="Instagram",
            color=self.COLOR,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(InstaEmbed(bot))
