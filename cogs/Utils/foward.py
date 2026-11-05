import io
import logging
import os
import re
from urllib.parse import unquote, urlparse

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("arex.foward")

# https://discord.com/channels/<guild>/<channel>/<message>
# Also accepts canary/ptb subdomains, discordapp.com and the @me DM form.
MESSAGE_LINK_RE = re.compile(
    r"https?://(?:www\.)?(?:ptb\.|canary\.)?discord(?:app)?\.com/channels/"
    r"(?P<guild_id>\d+|@me)/(?P<channel_id>\d+)/(?P<message_id>\d+)",
    re.IGNORECASE,
)

MAX_FILES = 10
MAX_EMBEDS = 10
DM_FILE_LIMIT = 8 * 1024 * 1024


class ForwardFailure(Exception):
    """Raised when a message cannot be forwarded to the chosen channel."""


class ForwardDestinationView(discord.ui.View):
    """Channel picker shown by the message context menu."""

    def __init__(self, cog: "Foward", source: discord.Message):
        super().__init__(timeout=120)
        self.cog = cog
        self.source = source

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text, discord.ChannelType.news],
        placeholder="Pick a destination channel",
    )
    async def destination_select(
        self,
        interaction: discord.Interaction,
        select: discord.ui.ChannelSelect,
    ):
        await interaction.response.defer(ephemeral=True)

        selected = select.values[0]
        channel = selected.resolve()
        if channel is None:
            try:
                channel = await selected.fetch()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as exc:
                log.warning(
                    "Could not resolve forward destination %s: %s",
                    selected.id,
                    exc,
                    exc_info=exc,
                )
                await interaction.followup.send(
                    "I couldn't access that channel.", ephemeral=True
                )
                return

        try:
            sent, warnings = await self.cog.deliver(self.source, channel)
        except ForwardFailure as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        response = f"✅ Forwarded the message to {channel.mention}.\n{sent.jump_url}"
        if warnings:
            response += "\n\n⚠️ " + "\n⚠️ ".join(warnings)
        await interaction.followup.send(response, ephemeral=True)
        self.stop()


