import os
import discord
from discord.ext import commands
from typing import Optional
import aiohttp
import io

MAX_FILE_SIZE = 8 * 1024 * 1024  # 8 MB


class AvatarFun(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="avatar", description="Process an attached image (or your avatar) through the jeyy image API.")
    async def avatar(self, ctx: commands.Context, file: Optional[discord.Attachment] = None):
        """Applies an effect to an uploaded image or your avatar."""
        await ctx.defer()

        api_token = os.getenv('jeyy_api')
        if not api_token:
            await ctx.send("The `jeyy_api` key is not configured in `.env`. Please add it to use avatar image filters.")
            return

        # Slash: explicit attachment param. Prefix: fall back to message attachments.
        if file is None and ctx.message and ctx.message.attachments:
            file = ctx.message.attachments[0]

        if file is not None:
            if file.size > MAX_FILE_SIZE:
                await ctx.send(f"Image too large (max {MAX_FILE_SIZE // (1024 * 1024)} MB).")
                return
            content_type = file.content_type or "image/jpeg"
            if not content_type.startswith("image/"):
                await ctx.send("Please attach a valid image file.")
                return
            file_name = file.filename or "image.jpg"
            file_bytes = await file.read()
        else:
            # Fall back to the invoker's own avatar.
            asset = ctx.author.display_avatar.replace(size=512, format="png")
            file_name = "avatar.png"
            content_type = "image/png"
            try:
                file_bytes = await asset.read()
            except Exception as e:
                await ctx.send(f"Could not download your avatar: {e}")
                return

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
