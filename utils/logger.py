import discord
import config

async def log_attempt(bot, interaction: discord.Interaction, name_input: str, outcome: str, success: bool):
    """sends a formatted log message to the moderation channel"""
    if not config.MOD_LOG_CHANNEL_ID: return
    try:
        log_channel = bot.get_channel(config.MOD_LOG_CHANNEL_ID)
        if not log_channel: return

        color = discord.Color.green() if success else discord.Color.red()
        embed = discord.Embed(title="Verification Attempt", color=color)
        embed.add_field(name="Member", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=False)
        embed.add_field(name="Name Input", value=f"`{name_input}`", inline=False)
        embed.add_field(name="Outcome", value=outcome, inline=False)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.timestamp = discord.utils.utcnow()
        await log_channel.send(embed=embed)
    except Exception as e:
        print(f"Failed to send log message: {e}")