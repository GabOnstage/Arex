"""Wordle, powered by the official New York Times daily puzzle endpoint."""

from __future__ import annotations

import logging
import random
from datetime import date as date_type

import discord
from discord import app_commands
from discord.ext import commands

from utils.games import (
    EMPTY,
    GameLayoutView,
    fetch_json,
    is_word,
    normalise_word,
    parse_puzzle_date,
    score_emoji,
    score_word,
)
from utils.userapps import user_app
from utils.wordlists import WORDLE_FALLBACK

log = logging.getLogger("arex.wordle")

WORDLE_URL = "https://www.nytimes.com/svc/wordle/v2/{day}.json"
MAX_GUESSES = 6


class WordleGuessModal(discord.ui.Modal):
    """A small modal instead of making players type into the channel."""

    def __init__(self, game: "WordleGameView") -> None:
        super().__init__(title="Wordle — make a guess", timeout=180)
        self.game = game
        self.guess = discord.ui.Label(
            text="Your five-letter guess",
            description="The word must be exactly five letters long.",
            component=discord.ui.TextInput(
                placeholder="crane",
                min_length=5,
                max_length=5,
                required=True,
            ),
        )
        self.add_item(self.guess)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.game.author_id:
            await interaction.response.send_message(
                "This is not your Wordle game — start one with `/wordle`.",
                ephemeral=True,
            )
            return False
        return True

    async def on_submit(self, interaction: discord.Interaction) -> None:
        value = normalise_word(self.guess.component.value or "")
        if not is_word(value, 5):
            await interaction.response.send_message(
                "Please enter exactly five letters (no spaces, numbers or punctuation).",
                ephemeral=True,
            )
            return

        if value in self.game.guessed_words:
            await interaction.response.send_message(
                f"`{value.upper()}` has already been guessed.",
                ephemeral=True,
            )
            return

        await self.game.submit_guess(interaction, value)


