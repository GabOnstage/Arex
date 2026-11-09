"""A modern button/select based Hangman game."""

from __future__ import annotations

import logging
import random
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

from utils.games import GameLayoutView
from utils.userapps import user_app
from utils.wordlists import hangman_pool

log = logging.getLogger("arex.hangman")

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
MAX_MISTAKES = 6


def _hangman_art(mistakes: int) -> str:
    head = "O" if mistakes >= 1 else " "
    torso = "|" if mistakes >= 2 else " "
    left_arm = "/" if mistakes >= 3 else " "
    right_arm = "\\" if mistakes >= 4 else " "
    left_leg = "/" if mistakes >= 5 else " "
    right_leg = "\\" if mistakes >= 6 else " "

    return "\n".join(
        (
            "  +---+",
            "  |   |",
            f"  {head}   |",
            f" {left_arm}{torso}{right_arm}  |",
            f" {left_leg} {right_leg}  |",
            "      |",
            "=========",
        )
    )


class HangmanView(GameLayoutView):
    def __init__(
        self,
        *,
        author: discord.abc.User,
        word: str,
        category: str,
        difficulty: str,
    ) -> None:
        super().__init__(timeout=900)
        self.author_id = author.id
        self.word = word.upper()
        self.category = category
        self.difficulty = difficulty
        self.guessed: set[str] = set()
        self.mistakes = 0
        self.status = "playing"

        self.container = discord.ui.Container(accent_color=discord.Color.orange())
        self.heading = discord.ui.TextDisplay("")
        self.art = discord.ui.TextDisplay("")
        self.word_display = discord.ui.TextDisplay("")
        self.letter_row_1 = discord.ui.ActionRow()
        self.letter_row_2 = discord.ui.ActionRow()
        self.button_row = discord.ui.ActionRow()

        self.select_1 = self._make_select(ALPHABET[:13], "Guess a letter (A–M)")
        self.select_2 = self._make_select(ALPHABET[13:], "Guess a letter (N–Z)")
        self.letter_row_1.add_item(self.select_1)
        self.letter_row_2.add_item(self.select_2)

        self.new_button = discord.ui.Button(
            label="New word",
            emoji="🔄",
            style=discord.ButtonStyle.success,
        )
        self.new_button.callback = self.new_word
        self.resign_button = discord.ui.Button(
            label="Resign",
            emoji="🏳️",
            style=discord.ButtonStyle.secondary,
        )
        self.resign_button.callback = self.resign
        self.button_row.add_item(self.new_button)
        self.button_row.add_item(self.resign_button)

        self.container.add_item(self.heading)
        self.container.add_item(self.art)
        self.container.add_item(self.word_display)
        self.container.add_item(self.letter_row_1)
        self.container.add_item(self.letter_row_2)
        self.container.add_item(self.button_row)
        self.add_item(self.container)
        self.refresh()

    def _make_select(self, letters: str, placeholder: str) -> discord.ui.Select:
        select = discord.ui.Select(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=[discord.SelectOption(label=letter, value=letter) for letter in letters],
        )
        select.callback = self.guess_letter
        return select

    # ------------------------------------------------------------------ state
    @property
    def won(self) -> bool:
        return all(letter in self.guessed for letter in self.word)

    @property
    def lost(self) -> bool:
        return self.mistakes >= MAX_MISTAKES

    @property
    def remaining(self) -> int:
        return MAX_MISTAKES - self.mistakes

    def refresh(self) -> None:
        self.heading.content = (
            f"## 🪢 Hangman — {self.category}\n"
            f"Difficulty: **{self.difficulty.title()}** • "
            f"Lives left: **{self.remaining}/{MAX_MISTAKES}**"
        )
        self.art.content = "```\n" + _hangman_art(self.mistakes) + "\n```"
        display = " ".join(letter if letter in self.guessed else "_" for letter in self.word)
        wrong = " ".join(sorted(letter for letter in self.guessed if letter not in self.word))

        if self.status == "won":
            extra = f"\n\n🎉 **You solved it!** The word was **{self.word}**."
        elif self.status == "lost":
            extra = f"\n\n💀 **Out of lives.** The word was **{self.word}**."
        else:
            extra = f"\n\nWrong letters: {wrong or '—'}"

        self.word_display.content = f"### `{display}`{extra}"

        for select, letters in ((self.select_1, ALPHABET[:13]), (self.select_2, ALPHABET[13:])):
            available = [letter for letter in letters if letter not in self.guessed]
            if available:
                select.options = [
                    discord.SelectOption(label=letter, value=letter)
                    for letter in available
                ]
            else:
                select.options = [discord.SelectOption(label="All guessed", value="__done__")]
            select.disabled = self.status != "playing" or not available

        self.resign_button.disabled = self.status != "playing"

    def reset(self, word: str, category: str) -> None:
        self.word = word.upper()
        self.category = category
        self.guessed.clear()
        self.mistakes = 0
        self.status = "playing"
        self.refresh()

    def apply_letter(self, letter: str) -> None:
        letter = letter.upper()
        if len(letter) != 1 or letter not in ALPHABET:
            return
        if letter in self.guessed or self.status != "playing":
            return

        self.guessed.add(letter)
        if letter not in self.word:
            self.mistakes += 1

        if self.won:
            self.status = "won"
        elif self.lost:
            self.status = "lost"
        self.refresh()

    # -------------------------------------------------------------- callbacks
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "Only the player who started this Hangman game can use it.",
            ephemeral=True,
        )
        return False

    async def guess_letter(self, interaction: discord.Interaction) -> None:
        if self.status != "playing":
            await interaction.response.defer()
            return

        values = (interaction.data or {}).get("values") or []
        if not values:
            await interaction.response.defer()
            return

        self.apply_letter(values[0])
        await interaction.response.edit_message(view=self)

    async def new_word(self, interaction: discord.Interaction) -> None:
        pool = hangman_pool(self.difficulty) or hangman_pool("medium")
        word, category = random.choice(pool)
        self.reset(word, category)
        await interaction.response.edit_message(view=self)

    async def resign(self, interaction: discord.Interaction) -> None:
        if self.status != "playing":
            await interaction.response.defer()
            return
        self.status = "lost"
        self.refresh()
        await interaction.response.edit_message(view=self)


class Hangman(commands.Cog):
    """Guess the hidden word before the stick figure is complete."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="hangman",
        description="Play Hangman with an interactive letter picker.",
    )
    @user_app()
    @app_commands.describe(difficulty="Choose how long the hidden word should be.")
    async def hangman(
        self,
        ctx: commands.Context,
        difficulty: Literal["easy", "medium", "hard"] = "medium",
    ) -> None:
        difficulty = (difficulty or "medium").lower()
        if difficulty not in {"easy", "medium", "hard"}:
            await ctx.send("Choose `easy`, `medium` or `hard`.")
            return

        pool = hangman_pool(difficulty) or hangman_pool("medium")
        word, category = random.choice(pool)
        view = HangmanView(
            author=ctx.author,
            word=word,
            category=category,
            difficulty=difficulty,
        )
        message = await ctx.send(view=view)
        view.message = message


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Hangman(bot))
