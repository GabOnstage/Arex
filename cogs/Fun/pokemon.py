import discord
import random
import aiohttp
import asyncio
from discord.ext import commands

class Pokemon(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="guesspokemon", description="Play a Who's That Pokemon guessing game!")
    async def guesspokemon(self, ctx: commands.Context):
        await ctx.defer()
        
        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            # Pick a random Pokemon ID (Gen 1-9 species range: 1 to 1025)
            random_number = random.randint(1, 1010)

            async with session.get(f"https://pokeapi.co/api/v2/pokemon-species/{random_number}", timeout=10) as response:
                if response.status != 200:
                    await ctx.send("Failed to fetch Pokemon data from PokeAPI. Please try again later.")
                    return
                pokemon_data = await response.json()

            pokemon_name = pokemon_data['name'].capitalize()
            image_url = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/{random_number}.png"

            embed = discord.Embed(
                title="🤔 Who's That Pokemon?",
                description="Look at the image below and type the name of this Pokemon in chat within **20 seconds**!",
                color=discord.Color.red()
            )
            embed.set_image(url=image_url)
            embed.set_footer(text="Type your guess in this channel!")
            await ctx.send(embed=embed)

            def check(msg: discord.Message):
                return msg.author.id == ctx.author.id and msg.channel.id == ctx.channel.id

            try:
                msg = await self.bot.wait_for('message', timeout=20.0, check=check)

                if msg.content.strip().lower() == pokemon_name.lower():
                    win_embed = discord.Embed(
                        title="🎉 Correct!",
                        description=f"Great job! The Pokemon was indeed **{pokemon_name}**!",
                        color=discord.Color.green()
                    )
                    await ctx.send(embed=win_embed)
                else:
                    fail_embed = discord.Embed(
                        title="❌ Incorrect",
                        description=f"Sorry, that's not right. The correct Pokemon was **{pokemon_name}**.",
                        color=discord.Color.red()
                    )
                    await ctx.send(embed=fail_embed)

            except asyncio.TimeoutError:
                timeout_embed = discord.Embed(
                    title="⏰ Time's Up!",
                    description=f"You took too long to answer. The Pokemon was **{pokemon_name}**.",
                    color=discord.Color.orange()
                )
                await ctx.send(embed=timeout_embed)

        except Exception as e:
            await ctx.send(f"An error occurred: {e}")
        finally:
            if close_session and session and not session.closed:
                await session.close()

async def setup(bot: commands.Bot):
    await bot.add_cog(Pokemon(bot))