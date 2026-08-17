import discord
from discord.ext import commands
from urllib.parse import quote_plus

class QR(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="qr", description="Create a QR code from text (returns image URL).")
    async def qr(self, ctx: commands.Context, *, text: str):
        await ctx.defer()
        if not text:
            await ctx.send("Please provide text to encode into a QR code.")
            return
        if len(text) > 2000:
            await ctx.send("Text too long for QR generation (limit 2000 characters).")
            return
        data = quote_plus(text)
        url = f"https://api.qrserver.com/v1/create-qr-code/?size=400x400&data={data}"
        embed = discord.Embed(title="QR Code", description="Here is your QR code:", color=discord.Color.green())
        embed.set_image(url=url)
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(QR(bot))
