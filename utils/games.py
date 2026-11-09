"""Shared helpers for the interactive games."""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Any, AsyncIterator, Sequence, TypeVar

import aiohttp
import discord

T = TypeVar("T")

#: Wordle colour blocks, reused by several games.
CORRECT = "🟩"
PRESENT = "🟨"
ABSENT = "⬛"
EMPTY = "⬜"

_WORD_RE = re.compile(r"^[a-z]+$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def utc_today() -> date:
    """Return the current UTC date (the day used by the NYT daily puzzles)."""

    return datetime.now(timezone.utc).date()


def parse_puzzle_date(value: str | None) -> date:
    """Parse a ``YYYY-MM-DD`` string, defaulting to today's UTC date."""

    if value is None or not str(value).strip():
        return utc_today()

    value = str(value).strip()
    if not _DATE_RE.match(value):
        raise ValueError("Use a date in `YYYY-MM-DD` format, for example `2026-11-07`.")

    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("That is not a real calendar date.") from exc

    if parsed > utc_today():
        raise ValueError("I cannot fetch a puzzle from the future (yet).")
    return parsed


def normalise_word(value: str) -> str:
    """Lower-case a guess and strip anything that is not a letter."""

    return re.sub(r"[^a-z]", "", value.lower())


def is_word(value: str, length: int | None = None) -> bool:
    """Return ``True`` when *value* is alphabetic (and the expected length)."""

    if not _WORD_RE.match(value):
        return False
    return length is None or len(value) == length


def score_word(guess: str, answer: str) -> list[str]:
    """Score a Wordle guess.

    The result contains one of ``"correct"``, ``"present"`` or ``"absent"`` per
    letter and implements the usual duplicate-letter rules.
    """

    guess = guess.lower()
    answer = answer.lower()
    result = ["absent"] * len(guess)
    remaining: list[str | None] = list(answer)

    for index, letter in enumerate(guess):
        if index < len(answer) and letter == answer[index]:
            result[index] = "correct"
            remaining[index] = None

    for index, letter in enumerate(guess):
        if result[index] == "correct":
            continue
        if letter in remaining:
            result[index] = "present"
            remaining[remaining.index(letter)] = None

    return result


def score_emoji(score: Sequence[str]) -> str:
    """Convert a :func:`score_word` result into coloured emoji squares."""

    mapping = {"correct": CORRECT, "present": PRESENT, "absent": ABSENT}
    return "".join(mapping.get(item, ABSENT) for item in score)


def paginate(items: Sequence[T], page: int, per_page: int) -> tuple[list[T], int, int]:
    """Return ``(slice, page, total_pages)`` clamped to a valid page."""

    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    return list(items[start : start + per_page]), page, total_pages


def truncate(value: Any, length: int = 100) -> str:
    """Shorten a string for use in a Discord component label."""

    text = str(value).replace("\n", " ").strip()
    if len(text) <= length:
        return text
    return text[: max(0, length - 1)] + "…"


@asynccontextmanager
async def bot_session(bot: Any) -> AsyncIterator[aiohttp.ClientSession]:
    """Yield the bot's shared aiohttp session, or a temporary one."""

    session = getattr(bot, "session", None)
    if session is not None and not session.closed:
        yield session
        return

    async with aiohttp.ClientSession() as temporary:
        yield temporary


async def fetch_json(
    bot: Any,
    url: str,
    *,
    timeout: float = 10.0,
) -> Any | None:
    """Fetch JSON from *url* and return ``None`` for any non-200 response."""

    try:
        async with bot_session(bot) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                if response.status != 200:
                    return None
                return await response.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError, ValueError):
        return None


class GameLayoutView(discord.ui.LayoutView):
    """A LayoutView that disables its controls when the game times out."""

    def __init__(self, *, timeout: float = 1800) -> None:
        super().__init__(timeout=timeout)
        self.message: discord.Message | None = None

    async def on_timeout(self) -> None:
        for item in self.walk_children():
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


def column_label(index: int) -> str:
    """Return ``A`` for 0, ``B`` for 1, ... (used by Battleship)."""

    return chr(ord("A") + index)


def board_header(width: int) -> str:
    """Return a Battleship-style column header (``1 2 ... 10``)."""

    return "    " + " ".join(str(i) for i in range(1, width + 1))
