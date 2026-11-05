import logging
import os

import discord
from discord import app_commands
from discord.ext import commands

from ._embed_common import (
    BACKUP_DOMAINS,
    DOMAIN_ALIASES,
    OTHER_URL_PATTERN,
    PRIMARY_DOMAINS,
    SUPPORTED_PLATFORMS,
    TRAILING_PUNCTUATION,
    get_session,
    get_tracker,
    is_wrapped,
    log_embed,
    resolve_link,
)

log = logging.getLogger("arex.embed_command")


PLATFORM_COGS = {
    "tiktok.com": "TikTokEmbed",
    "instagram.com": "InstaEmbed",
    "reddit.com": "RedditEmbed",
    "threads.net": "ThreadsEmbed",
}


def _parse_guild_ids() -> frozenset:
    raw = os.getenv("Guilds", "")
    return frozenset(int(g.strip()) for g in raw.split(",") if g.strip().isdigit())


class EmbedFix(commands.Cog):
    """Single listener that dispatches links to the matching platform cog."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.allowed_guilds = _parse_guild_ids()
        self.tracker = get_tracker(bot)
        if not self.allowed_guilds:
            log.warning(
                "EmbedFix: Guilds is not set in .env — beta auto-fix is disabled everywhere."
            )

        self.embed_menu = app_commands.ContextMenu(
            name="Fix Embed",
            callback=self.handle_embed_context_menu,
            allowed_contexts=app_commands.AppCommandContext(
                guild=True, dm_channel=False, private_channel=False
            ),
            allowed_installs=app_commands.AppInstallationType(guild=True, user=True),
        )
        self.bot.tree.add_command(self.embed_menu)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.embed_menu.name, type=self.embed_menu.type)

    async def handle_embed_context_menu(
        self,
        interaction: discord.Interaction,
        message: discord.Message,
    ):
        """Fix the supported social link(s) in the message that was right-clicked."""
        await interaction.response.defer(ephemeral=True)

        content = message.content or ""
        if not content.strip():
            await interaction.followup.send(
                "That message has no text or link to fix.", ephemeral=True
            )
            return

        x_cog = self._x_cog()
        has_link = False
        if x_cog is not None:
            has_link = bool(
                x_cog.find_x_link(content, allow_wrapped=True)
                or x_cog.find_x_profile_link(content, allow_wrapped=True)
            )
        if not has_link:
            has_link = bool(self._find_other_links(content))

        if not has_link:
            await interaction.followup.send(
                f"No supported link found. Supported platforms: {SUPPORTED_PLATFORMS}.",
                ephemeral=True,
            )
            return

        try:
            handled = await self._handle_message(message, allow_suppressed=True)
        except Exception:
            log.exception("Embed context menu failed for message %s", message.id)
            await interaction.followup.send(
                "I couldn't fix that message's links.", ephemeral=True
            )
            return

        if handled:
            await interaction.followup.send(
                "Fixed the link(s) in that message.", ephemeral=True
            )
        else:
            await interaction.followup.send(
                "I couldn't fix that message's links.", ephemeral=True
            )

    def _x_cog(self):
        return self.bot.get_cog("XEmbed")

    def _platform_cog(self, domain: str):
        cog_name = PLATFORM_COGS.get(domain)
        if cog_name is None:
            return None
        return self.bot.get_cog(cog_name)

    def _find_other_links(self, content: str):
        found = []
        seen = set()
        for match in OTHER_URL_PATTERN.finditer(content):
            if is_wrapped(content, match):
                continue
            url = match.group(0).rstrip(TRAILING_PUNCTUATION)
            domain = match.group("domain").lower()
            domain = DOMAIN_ALIASES.get(domain, domain)
            key = url.lower()
            if key in seen:
                continue
            seen.add(key)
            found.append((url, domain))
        return found

    async def _handle_other(self, message: discord.Message, found):
        session, close_session = get_session(self.bot)

        try:
            fixed_links = []
            for url, domain in found:
                cog = self._platform_cog(domain)
                if cog is not None and hasattr(cog, "handle_message"):
                    try:
                        handled = await cog.handle_message(message, url)
                    except Exception as exc:
                        log.exception("Rich %s handler crashed", domain)
                        log_embed(domain, f"rich handler crashed: {exc!r}")
                        handled = False
                    if handled:
                        continue
                    fixed_links.append(await cog.resolve(session, url))
                elif cog is not None:
                    fixed_links.append(await cog.resolve(session, url))
                else:
                    fixed_links.append(
                        await resolve_link(
                            session,
                            url,
                            PRIMARY_DOMAINS[domain],
                            BACKUP_DOMAINS.get(domain),
                        )
                    )

            if not fixed_links:
                return False

            try:
                reply = await message.reply(
                    content="\n".join(fixed_links),
                    mention_author=False,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException:
                return False
            self.tracker.track_reply(message.id, message.channel.id, reply.id)
            return True
        finally:
            if close_session and session and not session.closed:
                await session.close()

    async def _handle_message(self, message: discord.Message, allow_suppressed: bool = False):
        if not allow_suppressed and message.flags.suppress_embeds:
            return False

        x_cog = self._x_cog()
        if x_cog is not None:
            x_link = x_cog.find_x_link(message.content)
            if x_link:
                await x_cog.handle_message(message, x_link[0], x_link[1])
                return True

            profile_link = x_cog.find_x_profile_link(message.content)
            if profile_link:
                await x_cog.handle_profile_message(message, profile_link[0], profile_link[1])
                return True

        found = self._find_other_links(message.content)
        if found:
            return await self._handle_other(message, found)
        return False

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

        await self.tracker.delete_tracked_reply(after.id)
        await self._handle_message(after, allow_suppressed=True)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild is None or message.guild.id not in self.allowed_guilds:
            return

        if message.author.bot:
            original_id = self.tracker.find_original_by_reply(message.id)
            if original_id is None:
                return
            self.tracker.forget(original_id)
        else:
            await self.tracker.delete_tracked_reply(message.id)

    @commands.hybrid_command(name="embed", description="Fix a social media link so it embeds properly in Discord.")
    @app_commands.describe(link=f"Link to fix ({SUPPORTED_PLATFORMS})")
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def embed(self, ctx: commands.Context, link: str):
        await ctx.defer()
        link = link.strip()

        x_cog = self._x_cog()
        if x_cog is not None:
            x_link = x_cog.find_x_link(link, allow_wrapped=True)
            if x_link:
                await x_cog.handle_command_post(ctx, x_link[0], x_link[1])
                return

            profile_link = x_cog.find_x_profile_link(link, allow_wrapped=True)
            if profile_link:
                await x_cog.handle_command_profile(ctx, profile_link[0], profile_link[1])
                return

        match = OTHER_URL_PATTERN.search(link)
        if match is None:
            await ctx.send(f"Unsupported link. Supported platforms: {SUPPORTED_PLATFORMS}.")
            return

        domain = match.group("domain").lower()
        domain = DOMAIN_ALIASES.get(domain, domain)
        url = link[match.start():match.end()].rstrip(TRAILING_PUNCTUATION)
        cog = self._platform_cog(domain)

        if cog is not None and hasattr(cog, "handle_command"):
            try:
                await cog.handle_command(ctx, url)
            except Exception as exc:
                log.exception("Rich %s command handler crashed", domain)
                log_embed(domain, f"rich command handler crashed: {exc!r}")
            return

        session, close_session = get_session(self.bot)

        try:
            if cog is not None:
                fixed = await cog.resolve(session, url)
            else:
                fixed = await resolve_link(
                    session,
                    url,
                    PRIMARY_DOMAINS[domain],
                    BACKUP_DOMAINS.get(domain),
                )
            await ctx.send(fixed)
        finally:
            if close_session and session and not session.closed:
                await session.close()


async def setup(bot: commands.Bot):
    await bot.add_cog(EmbedFix(bot))
