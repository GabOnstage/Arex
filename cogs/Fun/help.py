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
                "• `/locate`: Geolocation lookup for IP/Domain.\n"
                "• `/userinfo`: Detailed user information & Discord badges.\n"
                "• `/find`: Comprehensive Roblox user lookup.\n"
                "• `/badge`: Search user Roblox badges."
            ),
            inline=False
        )
        
        embed.add_field(
            name="「 🎉 」Fun & Utility Commands",
            value=(
                "• `/ball`: Magic 8-ball answers.\n"
                "• `/meme`: Random meme.\n"
                "• `/ping`: Check bot latency.\n"
                "• `/insult`: Generate a playful insult.\n"
                "• `/apod`: NASA Astronomy Picture of the Day.\n"
                "• `/color`: Detailed RGB/Hex color information.\n"
                "• `/f1`: Latest Formula 1 race results.\n"
                "• `/guesspokemon`: Guess the Pokemon mini-game.\n"
                "• `/rockpaperscissors`: Play RPS with a friend.\n"
                "• `/quote`: Random inspirational quote.\n"
                "• `/tempchannel`: Create auto-expiring temporary channels."
            ),
            inline=False
        )

        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))