import discord
from discord.ext import commands
import random
from typing import Optional
import aiohttp

class ColorView(discord.ui.View):
    def __init__(self, color_name: str, hex_number: str, rgb_values: dict, html_url: str, *, timeout=180):
        super().__init__(timeout=timeout)
        self.html_url = html_url
        self.add_item(discord.ui.Button(label="Advanced Color Info", style=discord.ButtonStyle.link, url=html_url, emoji="🖌️"))

    @discord.ui.button(label="Randomize Color", emoji="🎲", style=discord.ButtonStyle.primary)
    async def random_color(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        red = random.randint(0, 255)
        green = random.randint(0, 255)
        blue = random.randint(0, 255)

        api_url = f'https://www.thecolorapi.com/id?rgb={red},{green},{blue}&format=json'

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, timeout=5) as response:
                    if response.status == 200:
                        response_data = await response.json()
                    else:
                        await interaction.followup.send("Failed to fetch new color from TheColorAPI.", ephemeral=True)
                        return

            color_name = response_data['name']['value']
            hex_number = response_data['hex']['value']
            rgb_str = f"R: {red}, G: {green}, B: {blue}"
            new_html_url = f'https://www.thecolorapi.com/id?rgb={red},{green},{blue}&format=html'
            image_url = f'https://fakeimg.pl/720x400/{hex_number[1:]}/fff/?text=+'
            thumbnail_url = f'https://fakeimg.pl/450x450/{hex_number[1:]}/fff/?text=+'

            embed = discord.Embed(title=color_name, url=new_html_url, color=discord.Color.from_rgb(red, green, blue))
            embed.add_field(name='Hex', value=f"`{hex_number}`", inline=True)
            embed.add_field(name='RGB', value=f"`{rgb_str}`", inline=True)
            embed.set_image(url=image_url)
            embed.set_thumbnail(url=thumbnail_url)

            new_view = ColorView(color_name, hex_number, {'r': red, 'g': green, 'b': blue}, new_html_url)
            await interaction.edit_original_response(embed=embed, view=new_view)
        except Exception as e:
            await interaction.followup.send(f"Error updating color: {e}", ephemeral=True)

class ColorInfo(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="color", description="Get color information by RGB or generate a random color.")
    async def color(self, ctx: commands.Context, red: Optional[int] = None, green: Optional[int] = None, blue: Optional[int] = None):
        """Show color information."""
        await ctx.defer()

        # If any value is not provided, generate random RGB
        if red is None or green is None or blue is None:
            red = random.randint(0, 255)
            green = random.randint(0, 255)
            blue = random.randint(0, 255)

        # Validate range
        if not (0 <= red <= 255 and 0 <= green <= 255 and 0 <= blue <= 255):
            await ctx.send('Please enter valid RGB values between 0 and 255.')
            return

        api_url = f'https://www.thecolorapi.com/id?rgb={red},{green},{blue}&format=json'

        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            async with session.get(api_url, timeout=5) as response:
                if response.status != 200:
                    await ctx.send("Failed to retrieve color data from TheColorAPI.")
                    return
                response_data = await response.json()

            color_name = response_data['name']['value']
            hex_number = response_data['hex']['value']
            rgb_str = f"R: {red}, G: {green}, B: {blue}"
            html_url = f'https://www.thecolorapi.com/id?rgb={red},{green},{blue}&format=html'

            image_url = f'https://fakeimg.pl/720x400/{hex_number[1:]}/fff/?text=+'
            thumbnail_url = f'https://fakeimg.pl/450x450/{hex_number[1:]}/fff/?text=+'

            embed = discord.Embed(title=color_name, url=html_url, color=discord.Color.from_rgb(red, green, blue))
            embed.add_field(name='Hex', value=f"`{hex_number}`", inline=True)
            embed.add_field(name='RGB', value=f"`{rgb_str}`", inline=True)
            embed.set_image(url=image_url)
            embed.set_thumbnail(url=thumbnail_url)

            view = ColorView(color_name, hex_number, {'r': red, 'g': green, 'b': blue}, html_url)
            await ctx.send(embed=embed, view=view)

        except Exception as e:
            await ctx.send(f"Error fetching color information: {e}")
        finally:
            if close_session and session and not session.closed:
                await session.close()

    @color.error
    async def color_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.MissingRequiredArgument):
            r, g, b = random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)
            await self.color.callback(self, ctx, red=r, green=g, blue=b)
        elif isinstance(error, commands.BadArgument):
            embed_error = discord.Embed(
                title="Invalid Input",
                description="Please provide valid numerical RGB values between 0 and 255.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed_error, ephemeral=True)
        else:
            await ctx.send(f"An error occurred: {error}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ColorInfo(bot))