import aiohttp
from discord.ext import commands
from discord import app_commands
import discord
from datetime import datetime, timezone
import random
from typing import Optional
import asyncio

class Animal(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.animal_apis = {
            "dog": "https://some-random-api.com/img/dog",
            "cat": "https://api.thecatapi.com/v1/images/search",
            "duck": "https://random-d.uk/api/v1/random",
            "fox": "https://randomfox.ca/floof/",
            "bunny": "https://api.bunnies.io/v2/loop/random/?media=gif,png",
            "bird": "https://some-random-api.com/img/bird",
            "lizard": "https://nekos.life/api/v2/img/lizard",
            "shiba": "https://shibe.online/api/shibes",
            "kangaroo": "https://some-random-api.com/img/kangaroo",
            "koala": "https://some-random-api.com/img/koala",
            "panda": "https://some-random-api.com/img/panda",
            "red_panda": "https://some-random-api.com/img/red_panda",
            "raccoon": "https://some-random-api.com/img/raccoon",
            "whale": "https://some-random-api.com/img/whale"
        }

    async def _fetch_animal_url(self, session: aiohttp.ClientSession, animal_key: str) -> Optional[str]:
        api_url = self.animal_apis.get(animal_key)
        if not api_url:
            return None

        async with session.get(api_url, timeout=5) as response:
            if response.status != 200:
                return None
            data = await response.json()

            if animal_key == "cat":
                return data[0]['url'] if isinstance(data, list) and data else None
            elif animal_key == "duck":
                return data.get('url')
            elif animal_key == "bunny":
                return data.get('media', {}).get('poster')
            elif animal_key == "dog":
                return data.get('link') or data.get('url')
            elif animal_key == "shiba":
                return random.choice(data) if isinstance(data, list) and data else None
            else:
                return data.get('link') or data.get('url')

    @commands.hybrid_command(name="animal", description="Sends a random picture of the specified animal!", aliases=['pet'])
    @app_commands.describe(animal='Pick an animal type')
    @app_commands.choices(animal=[
        app_commands.Choice(name='Dog', value="dog"),
        app_commands.Choice(name='Cat', value="cat"),
        app_commands.Choice(name='Bird', value="bird"),
        app_commands.Choice(name='Duck', value="duck"),
        app_commands.Choice(name='Bunny', value="bunny"),
        app_commands.Choice(name='Fox', value="fox"),
        app_commands.Choice(name='Panda', value="panda"),
        app_commands.Choice(name='Red Panda', value="red_panda"),
        app_commands.Choice(name='Koala', value="koala"),
        app_commands.Choice(name='Whale', value="whale"),
        app_commands.Choice(name='Raccoon', value="raccoon"),
        app_commands.Choice(name='Kangaroo', value="kangaroo"),
        app_commands.Choice(name='Lizard', value="lizard"),
        app_commands.Choice(name='Shiba', value="shiba"),
    ])
    async def animal(self, ctx: commands.Context, animal: Optional[str] = None):
        await ctx.defer()
        selected_animal = animal.lower() if animal else random.choice(list(self.animal_apis.keys()))

        if selected_animal not in self.animal_apis:
            await ctx.send(f"Sorry, I don't have images for `{selected_animal}`. Choose from: {', '.join(self.animal_apis.keys())}")
            return

        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            image_url = await self._fetch_animal_url(session, selected_animal)
            if not image_url:
                await ctx.send("Sorry, could not fetch an image from the animal API at this moment.")
                return

            display_name = selected_animal.replace('_', ' ').title()
            embed = discord.Embed(
                title=f"🐾 Random {display_name} just for you!",
                color=discord.Color.blue()
            )
            embed.set_image(url=image_url)
            embed.timestamp = datetime.now(timezone.utc)
            await ctx.send(embed=embed)

        except asyncio.TimeoutError:
            await ctx.send("Fetching the animal image timed out. The API may be experiencing downtime.")
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")
        finally:
            if close_session and session and not session.closed:
                await session.close()

async def setup(bot: commands.Bot):
    await bot.add_cog(Animal(bot))