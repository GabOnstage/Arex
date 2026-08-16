import discord
from discord.ext import commands
import aiohttp

class Joke(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_group(name="joke", fallback="random", description="Tells a random joke")
    async def joke(self, ctx: commands.Context) -> None:
        await self.randomjoke(ctx)

    @joke.command(name="dad", description="Sends a funny Dad joke")
    async def dadjoke(self, ctx: commands.Context):
        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            headers = {'Accept': 'application/json'}
            async with session.get("https://icanhazdadjoke.com/", headers=headers, timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    joke = data.get('joke', 'No joke found.')
                    embed = discord.Embed(title="👨 Dad Joke", description=joke, color=discord.Color.blue())
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("Failed to fetch Dad joke. Please try again later.")
        except Exception as e:
            await ctx.send(f"Error fetching joke: {e}")
        finally:
            if close_session and session and not session.closed:
                await session.close()

    @joke.command(name="chucknorris", description="Sends a Chuck Norris joke")
    async def chuckjoke(self, ctx: commands.Context):
        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            async with session.get("https://api.chucknorris.io/jokes/random", timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    joke = data.get('value', 'No joke found.')
                    embed = discord.Embed(title="🤠 Chuck Norris Joke", description=joke, color=discord.Color.gold())
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("Failed to fetch Chuck Norris joke.")
        except Exception as e:
            await ctx.send(f"Error fetching joke: {e}")
        finally:
            if close_session and session and not session.closed:
                await session.close()

    @joke.command(name="programming", description="Sends a Programming joke")
    async def progjoke(self, ctx: commands.Context):
        await self._fetch_jokeapi(ctx, "Programming", "💻 Programming Joke")

    @joke.command(name="dark", description="Sends a Dark humor joke")
    async def darkjoke(self, ctx: commands.Context):
        await self._fetch_jokeapi(ctx, "Dark", "🖤 Dark Joke")

    @joke.command(name="pun", description="Sends a Pun joke")
    async def punjoke(self, ctx: commands.Context):
        await self._fetch_jokeapi(ctx, "Pun", "🎭 Pun")

    @joke.command(name="spooky", description="Sends a Spooky Halloween joke")
    async def spookyjoke(self, ctx: commands.Context):
        await self._fetch_jokeapi(ctx, "Spooky", "🎃 Spooky Joke")

    @joke.command(name="random", description="Sends a Random category joke")
    async def randomjoke(self, ctx: commands.Context):
        await self._fetch_jokeapi(ctx, "Any", "😂 Random Joke")

    async def _fetch_jokeapi(self, ctx: commands.Context, category: str, title: str):
        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            url = f"https://v2.jokeapi.dev/joke/{category}?blacklistFlags=nsfw,religious,political,racist,sexist,explicit"
            async with session.get(url, timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    joke_type = data.get('type')
                    if joke_type == 'single':
                        text = data.get('joke', '')
                    elif joke_type == 'twopart':
                        text = f"{data.get('setup', '')}\n\n*{data.get('delivery', '')}*"
                    else:
                        text = "Unable to parse joke."
                    embed = discord.Embed(title=title, description=text, color=discord.Color.green())
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("Failed to retrieve a joke from JokeAPI.")
        except Exception as e:
            await ctx.send(f"Error fetching joke: {e}")
        finally:
            if close_session and session and not session.closed:
                await session.close()

async def setup(bot: commands.Bot):
    await bot.add_cog(Joke(bot))