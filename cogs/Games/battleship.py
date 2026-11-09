"""Battleship against a small target-hunting bot."""

from __future__ import annotations

import logging
import random
import re
from dataclasses import dataclass, field

import discord
from discord.ext import commands

from utils.games import GameLayoutView, column_label
from utils.userapps import user_app

log = logging.getLogger("arex.battleship")

GRID_SIZE = 10
SHIPS: tuple[tuple[str, int], ...] = (
    ("Carrier", 5),
    ("Battleship", 4),
    ("Cruiser", 3),
    ("Submarine", 3),
    ("Destroyer", 2),
)

_COORD_RE = re.compile(r"^([A-J])(10|[1-9])$")


def parse_coordinate(value: str) -> int | None:
    value = (value or "").strip().upper().replace(" ", "")
    match = _COORD_RE.match(value)
    if match is None:
        return None
    row = ord(match.group(1)) - ord("A")
    column = int(match.group(2)) - 1
    return row * GRID_SIZE + column


def coordinate_name(index: int) -> str:
    return f"{column_label(index // GRID_SIZE)}{(index % GRID_SIZE) + 1}"


@dataclass(slots=True)
class Ship:
    name: str
    size: int
    cells: set[int] = field(default_factory=set)
    hits: set[int] = field(default_factory=set)

    @property
    def sunk(self) -> bool:
        return len(self.hits) >= self.size

    @property
    def remaining(self) -> int:
        return max(0, self.size - len(self.hits))


class Board:
    """A 10x10 board with randomly placed ships."""

    def __init__(self) -> None:
        self.ships: list[Ship] = []
        self.shots: set[int] = set()
        self.place_ships()

    def place_ships(self) -> None:
        while True:
            self.ships.clear()
            occupied: set[int] = set()
            success = True

            for name, size in SHIPS:
                placed = False
                for _ in range(500):
                    horizontal = random.choice((True, False))
                    if horizontal:
                        row = random.randrange(GRID_SIZE)
                        column = random.randrange(GRID_SIZE - size + 1)
                        cells = {
                            row * GRID_SIZE + column + offset
                            for offset in range(size)
                        }
                    else:
                        row = random.randrange(GRID_SIZE - size + 1)
                        column = random.randrange(GRID_SIZE)
                        cells = {
                            (row + offset) * GRID_SIZE + column
                            for offset in range(size)
                        }

                    if cells & occupied:
                        continue
                    occupied.update(cells)
                    self.ships.append(Ship(name, size, cells))
                    placed = True
                    break

                if not placed:
                    success = False
                    break

            if success:
                return

    @property
    def all_sunk(self) -> bool:
        return all(ship.sunk for ship in self.ships)

    def ship_at(self, index: int) -> Ship | None:
        return next((ship for ship in self.ships if index in ship.cells), None)

    def receive_shot(self, index: int) -> str:
        self.shots.add(index)
        ship = self.ship_at(index)
        if ship is None:
            return "miss"
        ship.hits.add(index)
        return "sunk" if ship.sunk else "hit"

    def unshot_cells(self) -> list[int]:
        return [index for index in range(GRID_SIZE * GRID_SIZE) if index not in self.shots]


def _grid_header() -> str:
    return "    " + " ".join(str(number) for number in range(1, GRID_SIZE + 1))


def render_grid(board: Board, *, hide_ships: bool = False) -> str:
    lines = [_grid_header()]
    for row in range(GRID_SIZE):
        cells: list[str] = []
        for column in range(GRID_SIZE):
            index = row * GRID_SIZE + column
            ship = board.ship_at(index)
            if index in board.shots:
                cells.append("X" if ship is not None else "O")
            elif ship is not None and not hide_ships:
                cells.append("S")
            else:
                cells.append("·")
        lines.append(f"{column_label(row)}   " + " ".join(cells))
    return "```\n" + "\n".join(lines) + "\n```"


class BattleshipFireModal(discord.ui.Modal):
    def __init__(self, game: "BattleshipView") -> None:
        super().__init__(title="Fire at enemy waters", timeout=120)
        self.game = game
        self.coordinate = discord.ui.Label(
            text="Target coordinate",
            description="Enter a square from A1 to J10, for example B7.",
            component=discord.ui.TextInput(
                placeholder="B7",
                min_length=2,
                max_length=3,
                required=True,
            ),
        )
        self.add_item(self.coordinate)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.game.author_id:
            return True
        await interaction.response.send_message(
            "Only the player who started this game can fire.",
            ephemeral=True,
        )
        return False

    async def on_submit(self, interaction: discord.Interaction) -> None:
        index = parse_coordinate(self.coordinate.component.value or "")
        if index is None:
            await interaction.response.send_message(
                "That is not a valid square. Use a letter **A–J** and a number **1–10**, like `B7`.",
                ephemeral=True,
            )
            return

        if index in self.game.enemy.shots:
            await interaction.response.send_message(
                f"You already fired at **{coordinate_name(index)}**.",
                ephemeral=True,
            )
            return

        self.game.player_fire(index)
        await interaction.response.edit_message(view=self.game)


