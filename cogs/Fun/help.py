import logging
import discord
from discord.ext import commands
from utils.userapps import user_app

log = logging.getLogger("arex.help")


CATEGORIES = {
    "admin": {
        "title": "「 🛠️ 」Moderation & Admin Commands",
        "color": discord.Color.red(),
        "emoji": "🛠️",
        "description": "Bot administration & management",
        "commands": [
            "`/al` — View verified allowed bot admins.",
            "`/close` — Safely shut down the bot session.",
            "`!sync` — Synchronize slash commands with Discord.",
            "`/locate` — Geolocation lookup for IP/Domain.",
            "`/userinfo` — Detailed user information & Discord badges.",
            "`/tempchannel` — Create auto-expiring temporary channels.",
        ],
    },
    "games": {
        "title": "「 🎮 」Games",
        "color": discord.Color.green(),
        "emoji": "🎮",
        "description": "Roblox, Minecraft & mini-games",
        "commands": [
            "`/roblox user <user>` — Comprehensive Roblox user lookup.",
            "`/roblox badge <user>` — Search user Roblox badges.",
            "`/roblox rotector-user <id>` — Rotector user flag info.",
            "`/roblox rotector-user-plain <id>` — Rotector user status (plaintext).",
            "`/roblox rotector-user-batch <ids>` — Rotector batch user lookup.",
            "`/roblox rotector-user-status-batch <ids>` — Rotector batch user statuses.",
            "`/roblox rotector-user-discord <id>` — Linked Discord accounts for Roblox user.",
            "`/roblox rotector-group <id>` — Rotector group flag info.",
            "`/roblox rotector-group-plain <id>` — Rotector group status (plaintext).",
            "`/roblox rotector-group-batch <ids>` — Rotector batch group lookup.",
            "`/roblox rotector-group-tracked <id>` — Tracked users in a Roblox group.",
            "`/roblox rotector-discord <id>` — Rotector Discord user info.",
            "`/roblox rotector-discord-batch <ids>` — Rotector batch Discord lookup.",
            "`/mc server <address>` — Minecraft server status & stats.",
            "`/mc skin <username>` — Minecraft user skin & profile lookup.",
            "`/rockpaperscissors` — Play RPS with a friend.",
            "`/guesspokemon` — Who's That Pokemon mini-game.",
            "`/coinflip` — Flip a coin.",
            "`/wordle [date]` — NYT daily Wordle with an interactive board.",
            "`/crosswords [mini|daily] [date]` — Solve the NYT crossword clue by clue.",
            "`/hangman [easy|medium|hard]` — Classic Hangman with letter menus.",
            "`/battleship` — Sink the bot's fleet on a 10×10 grid.",
            "`/connect4 [opponent]` — Drop four in a row against a friend or the bot.",
        ],
    },
    "fun": {
        "title": "「 🎉 」Fun & Social",
        "color": discord.Color.gold(),
        "emoji": "🎉",
        "description": "Social, jokes, memes & reactions",
        "commands": [
            "`/truth` — Random truth question.",
            "`/dare` — Dare challenges.",
            "`/nhie` — Never Have I Ever statements.",
            "`/wyr` — Would You Rather questions.",
            "`/paranoia` — Paranoia questions.",
            "`/advice` — Words of wisdom & life advice.",
            "`/rizz` — Smooth & funny pickup lines.",
            "`/ship <user1> <user2>` — Calculate compatibility between two users.",
            "`/ppsize [user]` — Scientifically measure PP size.",
            "`/gayness [user]` — Measure someone's gay percentage.",
            "`/smashorpass [user]` — The ultimate verdict on a user.",
            "`/waifu [tag] [animated]` — Random SFW anime images from waifu.im.",
            "`/yiffy_sfw [category]` — Random SFW furry images from the Yiffy API.",
            "`/anime search <title>` — Search anime info on Kitsu.",
            "`/anime quote` — Random anime quote.",
            "`/action <type> [user]` — Anime reaction GIFs (hug, slap, pat...).",
            "`/joke` — Dad, Programming, Chuck Norris, and Dark jokes.",
            "`/ball` — Magic 8-ball answers.",
            "`/meme` — Random popular meme.",
            "`/animal` — Cute random animal photos.",
            "`/insult` — Generate a playful insult.",
            "`/quote` — Inspirational quotes.",
        ],
    },
    "utils": {
        "title": "「 ⚙️ 」Utilities & Info",
        "color": discord.Color.blue(),
        "emoji": "⚙️",
        "description": "Tools, lookups & handy info",
        "commands": [
            "`/ping` — Check bot latency and responsiveness.",
            "`/color` — Detailed RGB/Hex color information.",
            "`/apod` — NASA Astronomy Picture of the Day.",
            "`/echo` — Repeat a message safely.",
            "`/dictionary` — Look up word definitions.",
            "`/qr` — Generate a QR code from text.",
            "`/b64 encode|decode` — Base64 encoder/decoder.",
            "`/hn` — Top Hacker News stories.",
            "`/weather` — Current weather via Open-Meteo.",
            "`/f1` — Formula 1 latest race standings.",
            "`/movie search <query>` — Search IMDB for movies & shows.",
            "`/embed` — Fix social media links so they embed properly.",
            "`/testhelp` — Interactive categorized help menu.",
        ],
    },
}


def build_overview_embed() -> discord.Embed:
    embed = discord.Embed(
        title="📖 Command Categories",
        description=(
            "Select a category from the dropdown below to view its commands.\n\n"
            + "\n".join(
                f"{data['emoji']} — **{data['title'].split('」')[1].strip()}** · {data['description']}"
                for data in CATEGORIES.values()
            )
        ),
        color=discord.Color.blurple(),
    )
    embed.set_footer(text="Use the dropdown to browse categories.")
    return embed


def build_category_embed(category: str) -> discord.Embed:
    data = CATEGORIES[category]
    embed = discord.Embed(
        title=data["title"],
        description="\n".join(f"• {cmd}" for cmd in data["commands"]),
        color=data["color"],
    )
    embed.set_footer(text="Use the dropdown to switch categories.")
    return embed


class HelpView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This help menu isn't yours — run the help command yourself!",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.select(placeholder="📂 Select a category...")
    async def select_category(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.edit_message(embed=build_category_embed(select.values[0]))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="help", description="Show the list of available commands.")
    @user_app()
    async def help(self, ctx: commands.Context):
        view = HelpView(ctx.author.id)

        options = [
            discord.SelectOption(
                label=data["title"].split("」")[1].strip(),
                value=key,
                emoji=data["emoji"],
                description=data["description"],
            )
            for key, data in CATEGORIES.items()
        ]
        view.select_category.options = options

        message = await ctx.send(embed=build_overview_embed(), view=view)
        view.message = message


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
