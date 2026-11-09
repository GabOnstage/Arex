"""Interactive NYT crossword player (daily or mini)."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from datetime import date as date_type
from datetime import timedelta
from typing import Any, Literal

import discord
from discord import app_commands
from discord.ext import commands

from utils.games import (
    GameLayoutView,
    fetch_json,
    normalise_word,
    paginate,
    parse_puzzle_date,
    truncate,
    utc_today,
)
from utils.userapps import user_app

log = logging.getLogger("arex.crosswords")

CROSSWORD_URL = "https://www.nytimes.com/svc/crosswords/v6/puzzle/{kind}/{day}.json"
PER_PAGE = 18


# --------------------------------------------------------------------------- model
def _clue_text(raw: Any) -> str:
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, list):
        parts: list[str] = []
        for part in raw:
            if isinstance(part, dict):
                parts.append(str(part.get("plain") or part.get("text") or ""))
            else:
                parts.append(str(part))
        return "".join(parts).strip()
    if isinstance(raw, dict):
        return str(raw.get("plain") or raw.get("text") or "").strip()
    return ""


@dataclass(slots=True)
class CrosswordClue:
    index: int
    label: str
    direction: str
    cells: list[int]
    text: str
    answer: str


@dataclass(slots=True)
class CrosswordPuzzle:
    width: int
    height: int
    cells: list[str | None]
    clues: list[CrosswordClue]
    day: date_type
    kind: str
    source: str = "NYT Crosswords"


def parse_crossword(payload: Any, day: date_type, kind: str) -> CrosswordPuzzle | None:
    if not isinstance(payload, dict):
        return None

    body = payload.get("body", payload)
    if isinstance(body, list):
        if not body:
            return None
        body = body[0]
    if not isinstance(body, dict):
        return None

    dimensions = body.get("dimensions") or {}
    width = int(dimensions.get("width") or 0)
    height = int(dimensions.get("height") or 0)
    raw_cells = body.get("cells") or []
    raw_clues = body.get("clues") or []

    if width <= 0 or height <= 0 or len(raw_cells) != width * height:
        return None

    answers: list[str | None] = []
    for cell in raw_cells:
        answer = cell.get("answer") if isinstance(cell, dict) else None
        answer = str(answer).upper() if answer else None
        answers.append(answer if answer and answer.isalpha() else None)

    clues: list[CrosswordClue] = []
    for index, raw in enumerate(raw_clues):
        if not isinstance(raw, dict):
            continue
        cell_indexes = [int(i) for i in raw.get("cells") or [] if isinstance(i, int)]
        if not cell_indexes or any(i < 0 or i >= len(answers) for i in cell_indexes):
            continue
        answer = "".join(answers[i] or "" for i in cell_indexes)
        if not answer:
            continue
        direction = str(raw.get("direction") or "").title()
        clues.append(
            CrosswordClue(
                index=index,
                label=str(raw.get("label") or "?"),
                direction=direction or "Across",
                cells=cell_indexes,
                text=_clue_text(raw.get("text")) or "(no clue text)",
                answer=answer,
            )
        )

    if not clues:
        return None

    return CrosswordPuzzle(
        width=width,
        height=height,
        cells=answers,
        clues=clues,
        day=day,
        kind=kind,
    )


async def fetch_crossword(
    bot: commands.Bot,
    kind: str,
    day: date_type,
) -> CrosswordPuzzle | None:
    payload = await fetch_json(bot, CROSSWORD_URL.format(kind=kind, day=day.isoformat()))
    return parse_crossword(payload, day, kind)


# ----------------------------------------------------------------------------- UI
class CrosswordAnswerModal(discord.ui.Modal):
    def __init__(self, game: "CrosswordGameView", clue: CrosswordClue) -> None:
        title = f"{clue.label} {clue.direction} — {clue.text}"
        super().__init__(title=truncate(title, 45), timeout=180)
        self.game = game
        self.clue = clue
        self.answer = discord.ui.Label(
            text=truncate(f"{clue.direction} {clue.label}: {clue.text}", 45),
            description=f"{len(clue.answer)} letters — spaces are ignored.",
            component=discord.ui.TextInput(
                placeholder="Type the answer…",
                min_length=1,
                max_length=max(10, len(clue.answer) + 8),
                required=True,
            ),
        )
        self.add_item(self.answer)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.game.author_id:
            return True
        await interaction.response.send_message(
            "Only the player who started this crossword can fill it in.",
            ephemeral=True,
        )
        return False

    async def on_submit(self, interaction: discord.Interaction) -> None:
        value = normalise_word(self.answer.component.value or "").upper()
        if len(value) != len(self.clue.answer):
            await interaction.response.send_message(
                f"`{self.clue.direction} {self.clue.label}` needs **{len(self.clue.answer)}** letters.",
                ephemeral=True,
            )
            return
        if value != self.clue.answer:
            await interaction.response.send_message(
                "Not quite — check the crossing letters and try again.",
                ephemeral=True,
            )
            return

        self.game.solve_clue(self.clue)
        await interaction.response.edit_message(view=self.game)


class CrosswordGameView(GameLayoutView):
    def __init__(
        self,
        *,
        bot: commands.Bot,
        author: discord.abc.User,
        puzzle: CrosswordPuzzle,
    ) -> None:
        super().__init__(timeout=1800)
        self.bot = bot
        self.author_id = author.id
        self.puzzle = puzzle
        self.filled: list[str | None] = [None] * len(puzzle.cells)
        self.solved: set[int] = set()
        self.page = 0
        self.status = "playing"
        self.started_at = time.monotonic()

        accent = discord.Color.purple() if puzzle.kind == "mini" else discord.Color.dark_blue()
        self.container = discord.ui.Container(accent_color=accent)
        self.heading = discord.ui.TextDisplay("")
        self.grid_display = discord.ui.TextDisplay("")
        self.progress = discord.ui.TextDisplay("")
        self.clues_display = discord.ui.TextDisplay("")
        self.footer = discord.ui.TextDisplay("")

        self.select_row = discord.ui.ActionRow()
        self.clue_select = discord.ui.Select(
            placeholder="Choose a clue to answer…",
            min_values=1,
            max_values=1,
        )
        self.clue_select.callback = self.select_clue
        self.select_row.add_item(self.clue_select)

        self.nav_row = discord.ui.ActionRow()
        self.prev_button = discord.ui.Button(label="Previous", emoji="◀️", style=discord.ButtonStyle.secondary)
        self.prev_button.callback = self.previous_page
        self.next_button = discord.ui.Button(label="Next", emoji="▶️", style=discord.ButtonStyle.secondary)
        self.next_button.callback = self.next_page
        self.reveal_button = discord.ui.Button(label="Reveal", emoji="💡", style=discord.ButtonStyle.danger)
        self.reveal_button.callback = self.reveal
        self.new_button = discord.ui.Button(label="New puzzle", emoji="🔄", style=discord.ButtonStyle.success)
        self.new_button.callback = self.new_puzzle
        self.nav_row.add_item(self.prev_button)
        self.nav_row.add_item(self.next_button)
        self.nav_row.add_item(self.reveal_button)
        self.nav_row.add_item(self.new_button)

        self.container.add_item(self.heading)
        self.container.add_item(self.grid_display)
        self.container.add_item(self.progress)
        self.container.add_item(self.clues_display)
        self.container.add_item(self.select_row)
        self.container.add_item(self.nav_row)
        self.container.add_item(self.footer)
        self.add_item(self.container)
        self.refresh()

    # ------------------------------------------------------------------ helpers
    @property
    def letter_cells(self) -> int:
        return sum(1 for cell in self.puzzle.cells if cell is not None)

    @property
    def filled_cells(self) -> int:
        return sum(1 for cell in self.filled if cell is not None)

    def _grid_text(self) -> str:
        lines: list[str] = []
        for row in range(self.puzzle.height):
            line: list[str] = []
            for column in range(self.puzzle.width):
                index = row * self.puzzle.width + column
                if self.puzzle.cells[index] is None:
                    line.append("■")
                else:
                    line.append(self.filled[index] or "·")
            lines.append(" ".join(line))
        return "```\n" + "\n".join(lines) + "\n```"

    def _clue_pages(self) -> tuple[list[CrosswordClue], int, int]:
        return paginate(self.puzzle.clues, self.page, PER_PAGE)

    def _clue_list_text(self, clues: list[CrosswordClue]) -> str:
        if not clues:
            return ""
        across = [clue for clue in clues if clue.direction == "Across"]
        down = [clue for clue in clues if clue.direction != "Across"]
        sections: list[str] = []
        for title, entries in (("Across", across), ("Down", down)):
            if not entries:
                continue
            lines = [f"**{title}**"]
            for clue in entries:
                mark = "✅" if clue.index in self.solved else "▫️"
                lines.append(f"{mark} **{clue.label}.** {clue.text}")
            sections.append("\n".join(lines))
        return "\n\n".join(sections)

    def _select_options(self, clues: list[CrosswordClue]) -> list[discord.SelectOption]:
        options: list[discord.SelectOption] = []
        for clue in clues:
            solved = clue.index in self.solved
            label = f"{clue.direction[0]} {clue.label}: {clue.text}"
            options.append(
                discord.SelectOption(
                    label=truncate(label, 100),
                    value=str(clue.index),
                    description=f"{len(clue.answer)} letters" + (" • solved" if solved else ""),
                    emoji="✅" if solved else ("⬛" if clue.direction == "Across" else "⬇️"),
                    default=False,
                )
            )
        return options

    def refresh(self) -> None:
        kind = "Mini" if self.puzzle.kind == "mini" else "Daily"
        self.heading.content = f"## 🧩 NYT {kind} Crossword — {self.puzzle.day:%B %d, %Y}"

        self.grid_display.content = self._grid_text()
        self.progress.content = (
            f"**{len(self.solved)}/{len(self.puzzle.clues)}** clues solved  •  "
            f"**{self.filled_cells}/{self.letter_cells}** cells filled"
        )

        clues, page, pages = self._clue_pages()
        self.page = page
        self.clues_display.content = self._clue_list_text(clues)[:3900]
        self.clue_select.options = self._select_options(clues)
        self.clue_select.disabled = self.status != "playing"

        self.prev_button.disabled = self.status != "playing" or page <= 0
        self.next_button.disabled = self.status != "playing" or page >= pages - 1
        self.reveal_button.disabled = self.status != "playing"
        self.new_button.disabled = False

        if self.status == "won":
            elapsed = int(time.monotonic() - self.started_at)
            self.footer.content = f"-# 🎉 Complete in {elapsed // 60}m {elapsed % 60}s — well played!"
        elif self.status == "revealed":
            self.footer.content = "-# The full solution is shown above. Use **New puzzle** for another one."
        else:
            self.footer.content = (
                f"-# Page {page + 1}/{pages} • Select a clue, then type its answer in the popup."
            )

    def solve_clue(self, clue: CrosswordClue) -> None:
        for index, letter in zip(clue.cells, clue.answer):
            self.filled[index] = letter
        self.solved.add(clue.index)
        if self.filled_cells >= self.letter_cells:
            self.status = "won"

    def reveal_all(self) -> None:
        for index, answer in enumerate(self.puzzle.cells):
            if answer is not None:
                self.filled[index] = answer
        self.solved.update(clue.index for clue in self.puzzle.clues)
        self.status = "revealed"

    # -------------------------------------------------------------- callbacks
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "Only the player who started this crossword can use it.",
            ephemeral=True,
        )
        return False

    async def select_clue(self, interaction: discord.Interaction) -> None:
        if self.status != "playing":
            await interaction.response.defer()
            return
        try:
            clue_index = int(self.clue_select.values[0])
        except (IndexError, ValueError):
            await interaction.response.defer()
            return
        clue = next((item for item in self.puzzle.clues if item.index == clue_index), None)
        if clue is None:
            await interaction.response.defer()
            return
        await interaction.response.send_modal(CrosswordAnswerModal(self, clue))

    async def previous_page(self, interaction: discord.Interaction) -> None:
        self.page -= 1
        self.refresh()
        await interaction.response.edit_message(view=self)

    async def next_page(self, interaction: discord.Interaction) -> None:
        self.page += 1
        self.refresh()
        await interaction.response.edit_message(view=self)

    async def reveal(self, interaction: discord.Interaction) -> None:
        if self.status != "playing":
            await interaction.response.defer()
            return
        self.reveal_all()
        self.refresh()
        await interaction.response.edit_message(view=self)

    async def new_puzzle(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        today = utc_today()
        puzzle: CrosswordPuzzle | None = None
        for _ in range(6):
            day = today - timedelta(days=random.randint(1, 365))
            if day == self.puzzle.day:
                continue
            puzzle = await fetch_crossword(self.bot, self.puzzle.kind, day)
            if puzzle is not None:
                break

        if puzzle is None:
            await interaction.followup.send(
                "I could not fetch another crossword right now — please try again in a moment.",
                ephemeral=True,
            )
            return

        self.puzzle = puzzle
        self.filled = [None] * len(puzzle.cells)
        self.solved.clear()
        self.page = 0
        self.status = "playing"
        self.started_at = time.monotonic()
        self.refresh()
        await interaction.edit_original_response(view=self)


class Crosswords(commands.Cog):
    """Solve the New York Times daily or mini crossword inside Discord."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="crosswords",
        aliases=["crossword"],
        description="Solve the NYT mini or daily crossword with an interactive board.",
    )
    @user_app()
    @app_commands.describe(
        puzzle="Choose the mini (quick) or daily (full-size) crossword.",
        date="Puzzle date in YYYY-MM-DD format (defaults to today, UTC).",
    )
    async def crossword(
        self,
        ctx: commands.Context,
        puzzle: Literal["mini", "daily"] = "mini",
        date: str | None = None,
    ) -> None:
        kind = (puzzle or "mini").lower()
        if kind not in {"mini", "daily"}:
            await ctx.send("Choose either `mini` or `daily`.")
            return

        try:
            day = parse_puzzle_date(date)
        except ValueError as exc:
            await ctx.send(str(exc))
            return

        await ctx.defer()
        loaded = await fetch_crossword(self.bot, kind, day)
        if loaded is None:
            await ctx.send(
                f"I could not load the {kind} crossword for **{day:%B %d, %Y}**. "
                "Try a different date or try again later."
            )
            return

        view = CrosswordGameView(bot=self.bot, author=ctx.author, puzzle=loaded)
        message = await ctx.send(view=view)
        view.message = message


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Crosswords(bot))
