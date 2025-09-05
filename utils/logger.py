import discord
import logging
import config
from typing import Optional

# configure logging 
def setup_logging():
    """set up logging configuration for the bot"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('bot.log'),
            logging.StreamHandler()
        ]
    )

def get_logger(name: str) -> logging.Logger:
    """get a logger instance for the given name"""
    return logging.getLogger(name)

async def log_attempt(bot, interaction: discord.Interaction, name_input: str, outcome: str, success: bool):
    """sends a formatted log message to the moderation channel"""
    if not config.MOD_LOG_CHANNEL_ID: 
        return
    
    try:
        log_channel = bot.get_channel(config.MOD_LOG_CHANNEL_ID)
        if not log_channel: 
            return

        color = discord.Color.green() if success else discord.Color.red()
        embed = discord.Embed(title="Verification Attempt", color=color)
        embed.add_field(name="Member", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=False)
        embed.add_field(name="Name Input", value=f"`{name_input}`", inline=False)
        embed.add_field(name="Outcome", value=outcome, inline=False)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()
        await log_channel.send(embed=embed)
    except Exception as e:
        logger = get_logger(__name__)
        logger.error(f"Failed to send log message: {e}")

async def log_general(bot, title: str, description: str, color: discord.Color = discord.Color.blue(), 
                     fields: Optional[dict] = None, thumbnail_url: Optional[str] = None):
    """send a general log message to the moderation channel"""
    if not config.MOD_LOG_CHANNEL_ID:
        return
    
    try:
        log_channel = bot.get_channel(config.MOD_LOG_CHANNEL_ID)
        if not log_channel:
            return

        embed = discord.Embed(title=title, description=description, color=color)
        
        if fields:
            for name, value in fields.items():
                embed.add_field(name=name, value=value, inline=False)
        
        if thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)
        
        embed.timestamp = discord.utils.utcnow()
        await log_channel.send(embed=embed)
    except Exception as e:
        logger = get_logger(__name__)
        logger.error(f"Failed to send general log message: {e}")