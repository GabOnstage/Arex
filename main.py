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

prefix = os.getenv('COMMAND', '!')

# Guard against misconfigured prefixes (e.g. shell paths like $PREFIX leaking
# into .env on Termux: "/data/data/com.termux/files/usr").
if not prefix or len(prefix) > 10 or prefix.startswith('/') or any(ch.isspace() for ch in prefix):
    print(
        f"{Fore.YELLOW}WARNING: COMMAND in .env is invalid ({prefix!r}). "
        f"Falling back to '!'. Fix COMMAND in your .env file.{Style.RESET_ALL}"
    )
    prefix = '!'

# Setup Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

discord.utils.setup_logging()
log = logging.getLogger('arex')

class ArexBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=prefix,
            case_insensitive=True,
            intents=intents,
            application_id=int(app_id) if app_id and app_id.isdigit() else None,
            owner_ids=set(owners_id) if owners_id else None,
            help_command=None
        )
        self.session: aiohttp.ClientSession = None
        self._warned_empty_content = False

    async def setup_hook(self):
        self.session = aiohttp.ClientSession()
        await self.load_all_extensions()

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
        await super().close()

    async def load_all_extensions(self):
        print(f"\n{Fore.CYAN}Loading Cogs...{Style.RESET_ALL}")
        cogs_dir = "./cogs"
        if not os.path.isdir(cogs_dir):
            return

        loaded, failed = 0, 0
        for subdir in sorted(os.listdir(cogs_dir)):
            subdir_path = os.path.join(cogs_dir, subdir)
            if not os.path.isdir(subdir_path) or subdir.startswith("__"):
                continue

            print(f"   ├─── {subdir}")
            for filename in sorted(os.listdir(subdir_path)):
                if filename.endswith(".py") and not filename.startswith("__"):
                    ext_name = f"cogs.{subdir}.{filename[:-3]}"
                    try:
                        await self.load_extension(ext_name)
                        loaded += 1
                        print(f"   │      └─── {Fore.GREEN}{filename}{Style.RESET_ALL}")
                    except Exception as e:
                        failed += 1
                        print(f"   │      └─── {Fore.RED}{filename} (ERROR: {e}){Style.RESET_ALL}")
                        log.error("Failed to load extension %s", ext_name, exc_info=e)

        print(f"{Fore.CYAN}Cog loading finished: {loaded} loaded, {failed} failed.{Style.RESET_ALL}")

bot = ArexBot()

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Diagnostic: if we receive guild messages with empty content, the
    # MESSAGE CONTENT INTENT is disabled in the Developer Portal.
    if not message.content and not bot._warned_empty_content and message.guild:
        bot._warned_empty_content = True
        print(
            f"{Fore.YELLOW}WARNING: Received a guild message with empty content. "
            f"Enable 'MESSAGE CONTENT INTENT' in the Developer Portal (Bot -> Privileged Gateway Intents), "
            f"then restart the bot — otherwise prefix commands will never trigger.{Style.RESET_ALL}"
        )

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
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"This command is on cooldown. Try again in `{error.retry_after:.1f}s`.")
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
    print(f'Prefix commands registered: {len(bot.commands)} | App commands: {len(bot.tree.get_commands())}')
    print(f'Prefix: {prefix!r} | Owners configured: {len(owners_id)}')
    print('__________________________________________')
    if len(bot.commands) == 0:
        print(f'{Fore.RED}WARNING: No prefix commands registered — check cog load errors above.{Style.RESET_ALL}')

async def main():
    if not discord_token:
        print(f"{Fore.RED}ERROR: DISCORD_TOKEN is not set in .env! Please configure it before starting.{Style.RESET_ALL}", file=sys.stderr)
        sys.exit(1)
    async with bot:
        await bot.start(discord_token)

if __name__ == "__main__":
    asyncio.run(main())
