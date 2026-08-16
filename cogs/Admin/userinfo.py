import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

class UserInfo(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="userinfo", description="Show detailed information about a Discord user or member.")
    @app_commands.describe(
        member="Select a member from this server",
        user_id="Or provide a user ID to fetch globally"
    )
    async def userinfo(self, ctx: commands.Context, member: Optional[discord.Member] = None, user_id: Optional[str] = None):
        await ctx.defer()

        target_user = None
        target_member = None

        if user_id:
            if not user_id.strip().isdigit():
                await ctx.send("Invalid user ID. Please provide a valid numerical ID.", ephemeral=True)
                return
            uid = int(user_id.strip())
            try:
                target_user = await self.bot.fetch_user(uid)
                if ctx.guild:
                    target_member = ctx.guild.get_member(uid)
            except discord.NotFound:
                await ctx.send(f"User with ID `{user_id}` not found.", ephemeral=True)
                return
            except Exception as e:
                await ctx.send(f"Failed to fetch user: {e}", ephemeral=True)
                return
        elif member:
            target_member = member
            target_user = await self.bot.fetch_user(member.id)
        else:
            if isinstance(ctx.author, discord.Member):
                target_member = ctx.author
            target_user = await self.bot.fetch_user(ctx.author.id)

        profile_image = target_user.display_avatar.url
        banner_url = target_user.banner.url if target_user.banner else None

        embed = discord.Embed(
            title=f"User Info: {target_user.name}",
            color=target_member.color if target_member and target_member.color.value != 0 else discord.Color.blue()
        )
        embed.set_author(name=target_user.name, icon_url=profile_image)
        embed.set_thumbnail(url=profile_image)
        if banner_url:
            embed.set_image(url=banner_url)

        embed.add_field(name="Username", value=f"[{target_user.name}](https://discord.com/users/{target_user.id})", inline=True)
        embed.add_field(name="User ID", value=f"`{target_user.id}`", inline=True)
        embed.add_field(name="Account Created", value=f"<t:{int(target_user.created_at.timestamp())}:F> (<t:{int(target_user.created_at.timestamp())}:R>)", inline=False)

        # Server-specific information
        if target_member:
            if target_member.joined_at:
                embed.add_field(name="Joined Server", value=f"<t:{int(target_member.joined_at.timestamp())}:F> (<t:{int(target_member.joined_at.timestamp())}:R>)", inline=False)
            embed.add_field(name="Top Role", value=target_member.top_role.mention, inline=True)
            
            roles = [r.mention for r in reversed(target_member.roles[1:])]  # Exclude @everyone
            if roles:
                role_str = ', '.join(roles[:15]) + (f" (+{len(roles)-15} more)" if len(roles) > 15 else "")
                embed.add_field(name=f"Roles ({len(roles)})", value=role_str, inline=False)

            if target_member.activity:
                act = target_member.activity
                embed.add_field(name="Activity", value=f"**{act.type.name.title()}:** {act.name}", inline=False)

        # User badges
        if hasattr(target_user, 'public_flags') and target_user.public_flags:
            flags = [f.name.replace('_', ' ').title() for f in target_user.public_flags.all()]
            if flags:
                embed.add_field(name="Badges", value=', '.join(flags), inline=False)

        embed.add_field(name="Bot Account", value="Yes" if target_user.bot else "No", inline=True)

        await ctx.send(embed=embed)

    @userinfo.error
    async def userinfo_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send("This command is on cooldown. Please try again later.", ephemeral=True)
        elif isinstance(error, commands.BadArgument):
            await ctx.send("Invalid argument provided. Please mention a member or enter a valid user ID.", ephemeral=True)
        else:
            await ctx.send(f"An error occurred: {error}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(UserInfo(bot))
