import discord
from discord.ext import commands
from datetime import datetime, timedelta, timezone
import json
import os
from typing import Optional
import re
import asyncio

class TempChannel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.temp_dir = "./data/temp_channels"
        os.makedirs(self.temp_dir, exist_ok=True)

    @staticmethod
    def parse_duration(duration_str: str) -> int:
        match = re.match(r'(?:(?P<days>\d+)d)?(?:(?P<hours>\d+)h)?(?:(?P<minutes>\d+)m)?(?:(?P<seconds>\d+)s)?', duration_str.strip().lower())
        if match and any(match.groupdict().values()):
            duration = timedelta(
                days=int(match.group('days') or 0),
                hours=int(match.group('hours') or 0),
                minutes=int(match.group('minutes') or 0),
                seconds=int(match.group('seconds') or 0)
            )
            return max(int(duration.total_seconds()), 10)  # Minimum 10 seconds
        else:
            raise ValueError("Invalid duration format. Use formats like '1d', '24h', '1h', '30m', or '60s'.")

    async def check_deletion_time(self, guild_id: int, channel_id: int, file_path: str, deletion_seconds: int):
        await asyncio.sleep(min(deletion_seconds, 10))
        while True:
            if not os.path.exists(file_path):
                break
            try:
                with open(file_path, "r") as file:
                    channel_info = json.load(file)
                created_at = datetime.fromisoformat(channel_info["created_at"])
                deletion_time = created_at + timedelta(seconds=channel_info.get("deletion_seconds", deletion_seconds))
                if datetime.now(timezone.utc) >= deletion_time:
                    await self.delete_temp_channel(guild_id, channel_id, file_path)
                    break
            except Exception:
                break
            await asyncio.sleep(10)

    @commands.hybrid_command(name="tempchannel", description="Creates a self-destructing temporary channel.")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def create_temp_channel(self, ctx: commands.Context, name: str, description: Optional[str] = None, nsfw: str = "no", deletion_time: Optional[str] = "24h"):
        """Create a temporary text channel with auto-deletion timer."""
        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return

        try:
            is_nsfw = nsfw.strip().lower() in ("yes", "y", "true", "1")
            deletion_seconds = self.parse_duration(deletion_time or "24h")

            # Permission overwrites
            overwrites = {
                ctx.guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True),
                ctx.guild.me: discord.PermissionOverwrite(read_messages=True, manage_channels=True, manage_messages=True, send_messages=True, read_message_history=True)
            }

            channel = await ctx.guild.create_text_channel(
                name=name,
                overwrites=overwrites,
                topic=description or f"Temporary channel. Auto-deletes in {deletion_time}.",
                nsfw=is_nsfw
            )

            file_path = os.path.join(self.temp_dir, f"{channel.id}.json")
            channel_info = {
                "guild_id": ctx.guild.id,
                "channel_id": channel.id,
                "name": channel.name,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "deletion_seconds": deletion_seconds
            }
            with open(file_path, "w") as file:
                json.dump(channel_info, file)

            asyncio.create_task(self.check_deletion_time(ctx.guild.id, channel.id, file_path, deletion_seconds))

            embed = discord.Embed(
                title="✅ Temporary Channel Created",
                description=f"Channel {channel.mention} created successfully!",
                color=discord.Color.green()
            )
            embed.add_field(name="Name", value=channel.name, inline=True)
            embed.add_field(name="NSFW", value="Yes" if is_nsfw else "No", inline=True)
            embed.add_field(name="Auto-Deletion", value=f"In `{deletion_time}`", inline=True)
            embed.timestamp = datetime.now(timezone.utc)
            await ctx.send(embed=embed)

        except ValueError as ve:
            await ctx.send(f"⚠️ {ve}")
        except Exception as e:
            await ctx.send(f"Failed to create temporary channel: {e}")

    async def delete_temp_channel(self, guild_id: int, channel_id: int, file_path: str):
        try:
            guild = self.bot.get_guild(guild_id)
            if guild:
                channel = guild.get_channel(channel_id)
                if channel:
                    await channel.delete(reason="Temporary channel expired.")
        except Exception:
            pass
        finally:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass

async def setup(bot: commands.Bot):
    await bot.add_cog(TempChannel(bot))