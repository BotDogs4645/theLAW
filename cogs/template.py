"""
Template cog for creating new Discord bot cogs
Copy this file and modify it for your new cog
"""
import discord
from discord.ext import commands
from utils.cog_base import BaseCog, admin_only, moderator_only
from utils import logger

class TemplateCog(BaseCog):
    """Template cog - replace with your cog's functionality"""
    
    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        # Initialize any cog-specific data here
    
    @commands.command(name="template")
    async def template_command(self, ctx: commands.Context, *, message: str = None):
        """
        Template command - replace with your command logic
        Usage: !template [message]
        """
        if not message:
            await ctx.send("Please provide a message!")
            return
        
        await ctx.send(f"Template command received: {message}")
        await self.log_action("Template command used", ctx.author, {"Message": message})
    
    @commands.command(name="admin_template")
    @admin_only()
    async def admin_template_command(self, ctx: commands.Context):
        """Admin-only template command"""
        await ctx.send("This is an admin-only command!")
        await self.log_action("Admin template command used", ctx.author)
    
    @commands.command(name="mod_template")
    @moderator_only()
    async def mod_template_command(self, ctx: commands.Context):
        """Moderator-only template command"""
        await ctx.send("This is a moderator-only command!")
        await self.log_action("Mod template command used", ctx.author)
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Event listener for when a member joins"""
        self.logger.info(f"Member joined: {member.name} ({member.id})")
        # Add your logic here
    
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Event listener for when a member leaves"""
        self.logger.info(f"Member left: {member.name} ({member.id})")
        # Add your logic here

async def setup(bot: commands.Bot):
    """Setup function for the cog"""
    await bot.add_cog(TemplateCog(bot))
