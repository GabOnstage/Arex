import os
import sys
import asyncio
import logging
import aiohttp
import discord
from discord.ext import commands
from dotenv import load_dotenv
from colorama import init, Fore, Style

# Initialize Colorama and load dotenv
init()
load_dotenv()

# Configuration loading with safe fallbacks
discord_token = os.getenv('DISCORD_TOKEN')
app_id = os.getenv('APPLICATION_ID') or os.getenv('APPLICATONID')

raw_owners = os.getenv('OWNERS', '')
owners_id = [int(o.strip()) for o in raw_owners.split(',') if o.strip().isdigit()]

prefix = os.getenv('PREFIX', '!')

# Setup Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

discord.utils.setup_logging()

class ArexBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=prefix,
            intents=intents,
            application_id=int(app_id) if app_id and app_id.isdigit() else None,
            owner_ids=set(owners_id) if owners_id else None,
            help_command=None
        )
        self.session: aiohttp.ClientSession = None

    async def setup_hook(self):
        self.session = aiohttp.ClientSession()
        await self.load_all_extensions()
        # Note: sync cog is loaded via cogs/Admin during load_all_extensions

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
        await super().close()

    async def load_all_extensions(self):
        print(f"\n{Fore.CYAN}Loading Cogs...{Style.RESET_ALL}")
        cogs_dir = "./cogs"
        if not os.path.isdir(cogs_dir):
            return

        for subdir in os.listdir(cogs_dir):
            subdir_path = os.path.join(cogs_dir, subdir)
            if not os.path.isdir(subdir_path) or subdir.startswith("__"):
                continue

            print(f"   ├─── {subdir}")
            for filename in os.listdir(subdir_path):
                if filename.endswith(".py") and not filename.startswith("__"):
                    ext_name = f"cogs.{subdir}.{filename[:-3]}"
                    try:
                        await self.load_extension(ext_name)
                        print(f"   │      └─── {Fore.GREEN}{filename}{Style.RESET_ALL}")
                    except Exception as e:
                        print(f"   │      └─── {Fore.RED}{filename} (ERROR: {e}){Style.RESET_ALL}")

bot = ArexBot()

@bot.event
async def on_message(message):
    if message.author.bot:
        return
        
    print(f"[DEBUG] Saw message: {repr(message.content)}")
    print(f"[DEBUG] Bot Prefix is currently: {repr(bot.command_prefix)}")
    
    await bot.process_commands(message)
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.NotOwner):
        await ctx.send("You do not have permission to use this command.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("You are missing the required permissions to run this command.")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("I do not have the required permissions to execute this command.")
    else:
        print(f"Ignoring exception in command {ctx.command}:", file=sys.stderr)
        print(f"{error}", file=sys.stderr)

@bot.event
async def on_ready():
    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Game(name=f"Type {prefix}help for help")
    )
    print('__________________________________________')
    print(f'Connected to Discord as {Fore.GREEN}{bot.user}{Style.RESET_ALL} (ID: {bot.user.id})')
    print('__________________________________________')

async def main():
    if not discord_token:
        print(f"{Fore.RED}ERROR: DISCORD_TOKEN is not set in .env! Please configure it before starting.{Style.RESET_ALL}", file=sys.stderr)
        sys.exit(1)
    async with bot:
        await bot.start(discord_token)

if __name__ == "__main__":
    asyncio.run(main())