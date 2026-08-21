import base64
import asyncio
import time
from typing import Optional
import discord
from discord.ext import commands

MAX_INPUT_LENGTH = 1000
COOLDOWN_SECONDS = 3.0


class Base64Cog(commands.Cog):
    """Base64 encode/decode with input limits and per-user cooldowns
    to prevent CPU overload from abuse."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._cooldowns: dict[int, float] = {}

    async def _check_cooldown(self, ctx: commands.Context) -> bool:
        now = time.monotonic()
        last = self._cooldowns.get(ctx.author.id, 0.0)
        if now - last < COOLDOWN_SECONDS:
            remaining = round(COOLDOWN_SECONDS - (now - last), 1)
            await ctx.send(f"Slow down! Try again in `{remaining}s`.", ephemeral=True)
            return False
        self._cooldowns[ctx.author.id] = now
        return True

    @commands.hybrid_group(name="b64", invoke_without_command=True,
                            description="Base64 encode/decode. Use `encode` or `decode` subcommands.")
    async def b64(self, ctx: commands.Context):
        await ctx.send("Use subcommands `encode` or `decode`. Example: `!b64 encode hello`")

    @b64.command(name="encode", description="Encode text to Base64.")
    async def b64_encode(self, ctx: commands.Context, *, text: str):
        if not await self._check_cooldown(ctx):
            return
        await ctx.defer()
        if len(text) > MAX_INPUT_LENGTH:
            await ctx.send(f"Input too large (max {MAX_INPUT_LENGTH} chars).")
            return

        def do_encode(t: str) -> str:
            return base64.b64encode(t.encode('utf-8')).decode('utf-8')

        try:
            encoded = await asyncio.to_thread(do_encode, text)
            if len(encoded) > 1900:
                encoded = encoded[:1900] + "..."
            await ctx.send(f"Encoded (base64):\n```\n{encoded}\n```")
        except Exception as e:
            await ctx.send(f"Encoding failed: {e}")

    @b64.command(name="decode", description="Decode Base64 text.")
    async def b64_decode(self, ctx: commands.Context, *, data: str):
        if not await self._check_cooldown(ctx):
            return
        await ctx.defer()
        if len(data) > MAX_INPUT_LENGTH:
            await ctx.send(f"Input too large (max {MAX_INPUT_LENGTH} chars).")
            return

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
            await ctx.send(f"Decoded (utf-8):\n```\n{decoded}\n```")


async def setup(bot: commands.Bot):
    await bot.add_cog(Base64Cog(bot))
