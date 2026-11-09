"""Helpers for user-installable ("user app") application commands.

Discord lets an application be installed to a user's account instead of, or in
addition to, a guild.  Commands that opt in with these decorators can then be
used anywhere the user is allowed to run them, including DMs and group DMs.

The decorators have to be placed *below* ``commands.hybrid_command`` for hybrid
commands, because :class:`discord.ext.commands.HybridCommand` reads the
application-command metadata from the callback at construction time.
"""

from __future__ import annotations

from typing import Any, Callable, TypeVar

from discord import app_commands

T = TypeVar("T", bound=Callable[..., Any])


def user_app(
    *,
    guilds: bool = True,
    dms: bool = True,
    private_channels: bool = True,
) -> Callable[[T], T]:
    """Mark a hybrid/app command as installable by both guilds and users.

    Parameters
    ----------
    guilds:
        Whether the command may be used in guilds.  This is also used for the
        installation context, so leaving it enabled keeps normal server usage
        working.
    dms:
        Whether the command may be used in direct messages.
    private_channels:
        Whether the command may be used in group DMs.
    """

    def decorator(func: T) -> T:
        func = app_commands.allowed_installs(guilds=guilds, users=True)(func)
        func = app_commands.allowed_contexts(
            guilds=guilds,
            dms=dms,
            private_channels=private_channels,
        )(func)
        return func

    return decorator


# Common presets -------------------------------------------------------------

def user_app_guild_only() -> Callable[[T], T]:
    """Installable for users, but only usable where a guild context exists."""

    return user_app(dms=False, private_channels=False)
