import discord
from discord.ext import commands

class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def create_command_list(self):
        embed = discord.Embed(
            title="Command List",
            color=discord.Color.blue()
        )
        return embed

    @commands.hybrid_command(name="help", description="Show the list of available commands.")
    async def help(self, ctx: commands.Context):
        embed = self.create_command_list()
        
        embed.add_field(
            name="「 🛠️ 」Moderation & Admin Commands",
            value=(
                "• `/al`: View verified allowed bot admins.\n"
                "• `/close`: Safely shut down the bot session.\n"
                "• `!sync`: Synchronize slash commands with Discord.\n"
                "• `/locate`: Geolocation lookup for IP/Domain.\n"
                "• `/userinfo`: Detailed user information & Discord badges.\n"
                "• `/tempchannel`: Create auto-expiring temporary channels."
            ),
            inline=False
        )

        embed.add_field(
            name="「 🎮 」Roblox & Minecraft",
            value=(
                "• `/find`: Comprehensive Roblox user lookup.\n"
                "• `/badge`: Search user Roblox badges.\n"
                "• `/rotector_user` / `/rotector_group` / `/rotector_discord`: Rotector flag lookups "
                "(also `_plain`, `_batch`, `_status_batch`, `_tracked` variants).\n"
                "• `/mcserver`: Minecraft server status & stats.\n"
                "• `/mcskin`: Minecraft user skin & profile lookup."
            ),
            inline=False
        )
        
        embed.add_field(
            name="「 🎉 」Fun, Games & Party Commands",
            value=(
                "• `/truth`: Random truth question.\n"
                "• `/dare` & `/dare_nsfw`: Dare challenges (PG / 18+).\n"
                "• `/nhie`: Never Have I Ever statements.\n"
                "• `/wyr`: Would You Rather questions.\n"
                "• `/paranoia`: Paranoia questions.\n"
                "• `/advice`: Words of wisdom & life advice.\n"
                "• `/rizz`: Smooth & funny pickup lines.\n"
                "• `/joke`: Dad, Programming, Chuck Norris, and Dark jokes.\n"
                "• `/ball`: Magic 8-ball answers.\n"
                "• `/meme`: Random popular meme.\n"
                "• `/animal`: Cute random animal photos.\n"
                "• `/insult`: Generate a playful insult.\n"
                "• `/rockpaperscissors`: Play RPS with a friend.\n"
                "• `/guesspokemon`: Who's That Pokemon mini-game.\n"
                "• `/quote`: Inspirational quotes.\n"
                "• `/f1`: Formula 1 latest race standings.\n"
                "• `/imdb`: Search IMDB for movies & shows."
            ),
            inline=False
        )

        embed.add_field(
            name="「 ⚙️ 」Utilities",
            value=(
                "• `/ping`: Check bot latency and responsiveness.\n"
                "• `/color`: Detailed RGB/Hex color information.\n"
                "• `/apod`: NASA Astronomy Picture of the Day.\n"
                "• `/echo`: Repeat a message safely.\n"
                "• `/dictionary`: Look up word definitions.\n"
                "• `/qr`: Generate a QR code from text.\n"
                "• `/b64 encode|decode`: Base64 encoder/decoder.\n"
                "• `/hn`: Top Hacker News stories.\n"
                "• `/weather`: Current weather via Open-Meteo.\n"
                "• `/testhelp`: Interactive categorized help menu."
            ),
            inline=False
        )

        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))