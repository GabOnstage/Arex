import os
import discord
from discord.ext import commands
import aiohttp
import io

class AvatarFun(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_group(name="avatar", fallback="abstract", description="Image processing and avatar filters.")
    async def avatar(self, ctx: commands.Context, file: discord.Attachment) -> None:
        """Applies an abstract effect to the uploaded image."""
        api_token = os.getenv('jeyy_api')
        if not api_token:
            await ctx.send("The `jeyy_api` key is not configured in `.env`. Please add it to use avatar image filters.")
            return

        if not file:
            await ctx.send("Please attach an image file to process.")
            return

        await ctx.defer()
        file_bytes = await file.read()
        file_name = file.filename or "image.jpg"
        content_type = file.content_type or "image/jpeg"
        api_url = 'https://api.jeyy.xyz/v2/general/image_upload'

        session = getattr(self.bot, 'session', None)
        close_session = False
        if session is None or session.closed:
            session = aiohttp.ClientSession()
            close_session = True

        try:
            data = aiohttp.FormData()
            data.add_field('image', io.BytesIO(file_bytes), filename=file_name, content_type=content_type)
            headers = {
                'Authorization': f'Bearer {api_token}',
                'accept': 'application/json'
            }

            async with session.post(api_url, headers=headers, data=data, timeout=15) as response:
                if response.status == 200:
                    json_response = await response.json()
                    image_url = json_response.get('url')
                    if image_url:
                        embed = discord.Embed(title="🎨 Processed Image", color=discord.Color.magenta())
                        embed.set_image(url=image_url)
                        await ctx.send(embed=embed)
                    else:
                        await ctx.send("Image processed, but no image URL was returned.")
                else:
                    err_text = await response.text()
                    await ctx.send(f"Failed to process image (Status {response.status}): {err_text[:200]}")
        except Exception as e:
            await ctx.send(f"Error processing image: {e}")
        finally:
            if close_session and session and not session.closed:
                await session.close()

async def setup(bot: commands.Bot):
    await bot.add_cog(AvatarFun(bot))