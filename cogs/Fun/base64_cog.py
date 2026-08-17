import discord
from discord.ext import commands
import base64
import asyncio
from typing import Optional

MAX_INPUT_LENGTH = 1000

class Base64Cog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="b64", invoke_without_command=True)
    async def b64(self, ctx: commands.Context):
        await ctx.send("Use subcommands `encode` or `decode`. Example: `!b64 encode hello`")

    @b64.command(name="encode")
    async def b64_encode(self, ctx: commands.Context, *, text: str):
        await ctx.defer()
        if not text:
            await ctx.send("Provide text to encode.")
            return
        if len(text) > MAX_INPUT_LENGTH:
            await ctx.send(f"Input too large (max {MAX_INPUT_LENGTH} chars).")
            return

        def do_encode(t: str) -> str:
            return base64.b64encode(t.encode('utf-8')).decode('utf-8')

        try:
            encoded = await asyncio.to_thread(do_encode, text)
            await ctx.send(f"Encoded (base64):\n```
{encoded}
```")
        except Exception as e:
            await ctx.send(f"Encoding failed: {e}")

    @b64.command(name="decode")
    async def b64_decode(self, ctx: commands.Context, *, data: str):
        await ctx.defer()
        if not data:
            await ctx.send("Provide base64 data to decode.")
            return
        if len(data) > MAX_INPUT_LENGTH:
            await ctx.send(f"Input too large (max {MAX_INPUT_LENGTH} chars).")

        def do_decode(d: str) -> Optional[str]:
            try:
                return base64.b64decode(d, validate=True).decode('utf-8', errors='replace')
            except Exception:
                return None

        decoded = await asyncio.to_thread(do_decode, data)
        if decoded is None:
            await ctx.send("Invalid base64 input or decode failed.")
        else:
            if len(decoded) > 1900:
                decoded = decoded[:1900] + "..."
            await ctx.send(f"Decoded (utf-8):\n```
{decoded}
```")

async def setup(bot: commands.Bot):
    await bot.add_cog(Base64Cog(bot))
