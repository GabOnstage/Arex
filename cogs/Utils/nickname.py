from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.userapps import user_app_guild_only

log = logging.getLogger("arex.nickname")

MAX_NICKNAME_LENGTH = 32
RESET_KEYWORDS = {"reset", "clear", "none", "remove", "-"}


def _clean_nickname(value: Optional[str]):
    """Return ``(nickname, error)``; ``nickname`` is None when resetting."""
    if value is None:
        return None, None

    value = value.strip()
    if not value or value.lower() in RESET_KEYWORDS:
        return None, None

    if len(value) > MAX_NICKNAME_LENGTH:
        return None, (
            f"Nicknames can only be up to {MAX_NICKNAME_LENGTH} characters long."
        )

    return value, None


class Nickname(commands.Cog):
    """Change your own server nickname, with a staff rename helper."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _apply(
        self,
        ctx: commands.Context,
        target: discord.Member,
        nickname: Optional[str],
        *,
        staff: bool = False,
    ):
        nickname, error = _clean_nickname(nickname)
        if error:
            await ctx.send(f"⚠️ {error}", ephemeral=True)
            return

        guild = ctx.guild
        if guild is None:
            await ctx.send(
                "Nicknames can only be changed inside a server.",
                ephemeral=True,
            )
            return

        me = guild.me
        if me is None:
            try:
                me = await guild.fetch_member(self.bot.user.id)
            except (discord.NotFound, discord.HTTPException):
                await ctx.send(
                    "I couldn't resolve my server member. Please try again.",
                    ephemeral=True,
                )
                return

        if not me.guild_permissions.manage_nicknames:
            await ctx.send(
                "I need the **Manage Nicknames** permission to change nicknames.",
                ephemeral=True,
            )
            return

        author = ctx.author
        if staff and (
            not isinstance(author, discord.Member)
            or not author.guild_permissions.manage_nicknames
        ):
            await ctx.send(
                "You need the **Manage Nicknames** permission to rename other members.",
                ephemeral=True,
            )
            return

        if target.id == guild.owner_id:
            await ctx.send(
                "The server owner's nickname can't be changed.",
                ephemeral=True,
            )
            return

        if target.id != me.id and target.top_role >= me.top_role:
            await ctx.send(
                f"I can't rename {target.mention} because their highest role is "
                "above or equal to mine.",
                ephemeral=True,
            )
            return

        await ctx.defer(ephemeral=True)

        previous = target.nick or target.name
        action = "reset" if nickname is None else "changed"
        try:
            await target.edit(
                nick=nickname,
                reason=f"Nickname {action} by {author} ({author.id})",
            )
        except discord.Forbidden:
            await ctx.send(
                "I don't have permission to change that nickname.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as exc:
            log.warning(
                "Failed to change nickname for %s: %s", target.id, exc, exc_info=exc
            )
            await ctx.send(
                f"Discord rejected the nickname change: {exc}",
                ephemeral=True,
            )
            return

        if target.id == author.id:
            subject = "your nickname"
        else:
            subject = f"{target.mention}'s nickname"

        if nickname is None:
            await ctx.send(f"✅ Reset {subject}.", ephemeral=True)
        else:
            await ctx.send(
                f"✅ Changed {subject} to **{discord.utils.escape_markdown(nickname)}** "
                f"(was **{discord.utils.escape_markdown(previous)}**).",
                ephemeral=True,
            )

    @commands.hybrid_command(
        name="nickname",
        aliases=["nick", "setnick"],
        description="Change or reset your own server nickname.",
    )
    @user_app_guild_only()
    @commands.guild_only()
    @app_commands.describe(
        nickname="Your new nickname (max 32 characters). Leave empty or type `reset` to remove it."
    )
    async def nickname(self, ctx: commands.Context, *, nickname: Optional[str] = None):
        await self._apply(ctx, ctx.author, nickname)

    @commands.hybrid_command(
        name="rename",
        description="Rename another member (requires Manage Nicknames).",
    )
    @user_app_guild_only()
    @commands.guild_only()
    @app_commands.default_permissions(manage_nicknames=True)
    @app_commands.describe(
        member="The member to rename.",
        nickname="New nickname. Leave empty to reset it.",
    )
    async def rename(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        nickname: Optional[str] = None,
    ):
        await self._apply(ctx, member, nickname, staff=True)

    async def cog_command_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.MemberNotFound) or isinstance(
            error, commands.BadArgument
        ):
            await ctx.send("I couldn't find that member.", ephemeral=True)
            return
        if isinstance(error, commands.CommandOnCooldown):
            # Let the global handler report cooldowns.
            return

        log.error("Nickname command failed: %s", error, exc_info=error)
        await ctx.send(
            "Something went wrong while changing that nickname. Please try again.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Nickname(bot))