class Foward(commands.Cog):
    """Copy a message (including its images) into another channel.

    The message is rebuilt from a snapshot instead of using Discord's native
    forward, because Discord does not let bots forward bot-authored messages.
    Attachments are downloaded and re-uploaded so the copy survives the source
    message being edited or deleted.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.forward_menu = app_commands.ContextMenu(
            name="Forward Message",
            callback=self.forward_context_menu,
            allowed_contexts=app_commands.AppCommandContext(
                guild=True, dm_channel=True, private_channel=True
            ),
            allowed_installs=app_commands.AppInstallationType(guild=True, user=True),
        )
        self.bot.tree.add_command(self.forward_menu)

    async def cog_unload(self):
        self.bot.tree.remove_command(
            self.forward_menu.name, type=self.forward_menu.type
        )

    async def forward_context_menu(
        self,
        interaction: discord.Interaction,
        message: discord.Message,
    ):
        """Forward the message that was right-clicked via Apps > Forward Message."""
        if interaction.guild is None:
            await interaction.response.defer(ephemeral=True)
            try:
                sent, warnings = await self.deliver(message, message.channel)
            except ForwardFailure as exc:
                await interaction.followup.send(str(exc), ephemeral=True)
                return

            response = f"✅ Forwarded the message here.\n{sent.jump_url}"
            if warnings:
                response += "\n\n⚠️ " + "\n⚠️ ".join(warnings)
            await interaction.followup.send(response, ephemeral=True)
            return

        view = ForwardDestinationView(self, message)
        await interaction.response.send_message(
            "Where should I forward this message?",
            view=view,
            ephemeral=True,
        )

    @commands.hybrid_command(
        name="foward",
        aliases=["forward"],
        description="Forward a message and its images to another channel, even if the original is deleted or edited.",
    )
    @commands.guild_only()
    @app_commands.describe(
        channel="The channel to forward the message to.",
        message="Message link or message ID. Leave empty when using the prefix command as a reply.",
    )
    async def foward(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel,
        message: str = None,
    ):
        # Slash commands must be acknowledged within 3 seconds; downloading and
        # re-uploading images can take longer than that.
        await ctx.defer(ephemeral=True)

        source = await self._resolve_message(ctx, message)
        if source is None:
            await self._error(
                ctx,
                "I couldn't find that message. Provide a valid message link or ID, "
                "or reply to a message with the prefix command.",
            )
            return

        try:
            sent, warnings = await self.deliver(source, channel)
        except ForwardFailure as exc:
            await self._error(ctx, str(exc))
            return

        response = f"✅ Forwarded the message to {channel.mention}.\n{sent.jump_url}"
        if warnings:
            response += "\n\n⚠️ " + "\n⚠️ ".join(warnings)

        await ctx.send(response, ephemeral=True)

    async def deliver(self, source: discord.Message, destination):
        """Validate permissions and copy *source* into *destination*.

        Returns ``(sent_message, warnings)`` and raises :class:`ForwardFailure`
        with a user-facing reason when the copy cannot be sent.
        """
        if not source.content and not source.embeds and not source.attachments:
            raise ForwardFailure(
                "That message has no text, embeds, or files to forward."
            )

        guild = getattr(destination, "guild", None)
        perms = None
        target = getattr(destination, "mention", "that channel")

        if guild is not None:
            me = guild.me or guild.get_member(self.bot.user.id)
            if me is None:
                raise ForwardFailure(
                    "I couldn't resolve my permissions in that server."
                )

            perms = destination.permissions_for(me)
            if not perms.view_channel or not perms.send_messages:
                raise ForwardFailure(
                    f"I need **View Channel** and **Send Messages** permissions in {target}."
                )
            if source.attachments and not perms.attach_files:
                raise ForwardFailure(
                    f"I need the **Attach Files** permission in {target} to copy the image(s)."
                )
            if source.embeds and not perms.embed_links:
                raise ForwardFailure(
                    f"I need the **Embed Links** permission in {target} to copy the embed(s)."
                )

        embeds, files, warnings = await self._snapshot(
            source,
            destination,
            include_attribution=perms.embed_links if perms is not None else True,
        )

        if files and perms is not None and not perms.attach_files:
            raise ForwardFailure(
                f"I need the **Attach Files** permission in {target} to copy the image(s)."
            )
        if embeds and perms is not None and not perms.embed_links:
            raise ForwardFailure(
                f"I need the **Embed Links** permission in {target} to copy the embed(s)."
            )

        try:
            sent = await destination.send(
                content=source.content or None,
                embeds=embeds,
                files=files,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.Forbidden:
            raise ForwardFailure(
                f"I don't have permission to send messages in {target}."
            ) from None
        except discord.HTTPException as exc:
            log.error(
                "Failed to forward message %s: %s", source.id, exc, exc_info=exc
            )
            raise ForwardFailure(
                f"Discord rejected the forwarded message: {exc}"
            ) from exc

        return sent, warnings

    async def _resolve_message(self, ctx: commands.Context, value: str):
        # Prefix usage as a reply: forward the message being replied to.
        if not value:
            reference = ctx.message.reference if ctx.message else None
            if reference and reference.message_id:
                try:
                    return await ctx.channel.fetch_message(reference.message_id)
                except (discord.NotFound, discord.Forbidden):
                    return None
            return None

        value = value.strip()

        match = MESSAGE_LINK_RE.search(value)
        if match:
            return await self._fetch_from_link(match)

        if value.isdigit():
            return await self._find_by_id(ctx, int(value))

        return None

    async def _fetch_from_link(self, match: re.Match):
        channel_id = int(match.group("channel_id"))
        message_id = int(match.group("message_id"))

        source_channel = self.bot.get_channel(channel_id)
        if source_channel is None:
            try:
                source_channel = await self.bot.fetch_channel(channel_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return None

        try:
            return await source_channel.fetch_message(message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

    async def _find_by_id(self, ctx: commands.Context, message_id: int):
        # Prefer the current channel, then look through the guild's text
        # channels and active threads so pasted IDs still work.
        try:
            return await ctx.channel.fetch_message(message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

        if ctx.guild is None:
            return None

        candidates = list(ctx.guild.text_channels) + list(ctx.guild.threads)
        for source_channel in candidates[:50]:
            if source_channel.id == ctx.channel.id:
                continue
            try:
                if not source_channel.permissions_for(ctx.guild.me).read_message_history:
                    continue
                return await source_channel.fetch_message(message_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                continue

        return None

    async def _snapshot(
        self,
        source: discord.Message,
        destination,
        include_attribution: bool = True,
    ):
        """Build a self-contained copy of the message.

        Text and embeds are copied as-is. Attachments are downloaded and
        re-uploaded, and embed media that lives on Discord's CDN (or references
        one of the source attachments) is re-uploaded too. This way the copy no
        longer depends on the original message.
        """
        files = []
        new_names = set()
        attachment_names = {}
        downloaded_urls = {}
        warnings = []
        guild = getattr(destination, "guild", None)
        max_size = guild.filesize_limit if guild is not None else DM_FILE_LIMIT

        def unique_name(name: str) -> str:
            name = os.path.basename(name) or "image.png"
            if "." not in name:
                name += ".png"
            base, ext = os.path.splitext(name)
            candidate = name
            counter = 1
            while candidate in new_names:
                candidate = f"{base}_{counter}{ext}"
                counter += 1
            new_names.add(candidate)
            return candidate

        for attachment in source.attachments:
            if len(files) >= MAX_FILES:
                warnings.append("Some attachments were skipped because a message can only hold 10 files.")
                break

            try:
                data = await attachment.read()
            except Exception as exc:
                log.warning("Could not download attachment %s: %s", attachment.id, exc)
                warnings.append(f"`{attachment.filename}` could not be downloaded.")
                continue

            if len(data) > max_size:
                warnings.append(
                    f"`{attachment.filename}` is larger than this server's upload limit and was not copied."
                )
                continue

            filename = unique_name(attachment.filename or f"attachment_{attachment.id}")
            files.append(
                discord.File(
                    io.BytesIO(data),
                    filename=filename,
                    spoiler=attachment.is_spoiler(),
                )
            )
            attachment_names.setdefault(attachment.filename, filename)
            downloaded_urls[attachment.url] = filename
            if attachment.proxy_url:
                downloaded_urls[attachment.proxy_url] = filename

        embeds = []
        for embed in source.embeds[:MAX_EMBEDS]:
            data = embed.to_dict()

            for key in ("image", "thumbnail"):
                media = data.get(key)
                if not media or not media.get("url"):
                    continue

                url = media["url"]
                filename = None

                if url.startswith("attachment://"):
                    original_name = unquote(url[len("attachment://"):])
                    filename = attachment_names.get(original_name)
                    if filename is None:
                        # The source attachment could not be copied, so the
                        # reference would be broken.
                        data.pop(key, None)
                        continue
                else:
                    filename = downloaded_urls.get(url)
                    if filename is None and self._is_discord_cdn(url) and len(files) < MAX_FILES:
                        downloaded = await self._download_media(url, unique_name, max_size)
                        if downloaded:
                            filename, file = downloaded
                            files.append(file)
                            downloaded_urls[url] = filename
                        else:
                            warnings.append("An embed image could not be copied and may break later.")
                            filename = None

                if filename:
                    media["url"] = f"attachment://{filename}"
                    # Stale CDN dimensions/signatures no longer apply to the
                    # re-uploaded file.
                    media.pop("proxy_url", None)
                    media.pop("width", None)
                    media.pop("height", None)

            try:
                embeds.append(discord.Embed.from_dict(data))
            except Exception:
                embeds.append(embed)

        # Add a small attribution card if there is room for another embed.
        if include_attribution and len(embeds) < MAX_EMBEDS:
            attribution = discord.Embed(
                description=f"Forwarded from **{discord.utils.escape_markdown(str(source.author))}**\n"
                f"[Jump to original]({source.jump_url})",
                color=discord.Color.blurple(),
                timestamp=source.created_at,
            )
            attribution.set_author(
                name=str(source.author),
                icon_url=source.author.display_avatar.url,
            )
            if source.author.bot:
                attribution.set_footer(text="Original author was a bot")
            embeds.append(attribution)

        return embeds, files, warnings

    def _is_discord_cdn(self, url: str) -> bool:
        try:
            host = (urlparse(url).hostname or "").lower()
        except ValueError:
            return False
        return host == "cdn.discordapp.com" or host.endswith(".discordapp.net")

    async def _download_media(self, url: str, unique_name, max_size: int):
        session = getattr(self.bot, "session", None)
        if session is None or session.closed:
            return None

        try:
            async with session.get(url, timeout=30) as response:
                if response.status != 200:
                    return None
                if response.content_length and response.content_length > max_size:
                    return None
                data = await response.read()
        except Exception as exc:
            log.warning("Could not download embed media %s: %s", url, exc)
            return None

        if len(data) > max_size:
            return None

        name = unquote(os.path.basename(urlparse(url).path)) or "embed.png"
        filename = unique_name(name)
        file = discord.File(io.BytesIO(data), filename=filename)
        return filename, file

    async def _error(self, ctx: commands.Context, description: str):
        embed = discord.Embed(
            title="Forward Failed",
            description=description,
            color=discord.Color.red(),
        )
        await ctx.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Foward(bot))
