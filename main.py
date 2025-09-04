import discord
from discord.ext import commands
import os
import config
from utils import data_loader

class VerificationBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.students = data_loader.load_students()
        self.role_map = data_loader.load_roles()
        self.verified_role = None

# define intents
intents = discord.Intents.default()
intents.members = True

bot = VerificationBot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    guild = bot.get_guild(config.GUILD_ID)
    if guild:
        bot.verified_role = guild.get_role(config.VERIFIED_ROLE_ID)

    if config.VERIFICATION_CHANNEL_ID:
        await setup_verification_channel()
    
    print("------")
    print(f"Loaded {len(bot.students)} students and {len(bot.role_map)} role mappings.")

async def setup_verification_channel():
    """ensures the rules and verification embeds are in the verification channel"""
    try:
        channel = bot.get_channel(config.VERIFICATION_CHANNEL_ID)
        if not channel: return print(f"Error: Channel {config.VERIFICATION_CHANNEL_ID} not found.")

        # dynamically import VerifyView only when needed to avoid circular import issues at startup
        from cogs.verification import VerifyView
        
        rules_found, verify_found = False, False
        async for message in channel.history(limit=10):
            if message.author == bot.user:
                if message.embeds and message.embeds[0].title == "Server Rules":
                    rules_found = True
                if any(isinstance(c, discord.ui.Button) and c.custom_id == "persistent_verify_button" for row in message.components for c in row.children):
                    verify_found = True

        if not rules_found:
            rules_embed = discord.Embed(
                title="Server Rules",
                description=(
                    "1. Treat everyone equally. Discrimination based on gender, race, religion etc is prohibited.\n\n"
                    "2. Use common sense.\n\n"
                    "3. Follow [Discord's Terms of Service](https://discord.com/terms).\n\n---\n\n"
                    "This Discord server is an extension of both Lane Tech and Teams 4645 & 4863. "
                    "Your actions here may have consequences within the team and with Lane Tech administration."
                ),
                color=discord.Color.orange()
            )
            await channel.send(embed=rules_embed)

        if not verify_found:
            verify_embed = discord.Embed(title=config.EMBED_TITLE, description=config.EMBED_DESCRIPTION, color=config.EMBED_COLOR)
            await channel.send(embed=verify_embed, view=VerifyView(bot))
    except Exception as e:
        print(f"Failed during on_ready message setup: {e}")

async def main():
    # load all cogs from the 'cogs' directory
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            await bot.load_extension(f'cogs.{filename[:-3]}')
    
    await bot.start(config.TOKEN)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
