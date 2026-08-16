import discord
from discord.ext import commands
from discord import app_commands
from typing import List

class FruitChoices(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name='dynachoice', description="Example static autocomplete choices.")
    async def fruits(self, ctx: commands.Context, fruits: str):
        await ctx.send(f'Your favourite fruit seems to be `{fruits}`')

    @fruits.autocomplete('fruits')
    async def fruits_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        fruit_list = [
            'Apple', 'Banana', 'Blackberry', 'Blueberry', 'Cherry', 'Dragonfruit',
            'Grape', 'Kiwi', 'Lemon', 'Lime', 'Mango', 'Melon', 'Orange',
            'Peach', 'Pear', 'Pineapple', 'Plum', 'Raspberry', 'Strawberry', 'Watermelon'
        ]
        query = current.lower()
        matches = [f for f in fruit_list if query in f.lower()]
        return [app_commands.Choice(name=fruit, value=fruit) for fruit in matches][:25]

async def setup(bot: commands.Bot):
    await bot.add_cog(FruitChoices(bot))