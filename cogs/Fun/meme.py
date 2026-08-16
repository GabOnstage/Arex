import discord
from discord.ext import commands
import aiohttp

class Meme(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="meme", description="Fetches a random popular meme from Reddit.")
    async def meme(self, ctx: commands.Context):
        await ctx.defer()
        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            async with session.get('https://meme-api.com/gimme', timeout=6) as response:
                if response.status == 200:
                    meme_data = await response.json()
                    title = meme_data.get('title', 'Random Meme')
                    post_url = meme_data.get('postLink', 'https://reddit.com')
                    image_url = meme_data.get('url')
                    author = meme_data.get('author', 'reddit')
                    subreddit = meme_data.get('subreddit', 'memes')
                    ups = meme_data.get('ups', 0)

                    meme_embed = discord.Embed(
                        title=title[:256],
                        url=post_url,
                        color=discord.Color.orange()
                    )
                    if image_url:
                        meme_embed.set_image(url=image_url)
                    meme_embed.set_footer(text=f"r/{subreddit} • Posted by u/{author} • 👍 {ups:,}")

                    await ctx.send(embed=meme_embed)
                else:
                    await ctx.send('Failed to fetch a meme from the meme API.')
        except Exception as e:
            await ctx.send(f'Sorry, could not retrieve a meme right now: {e}')
        finally:
            if close_session and session and not session.closed:
                await session.close()

async def setup(bot: commands.Bot):
    await bot.add_cog(Meme(bot))