class BattleshipView(GameLayoutView):
    def __init__(self, *, author: discord.abc.User) -> None:
        super().__init__(timeout=1800)
        self.author_id = author.id
        self.player = Board()
        self.enemy = Board()
        self.status = "playing"
        self.targets: list[int] = []
        self.last_message = "Fleets deployed. Your move!"

        self.container = discord.ui.Container(accent_color=discord.Color.dark_teal())
        self.heading = discord.ui.TextDisplay("")
        self.status_display = discord.ui.TextDisplay("")
        self.own_display = discord.ui.TextDisplay("")
        self.enemy_display = discord.ui.TextDisplay("")
        self.fleet_display = discord.ui.TextDisplay("")
        self.actions = discord.ui.ActionRow()

        self.fire_button = discord.ui.Button(
            label="Fire",
            emoji="🎯",
            style=discord.ButtonStyle.primary,
        )
        self.fire_button.callback = self.fire
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
        self.actions.add_item(self.fire_button)
        self.actions.add_item(self.resign_button)
        self.actions.add_item(self.again_button)

        self.container.add_item(self.heading)
        self.container.add_item(self.status_display)
        self.container.add_item(self.own_display)
        self.container.add_item(self.enemy_display)
        self.container.add_item(self.fleet_display)
        self.container.add_item(self.actions)
        self.add_item(self.container)
        self.refresh()

    # ------------------------------------------------------------------ state
    def player_fire(self, index: int) -> None:
        if self.status != "playing":
            return

        result = self.enemy.receive_shot(index)
        target = coordinate_name(index)
        if result == "miss":
            self.last_message = f"You fired at **{target}** — miss. 🌊"
        elif result == "hit":
            self.last_message = f"You fired at **{target}** — **hit!** 💥"
        else:
            self.last_message = f"You fired at **{target}** — **ship sunk!** 🔥"

        if self.enemy.all_sunk:
            self.status = "won"
            self.refresh()
            return

        self.bot_turn()
        self.refresh()

    def bot_turn(self) -> None:
        if self.status != "playing":
            return

        available = [index for index in self.targets if index not in self.player.shots]
        if not available:
            self.targets.clear()

        if available:
            index = random.choice(available)
            self.targets.remove(index)
        else:
            choices = self.player.unshot_cells()
            if not choices:
                return
            index = random.choice(choices)

        result = self.player.receive_shot(index)
        target = coordinate_name(index)

        if result in {"hit", "sunk"}:
            # Hunt around the hit on the bot's next turn.
            row, column = divmod(index, GRID_SIZE)
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = row + dr, column + dc
                if 0 <= nr < GRID_SIZE and 0 <= nc < GRID_SIZE:
                    candidate = nr * GRID_SIZE + nc
                    if candidate not in self.player.shots and candidate not in self.targets:
                        self.targets.append(candidate)

        if self.player.all_sunk:
            self.status = "lost"
            self.last_message = f"The bot fired at **{target}** and sank your last ship. 💀"
        elif result == "miss":
            self.last_message += f" The bot fired at **{target}** — miss."
        elif result == "hit":
            self.last_message += f" The bot fired at **{target}** — hit! 💥"
        else:
            self.last_message += f" The bot fired at **{target}** — a ship was sunk! 🔥"

    def refresh(self) -> None:
        self.heading.content = "## 🚢 Battleship"
        if self.status == "won":
            self.status_display.content = f"### 🎉 Victory!\n{self.last_message}"
        elif self.status == "lost":
            self.status_display.content = f"### 💀 Defeat\n{self.last_message}"
        elif self.status == "resigned":
            self.status_display.content = "### 🏳️ You resigned.\nThe enemy fleet is revealed below."
        else:
            self.status_display.content = f"{self.last_message}\n**Your turn — fire at the enemy fleet.**"

        self.own_display.content = "**Your fleet**\n" + render_grid(self.player)
        self.enemy_display.content = "**Enemy waters**\n" + render_grid(
            self.enemy,
            hide_ships=self.status == "playing",
        )

        lines: list[str] = ["**Enemy ships**"]
        for ship in self.enemy.ships:
            if ship.sunk:
                lines.append(f"~~{ship.name}~~ — sunk ☠️")
            else:
                lines.append(f"{ship.name} — {ship.remaining}/{ship.size} left")
        self.fleet_display.content = "\n".join(lines)

        playing = self.status == "playing"
        self.fire_button.disabled = not playing
        self.resign_button.disabled = not playing
        self.again_button.disabled = playing

    # -------------------------------------------------------------- callbacks
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(
            "Only the player who started this game can use it.",
            ephemeral=True,
        )
        return False

    async def fire(self, interaction: discord.Interaction) -> None:
        if self.status != "playing":
            await interaction.response.defer()
            return
        await interaction.response.send_modal(BattleshipFireModal(self))

    async def resign(self, interaction: discord.Interaction) -> None:
        if self.status != "playing":
            await interaction.response.defer()
            return
        self.status = "resigned"
        self.refresh()
        await interaction.response.edit_message(view=self)

    async def play_again(self, interaction: discord.Interaction) -> None:
        self.player = Board()
        self.enemy = Board()
        self.status = "playing"
        self.targets.clear()
        self.last_message = "New fleets deployed. Your move!"
        self.refresh()
        await interaction.response.edit_message(view=self)


class Battleship(commands.Cog):
    """Sink the bot's fleet before it sinks yours."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="battleship",
        description="Play Battleship against the bot on a 10×10 grid.",
    )
    @user_app()
    async def battleship(self, ctx: commands.Context) -> None:
        view = BattleshipView(author=ctx.author)
        message = await ctx.send(view=view)
        view.message = message


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Battleship(bot))
