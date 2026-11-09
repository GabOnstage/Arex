import logging
import os
import discord
from discord.ext import commands
from discord import app_commands
from reactionmenu import ViewButton, ViewMenu, ViewSelect, Page
from utils.userapps import user_app

log = logging.getLogger("arex.help_menu")


class HelpMenu(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def get_section_content(self, section_name: str) -> str:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        filename = os.path.join(current_dir, "..", "..", "utils", "help.md")
        section_content = []
        inside_section = False

        start_tag = f"<___{section_name}-start___>"
        end_tag = f"<___{section_name}-end___>"

        if not os.path.isfile(filename):
            return "Help documentation file not found."

        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                stripped = line.strip()
                if stripped == start_tag:
                    inside_section = True
                elif stripped == end_tag:
                    inside_section = False
                elif inside_section:
                    section_content.append(line.rstrip())

        return '\n'.join(section_content) if section_content else "No documentation found for this section."

    @commands.hybrid_command(name="testhelp", description="Get information about commands via interactive menu")
    @user_app()
    @app_commands.rename(group='category')
    @app_commands.describe(group='Select a Category')
    @app_commands.choices(group=[
        app_commands.Choice(name='Admin', value="admin"),
        app_commands.Choice(name='Games', value="roblox"),
        app_commands.Choice(name='Fun & Social', value="fun"),
        app_commands.Choice(name='Media & Info', value="movies-anime"),
        app_commands.Choice(name='Utilities', value="utilities")
    ])
    async def help_command(self, ctx: commands.Context, group: str = None):
        menu = ViewMenu(ctx, menu_type=ViewMenu.TypeEmbed)

        admindesc = self.get_section_content('admin1')
        fundesc = self.get_section_content('fun1')
        gamesdesc = self.get_section_content('roblox1')
        mediadesc = self.get_section_content('anime-movies1')
        utilsdesc = self.get_section_content('utilities1')

        if group is None:
            maindesc = self.get_section_content('main')
            mainpage = discord.Embed(title="⚡ Commands", description=maindesc, color=discord.Color.blurple())
            mainpage.set_footer(text="Arexium © ITron Technologies")
            mainpage.set_thumbnail(url="https://cdn.discordapp.com/avatars/1143816212929859584/a_6211b083d72ad4f545d6418185d7cc52.gif")
            menu.add_page(mainpage)

            menu.add_select(ViewSelect(title="Categories", options={
                discord.SelectOption(label="Admin", emoji="🔨"): [
                    Page(embed=discord.Embed(title="🔨 Admin Commands", description=admindesc, color=discord.Color.blue()))
                ],
                discord.SelectOption(label="Games", emoji="🎮"): [
                    Page(embed=discord.Embed(title="🎮 Games", description=gamesdesc, color=discord.Color.green()))
                ],
                discord.SelectOption(label="Fun & Social", emoji="🎉"): [
                    Page(embed=discord.Embed(title="🎉 Fun & Social", description=fundesc, color=discord.Color.gold())),
                ],
                discord.SelectOption(label="Media & Info", emoji="🎥"): [
                    Page(embed=discord.Embed(title="🎥 Media & Info", description=mediadesc, color=discord.Color.purple()))
                ],
                discord.SelectOption(label="Utilities", emoji="🎲"): [
                    Page(embed=discord.Embed(title="🎲 Utility Commands", description=utilsdesc, color=discord.Color.orange()))
                ]
            }))
        else:
            group = group.lower()
            if group == "admin":
                embed = discord.Embed(title="🔨 Admin Commands", description=admindesc, color=discord.Color.blue())
            elif group in ("roblox", "games", "game", "gaming", "minecraft"):
                embed = discord.Embed(title="🎮 Games", description=gamesdesc, color=discord.Color.green())
            elif group in ("fun", "social"):
                embed = discord.Embed(title="🎉 Fun & Social", description=fundesc, color=discord.Color.gold())
            elif group in ("movies-anime", "anime", "media", "info"):
                embed = discord.Embed(title="🎥 Media & Info", description=mediadesc, color=discord.Color.purple())
            elif group in ("utilities", "utils", "utility"):
                embed = discord.Embed(title="🎲 Utility Commands", description=utilsdesc, color=discord.Color.orange())
            else:
                await ctx.send("Invalid category specified. Please choose from 'admin', 'games', 'fun', 'media', or 'utilities'.")
                return
            await ctx.send(embed=embed)
            return

        back_button = ViewButton(style=discord.ButtonStyle.primary, label='', emoji='◀️', custom_id=ViewButton.ID_PREVIOUS_PAGE)
        menu.add_button(back_button)
        next_button = ViewButton(style=discord.ButtonStyle.success, label='', emoji='▶️', custom_id=ViewButton.ID_NEXT_PAGE)
        menu.add_button(next_button)
        link_button = ViewButton(style=discord.ButtonStyle.link, emoji='🌍', label='Website', url='https://google.com')
        menu.add_button(link_button)
        await menu.start()

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpMenu(bot))
