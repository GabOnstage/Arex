"""Connect 4 with button controls, two-player mode and a simple bot."""

from __future__ import annotations

import functools
import logging
import random
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.games import GameLayoutView
from utils.userapps import user_app

log = logging.getLogger("arex.connect4")

ROWS = 6
COLUMNS = 7
EMPTY = "⚫"
PIECES = {0: EMPTY, 1: "🔴", 2: "🟡"}


class Connect4View(GameLayoutView):
    def __init__(
        self,
        *,
        author: discord.abc.User,
        opponent: Optional[discord.abc.User] = None,
    ) -> None:
        super().__init__(timeout=1800)
        self.author = author
        self.opponent = opponent
        self.two_player = opponent is not None
        self.author_id = author.id
        self.opponent_id = opponent.id if opponent is not None else None
        self.board: list[list[int]] = [[0] * COLUMNS for _ in range(ROWS)]
        self.turn = 1
        self.status = "playing"
        self.winner_id: int | None = None

        self.container = discord.ui.Container(accent_color=discord.Color.red())
        self.heading = discord.ui.TextDisplay("")
        self.board_display = discord.ui.TextDisplay("")
        self.note = discord.ui.TextDisplay("")

        self.columns_row_1 = discord.ui.ActionRow()
        self.columns_row_2 = discord.ui.ActionRow()
        self.controls = discord.ui.ActionRow()
        self.column_buttons: list[discord.ui.Button] = []

        for column in range(COLUMNS):
            button = discord.ui.Button(
                label=str(column + 1),
                style=discord.ButtonStyle.primary,
                emoji="⬇️",
            )
            button.callback = functools.partial(self.drop, column=column)
            self.column_buttons.append(button)
            if column < 5:
                self.columns_row_1.add_item(button)
            else:
                self.columns_row_2.add_item(button)

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
        self.controls.add_item(self.resign_button)
        self.controls.add_item(self.again_button)

        self.container.add_item(self.heading)
        self.container.add_item(self.board_display)
        self.container.add_item(self.note)
        self.container.add_item(self.columns_row_1)
        self.container.add_item(self.columns_row_2)
        self.container.add_item(self.controls)
        self.add_item(self.container)
        self.refresh()

    # ------------------------------------------------------------------ state
    @property
    def players(self) -> set[int]:
        ids = {self.author_id}
        if self.opponent_id is not None:
            ids.add(self.opponent_id)
        return ids

    @property
    def via_bot(self) -> bool:
        return not self.two_player

    def current_player_id(self) -> int:
        if self.turn == 1:
            return self.author_id
        return self.opponent_id if self.opponent_id is not None else -1

    def lowest_empty(self, column: int) -> int | None:
        for row in range(ROWS):
            if self.board[row][column] == 0:
                return row
        return None

    def _check_win(self, row: int, column: int, player: int) -> bool:
        for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
            count = 1
            for sign in (1, -1):
                r = row + dr * sign
                c = column + dc * sign
                while 0 <= r < ROWS and 0 <= c < COLUMNS and self.board[r][c] == player:
                    count += 1
                    r += dr * sign
                    c += dc * sign
            if count >= 4:
                return True
        return False

    def _place(self, column: int, player: int) -> int | None:
        row = self.lowest_empty(column)
        if row is None:
            return None
        self.board[row][column] = player
        return row

    def _after_move(self, row: int, column: int, player: int) -> None:
        if self._check_win(row, column, player):
            self.status = "won"
            self.winner_id = self.author_id if player == 1 else self.opponent_id
            if self.via_bot and player == 2:
                self.status = "lost"
            return

        if all(self.board[ROWS - 1][c] != 0 for c in range(COLUMNS)):
            self.status = "draw"
            return

        self.turn = 2 if self.turn == 1 else 1
        if self.via_bot and self.turn == 2:
            self._bot_move()

    def _would_win(self, column: int, player: int) -> bool:
        row = self.lowest_empty(column)
        if row is None:
            return False
        self.board[row][column] = player
        won = self._check_win(row, column, player)
        self.board[row][column] = 0
        return won

    def _bot_move(self) -> None:
        if self.status != "playing":
            return

        valid = [column for column in range(COLUMNS) if self.lowest_empty(column) is not None]
        if not valid:
            self.status = "draw"
            return

        winning = [column for column in valid if self._would_win(column, 2)]
        blocking = [column for column in valid if self._would_win(column, 1)]
        if winning:
            column = random.choice(winning)
        elif blocking:
            column = random.choice(blocking)
        else:
            # Prefer the centre, with a little randomness so games differ.
            best = min(abs(column - 3) for column in valid)
            column = random.choice([item for item in valid if abs(item - 3) == best])

        row = self._place(column, 2)
        if row is not None:
            self._after_move(row, column, 2)

    def refresh(self) -> None:
        self.heading.content = "## 🔴 Connect 4"
        if self.two_player and self.opponent is not None:
            self.heading.content += f"\n{self.author.mention} vs {self.opponent.mention}"
        else:
            self.heading.content += "\nYou vs the bot"

        lines: list[str] = []
        for row in reversed(range(ROWS)):
            lines.append(" ".join(PIECES[cell] for cell in self.board[row]))
        lines.append("1️⃣ 2️⃣ 3️⃣ 4️⃣ 5️⃣ 6️⃣ 7️⃣")
        self.board_display.content = "\n".join(lines)

        if self.status == "won":
            if self.via_bot:
                self.note.content = "### 🎉 You win!"
            else:
                winner = self.author.mention if self.winner_id == self.author_id else (
                    self.opponent.mention if self.opponent is not None else "The winner"
                )
                self.note.content = f"### 🎉 {winner} wins!"
        elif self.status == "lost":
            self.note.content = "### 🤖 The bot wins this round."
        elif self.status == "draw":
            self.note.content = "### 🤝 It's a draw!"
        elif self.status == "resigned":
            self.note.content = "### 🏳️ Game resigned."
        else:
            if self.via_bot:
                self.note.content = "**Your turn** — choose a column."
            else:
                current = self.author.mention if self.turn == 1 else (
                    self.opponent.mention if self.opponent is not None else "?"
                )
                self.note.content = f"**{current}'s turn** — choose a column."

        playing = self.status == "playing"
        for column, button in enumerate(self.column_buttons):
            button.disabled = not playing or self.lowest_empty(column) is None
        self.resign_button.disabled = not playing
        self.again_button.disabled = playing

    def reset(self) -> None:
        self.board = [[0] * COLUMNS for _ in range(ROWS)]
        self.turn = 1
        self.status = "playing"
        self.winner_id = None
        self.refresh()

    # -------------------------------------------------------------- callbacks
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id in self.players:
            return True
        await interaction.response.send_message(
            "Only the players in this game can use these buttons.",
            ephemeral=True,
        )
        return False

    async def drop(self, interaction: discord.Interaction, column: int) -> None:
        if self.status != "playing":
            await interaction.response.defer()
            return
        if self.two_player and interaction.user.id != self.current_player_id():
            await interaction.response.send_message(
                "It is not your turn yet.",
                ephemeral=True,
            )
            return
        if self.via_bot and interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This is a single-player game — start your own with `/connect4`.",
                ephemeral=True,
            )
            return

        row = self._place(column, self.turn)
        if row is None:
            await interaction.response.send_message(
                f"Column **{column + 1}** is already full.",
                ephemeral=True,
            )
            return

        self._after_move(row, column, self.turn)
        self.refresh()
        await interaction.response.edit_message(view=self)

    async def resign(self, interaction: discord.Interaction) -> None:
        if self.status != "playing":
            await interaction.response.defer()
            return
        self.status = "resigned"
        self.refresh()
        await interaction.response.edit_message(view=self)

    async def play_again(self, interaction: discord.Interaction) -> None:
        self.reset()
        await interaction.response.edit_message(view=self)


class Connect4(commands.Cog):
    """Drop four pieces in a row before your opponent does."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="connect4",
        aliases=["c4"],
        description="Play Connect 4 against a friend or the bot.",
    )
    @user_app()
    @app_commands.describe(opponent="Challenge another user, or leave empty to play the bot.")
    async def connect4(
        self,
        ctx: commands.Context,
        opponent: Optional[discord.User] = None,
    ) -> None:
        if opponent is not None and (opponent.bot or opponent.id == ctx.author.id):
            opponent = None

        view = Connect4View(author=ctx.author, opponent=opponent)
        message = await ctx.send(view=view)
        view.message = message


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Connect4(bot))
