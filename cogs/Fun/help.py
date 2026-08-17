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
                "• `/find`: Comprehensive Roblox user lookup.\n"
                "• `/badge`: Search user Roblox badges."
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
                "• `/f1`: Formula 1 latest race standings."
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
                "• `/tempchannel`: Create auto-expiring temporary channels."
            ),
            inline=False
        )

        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))