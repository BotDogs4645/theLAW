"""
Base classes and utilities for Discord bot cogs
"""
import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional, Dict, Any
from utils import logger

class BaseCog(commands.Cog):
    """base cog class with common functionality for all cogs"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logger.get_logger(self.__class__.__name__)
    
    def cog_load(self):
        """called when the cog is loaded"""
        self.logger.info(f"Loaded cog: {self.__class__.__name__}")
    
    def cog_unload(self):
        """called when the cog is unloaded"""
        self.logger.info(f"Unloaded cog: {self.__class__.__name__}")
    
    async def cog_command_error(self, ctx: commands.Context, error: Exception):
        """handle errors specific to this cog"""
        self.logger.error(f"Error in {self.__class__.__name__}: {error}")
        
        if isinstance(error, commands.CommandNotFound):
            return  # don't log command not found errors
        
        # send user-friendly error message
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ Missing required argument. Please check the command usage.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("❌ Invalid argument provided. Please check your input.")
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You don't have permission to use this command.")
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send("❌ I don't have the required permissions to execute this command.")
        else:
            await ctx.send("❌ An unexpected error occurred. Please try again later.")
    
    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """handle errors specific to slash commands in this cog"""
        self.logger.error(f"Slash command error in {self.__class__.__name__}: {error}")
        
        # send user-friendly error message
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        elif isinstance(error, app_commands.BotMissingPermissions):
            await interaction.response.send_message("❌ I don't have the required permissions to execute this command.", ephemeral=True)
        else:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ An unexpected error occurred. Please try again later.", ephemeral=True)
            else:
                await interaction.followup.send("❌ An unexpected error occurred. Please try again later.", ephemeral=True)
    
    async def log_action(self, action: str, user: discord.Member, details: Optional[Dict[str, Any]] = None):
        """log an action to the moderation channel"""
        fields = {
            "User": f"{user.mention} (`{user.id}`)",
            "Action": action
        }
        if details:
            fields.update(details)
        
        await logger.log_general(
            self.bot,
            title=f"{self.__class__.__name__} Action",
            description=f"Action performed: {action}",
            fields=fields,
            thumbnail_url=user.display_avatar.url
        )
    
    def get_guild(self) -> Optional[discord.Guild]:
        """get the main guild"""
        return self.bot.get_guild(self.bot.guild_id) if hasattr(self.bot, 'guild_id') else None
    
    def is_admin(self, member: discord.Member) -> bool:
        """check if a member is an admin (has administrator permission)"""
        return member.guild_permissions.administrator
    
    def is_moderator(self, member: discord.Member) -> bool:
        """check if a member is a moderator (has manage_messages permission)"""
        return member.guild_permissions.manage_messages or self.is_admin(member)

class AdminOnly(commands.CheckFailure):
    """custom exception for admin-only commands"""
    pass

class ModeratorOnly(commands.CheckFailure):
    """custom exception for moderator-only commands"""
    pass

def admin_only():
    """check if the user is an admin"""
    async def predicate(ctx: commands.Context):
        if not ctx.guild:
            raise AdminOnly("This command can only be used in a server.")
        if not ctx.author.guild_permissions.administrator:
            raise AdminOnly("You must be an administrator to use this command.")
        return True
    return commands.check(predicate)

def moderator_only():
    """check if the user is a moderator or admin"""
    async def predicate(ctx: commands.Context):
        if not ctx.guild:
            raise ModeratorOnly("This command can only be used in a server.")
        if not (ctx.author.guild_permissions.manage_messages or ctx.author.guild_permissions.administrator):
            raise ModeratorOnly("You must be a moderator or administrator to use this command.")
        return True
    return commands.check(predicate)

def in_verification_channel():
    """check if the command is being used in the verification channel"""
    async def predicate(ctx: commands.Context):
        if not ctx.guild:
            return False
        # this would need to be updated to use the actual verification channel ID
        # for now, we'll just check if it's a text channel
        return isinstance(ctx.channel, discord.TextChannel)
    return commands.check(predicate)

# Slash command permission decorators
def slash_admin_only():
    """check if the user is an admin for slash commands"""
    async def predicate(interaction: discord.Interaction):
        if not interaction.guild:
            raise app_commands.MissingPermissions(["administrator"])
        if not interaction.user.guild_permissions.administrator:
            raise app_commands.MissingPermissions(["administrator"])
        return True
    return app_commands.check(predicate)

def slash_moderator_only():
    """check if the user is a moderator or admin for slash commands"""
    async def predicate(interaction: discord.Interaction):
        if not interaction.guild:
            raise app_commands.MissingPermissions(["manage_messages"])
        if not (interaction.user.guild_permissions.manage_messages or interaction.user.guild_permissions.administrator):
            raise app_commands.MissingPermissions(["manage_messages"])
        return True
    return app_commands.check(predicate)
