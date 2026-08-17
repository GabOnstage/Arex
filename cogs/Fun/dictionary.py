import discord
from discord.ext import commands
import aiohttp
from urllib.parse import quote_plus

class Dictionary(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="dictionary", description="Look up a word's definition (English).")
    async def dictionary(self, ctx: commands.Context, *, word: str):
        await ctx.defer()
        word = word.strip()
        if not word:
            await ctx.send("Please provide a word to look up.")
            return

        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{quote_plus(word)}"
            async with session.get(url, timeout=6) as resp:
                if resp.status != 200:
                    await ctx.send(f"No definitions found for `{word}`.")
                    return
                data = await resp.json()
                if not isinstance(data, list) or not data:
                    await ctx.send(f"No definitions found for `{word}`.")
                    return
                entry = data[0]
                meanings = entry.get('meanings', [])
                embed = discord.Embed(title=f"Definition: {entry.get('word','')}", color=discord.Color.blue())
                for m in meanings[:4]:
                    part = m.get('partOfSpeech','')
                    defs = m.get('definitions', [])
                    if defs:
                        d = defs[0]
                        definition = d.get('definition','')
                        example = d.get('example')
                        value = definition
                        if example:
                            value += f"\n_Example_: {example}"
                        embed.add_field(name=part or 'Definition', value=value[:1024], inline=False)
                await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"Error while fetching definition: {e}")
        finally:
            if close_session and session and not session.closed:
                await session.close()

async def setup(bot: commands.Bot):
    await bot.add_cog(Dictionary(bot))