class WordleGameView(GameLayoutView):
    """A Components V2 Wordle board."""

    def __init__(
        self,
        *,
        author: discord.abc.User,
        solution: str,
        puzzle_date: date_type | None = None,
        source: str = "NYT Wordle",
        editor: str | None = None,
    ) -> None:
        super().__init__(timeout=900)
        self.author_id = author.id
        self.solution = solution.lower()
        self.puzzle_date = puzzle_date
        self.source = source
        self.editor = editor
        self.status = "playing"
        self.guesses: list[tuple[str, list[str]]] = []

        accent = discord.Color.green() if puzzle_date else discord.Color.blurple()
        self.container = discord.ui.Container(accent_color=accent)
        self.heading = discord.ui.TextDisplay("")
        self.board = discord.ui.TextDisplay("")
        self.legend = discord.ui.TextDisplay(
            f"{score_emoji(['correct'])} correct position  •  "
            f"{score_emoji(['present'])} wrong position  •  "
            f"{score_emoji(['absent'])} not in the word"
        )
        self.footer = discord.ui.TextDisplay("")
        self.actions = discord.ui.ActionRow()

        self.guess_button = discord.ui.Button(
            label="Guess",
            emoji="✏️",
            style=discord.ButtonStyle.primary,
        )
        self.guess_button.callback = self.open_guess
        self.resign_button = discord.ui.Button(
            label="Resign",
            emoji="🏳️",
            style=discord.ButtonStyle.secondary,
        )
        self.resign_button.callback = self.resign
        self.again_button = discord.ui.Button(
            label="Play again",
            emoji="🔄",
            style=discord.ButtonStyle.success,
            disabled=True,
        )
        self.again_button.callback = self.play_again

        self.actions.add_item(self.guess_button)
        self.actions.add_item(self.resign_button)
        self.actions.add_item(self.again_button)

        self.container.add_item(self.heading)
        self.container.add_item(self.board)
        self.container.add_item(self.legend)
        self.container.add_item(self.actions)
        self.container.add_item(self.footer)
        self.add_item(self.container)
        self.refresh()

    # ------------------------------------------------------------------ state
    @property
    def guessed_words(self) -> set[str]:
        return {word for word, _ in self.guesses}

    def refresh(self) -> None:
        if self.puzzle_date is not None:
            title = f"## 🟩 Wordle — {self.puzzle_date:%B %d, %Y}"
        else:
            title = "## 🟩 Wordle — practice round"

        if self.status == "won":
            title += f"\n**Solved in {len(self.guesses)}/{MAX_GUESSES}!** 🎉"
        elif self.status == "lost":
            title += f"\n**Out of guesses — the word was `{self.solution.upper()}`.**"
        else:
            title += f"\nUse the button below to make guess **{len(self.guesses) + 1}/{MAX_GUESSES}**."
        self.heading.content = title

        rows: list[str] = []
        for index in range(MAX_GUESSES):
            if index < len(self.guesses):
                word, score = self.guesses[index]
                rows.append(f"`{index + 1}.` {score_emoji(score)}  **{word.upper()}**")
            else:
                rows.append(f"`{index + 1}.` {EMPTY * 5}")
        self.board.content = "\n".join(rows)

        source = self.source
        if self.editor:
            source += f" • edited by {self.editor}"
        if self.status == "playing":
            self.footer.content = f"-# Source: {source}"
        elif self.status == "won":
            self.footer.content = f"-# Nice work! Source: {source}"
        else:
            self.footer.content = f"-# The answer was **{self.solution.upper()}** • Source: {source}"

        self.guess_button.disabled = self.status != "playing"
        self.resign_button.disabled = self.status != "playing"
        self.again_button.disabled = self.status == "playing"

    async def submit_guess(self, interaction: discord.Interaction, word: str) -> None:
        if self.status != "playing":
            await interaction.response.send_message(
                "This Wordle game has already finished.",
                ephemeral=True,
            )
            return

        score = score_word(word, self.solution)
        self.guesses.append((word, score))

        if word == self.solution:
            self.status = "won"
        elif len(self.guesses) >= MAX_GUESSES:
            self.status = "lost"

        self.refresh()
        await interaction.response.edit_message(view=self)

    # -------------------------------------------------------------- callbacks
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "Only the player who started this Wordle can use it.",
            ephemeral=True,
        )
        return False

    async def open_guess(self, interaction: discord.Interaction) -> None:
        if self.status != "playing":
            await interaction.response.send_message(
                "This game is already over — use **Play again** for a fresh word.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(WordleGuessModal(self))

    async def resign(self, interaction: discord.Interaction) -> None:
        if self.status != "playing":
            await interaction.response.defer()
            return
        self.status = "lost"
        self.refresh()
        await interaction.response.edit_message(view=self)

    async def play_again(self, interaction: discord.Interaction) -> None:
        self.solution = random.choice(WORDLE_FALLBACK)
        self.puzzle_date = None
        self.source = "Practice word"
        self.editor = None
        self.guesses.clear()
        self.status = "playing"
        self.refresh()
        await interaction.response.edit_message(view=self)


class Wordle(commands.Cog):
    """Play the daily NYT Wordle (or a practice round)."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="wordle",
        description="Play Wordle using the official New York Times daily word.",
    )
    @user_app()
    @app_commands.describe(date="Puzzle date in YYYY-MM-DD format (defaults to today, UTC).")
    async def wordle(self, ctx: commands.Context, date: str | None = None) -> None:
        try:
            puzzle_date = parse_puzzle_date(date)
        except ValueError as exc:
            await ctx.send(str(exc))
            return

        await ctx.defer()

        payload = await fetch_json(self.bot, WORDLE_URL.format(day=puzzle_date.isoformat()))
        solution = ""
        editor = None
        if isinstance(payload, dict):
            solution = str(payload.get("solution") or "").lower()
            editor = payload.get("editor")

        if not is_word(solution, 5):
            log.warning("NYT Wordle endpoint returned no usable solution for %s; using fallback.", puzzle_date)
            solution = random.choice(WORDLE_FALLBACK)
            view = WordleGameView(
                author=ctx.author,
                solution=solution,
                puzzle_date=None,
                source="Practice word (NYT unavailable)",
            )
        else:
            view = WordleGameView(
                author=ctx.author,
                solution=solution,
                puzzle_date=puzzle_date,
                source="NYT Wordle",
                editor=editor,
            )

        message = await ctx.send(view=view)
        view.message = message


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Wordle(bot))
