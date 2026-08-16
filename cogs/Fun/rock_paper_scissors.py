import discord
from discord.ext import commands
from typing import Optional

async def is_valid_opponent(ctx: commands.Context, opponent: Optional[discord.Member]) -> bool:
    if opponent is None:
        await ctx.send("Please mention a valid server member to challenge!")
        return False
    if opponent.id == ctx.author.id:
        await ctx.send("You cannot play rock-paper-scissors against yourself!")
        return False
    if opponent.bot:
        await ctx.send("You cannot challenge a bot!")
        return False
    return True

class RPSMenu(discord.ui.View):
    def __init__(self, ctx: commands.Context, opponent: discord.Member):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.opponent = opponent

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green, emoji='✅')
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            f"Rock Paper Scissors match started! Make your choice: {self.ctx.author.mention} vs {self.opponent.mention}",
            view=RPSGame(self.ctx, self.opponent)
        )
        self.stop()

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red, emoji='🛑')
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"{self.opponent.mention} declined the match challenge.")
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.opponent.id:
            return True
        await interaction.response.send_message(f"Only {self.opponent.mention} can accept or decline this challenge.", ephemeral=True)
        return False

    async def on_timeout(self):
        try:
            await self.ctx.send(f"{self.opponent.mention} took too long to respond to the match invitation.")
        except Exception:
            pass

class RPSGame(discord.ui.View):
    def __init__(self, ctx: commands.Context, opponent: discord.Member, selection=None):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.opponent = opponent
        self.selection = selection if selection is not None else [None, None]

    async def button_response(self, interaction: discord.Interaction, choice: int):
        if interaction.user.id == self.ctx.author.id:
            self.selection[0] = choice
        elif interaction.user.id == self.opponent.id:
            self.selection[1] = choice

        if self.selection[0] is not None and self.selection[1] is not None:
            choices = ('None', 'Rock', 'Paper', 'Scissors')
            choice_author = choices[self.selection[0]]
            choice_opponent = choices[self.selection[1]]

            if self.selection[0] == self.selection[1]:
                winner_text = "It's a Tie!"
            elif self.selection[0] == (self.selection[1] % 3) + 1:
                winner_text = f"🏆 **Winner:** {self.ctx.author.mention}"
            else:
                winner_text = f"🏆 **Winner:** {self.opponent.mention}"

            result_embed = discord.Embed(
                title="🎮 Rock Paper Scissors - Result",
                description=(
                    f"{self.ctx.author.mention} chose `{choice_author}`\n"
                    f"{self.opponent.mention} chose `{choice_opponent}`\n\n"
                    f"{winner_text}"
                ),
                color=discord.Color.gold()
            )
            await interaction.response.edit_message(content=None, embed=result_embed, view=None)
            self.stop()
        else:
            author_status = "✅ Made choice" if self.selection[0] else "⏳ Deciding..."
            opponent_status = "✅ Made choice" if self.selection[1] else "⏳ Deciding..."
            await interaction.response.edit_message(
                content=(
                    f"**Rock Paper Scissors Match**\n"
                    f"{self.ctx.author.mention}: {author_status}\n"
                    f"{self.opponent.mention}: {opponent_status}"
                )
            )

    @discord.ui.button(label="Rock", emoji='🪨', style=discord.ButtonStyle.primary)
    async def rock(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.button_response(interaction, 1)

    @discord.ui.button(label="Paper", emoji='📄', style=discord.ButtonStyle.primary)
    async def paper(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.button_response(interaction, 2)

    @discord.ui.button(label="Scissors", emoji='✂️', style=discord.ButtonStyle.primary)
    async def scissors(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.button_response(interaction, 3)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id in (self.ctx.author.id, self.opponent.id):
            return True
        await interaction.response.send_message(
            f"Only {self.ctx.author.mention} and {self.opponent.mention} are part of this game.",
            ephemeral=True
        )
        return False

    async def on_timeout(self):
        try:
            await self.ctx.send("The Rock Paper Scissors game has expired due to inactivity.")
        except Exception:
            pass

class Games(commands.Cog):
    """Mini-games to play with friends."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="rockpaperscissors", aliases=['rps'], description="Play Rock Paper Scissors against a server member.")
    async def rockpaperscissors(self, ctx: commands.Context, opponent: discord.Member):
        """Play Rock Paper Scissors with a friend."""
        if not await is_valid_opponent(ctx, opponent):
            return
        await ctx.send(
            f"{opponent.mention}, you have been challenged to Rock Paper Scissors by {ctx.author.mention}! Do you accept?",
            view=RPSMenu(ctx, opponent)
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(Games(bot))