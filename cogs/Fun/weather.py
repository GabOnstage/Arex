import discord
from discord.ext import commands
import aiohttp
from urllib.parse import quote_plus

class Weather(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="weather", description="Get current weather for a place (uses Open-Meteo).")
    async def weather(self, ctx: commands.Context, *, location: str):
        await ctx.defer()
        q = location.strip()
        if not q:
            await ctx.send('Provide a location to search for.')
            return
        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True
        try:
            geourl = f"https://geocoding-api.open-meteo.com/v1/search?name={quote_plus(q)}&count=1"
            async with session.get(geourl, timeout=6) as g:
                if g.status != 200:
                    await ctx.send('Location not found via geocoding.')
                    return
                gdata = await g.json()
                results = gdata.get('results')
                if not results:
                    await ctx.send('Location not found.')
                    return
                place = results[0]
                lat = place.get('latitude')
                lon = place.get('longitude')
                name = f"{place.get('name')}, {place.get('country')}"

            weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
            async with session.get(weather_url, timeout=6) as w:
                if w.status != 200:
                    await ctx.send('Failed to fetch weather data.')
                    return
                wdata = await w.json()
                cur = wdata.get('current_weather', {})
                temp = cur.get('temperature')
                wind = cur.get('windspeed')
                weather_code = cur.get('weathercode')
                embed = discord.Embed(title=f'Weather — {name}', color=discord.Color.teal())
                embed.add_field(name='Temperature (°C)', value=str(temp), inline=True)
                embed.add_field(name='Wind (km/h)', value=str(wind), inline=True)
                embed.add_field(name='Weather Code', value=str(weather_code), inline=True)
                await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f'Error fetching weather: {e}')
        finally:
            if close_session and session and not session.closed:
                await session.close()

async def setup(bot: commands.Bot):
    await bot.add_cog(Weather(bot))
