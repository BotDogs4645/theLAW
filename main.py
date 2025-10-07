import discord
from discord.ext import commands
import os
import asyncio
import config
from utils import data_loader, database, logger


class VerificationBot(commands.Bot):
    """Main bot class"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logger.get_logger(__name__)
        self.students = {}
        self.role_map = {}
        self.verified_role = None

    async def setup_hook(self):
        """Called when the bot is starting up"""
        await self._load_data()

        await self.load_cogs()
        
        # sync slash commands to the specific guild
        try:
            guild = discord.Object(id=config.GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            self.logger.info(f"Synced {len(synced)} slash commands to guild {config.GUILD_ID}")
        except Exception as e:
            self.logger.error(f"Failed to sync slash commands: {e}")

    async def _load_data(self):
        """Load student data and role mappings"""
        try:
            self.students = data_loader.load_students()
            if not self.students:
                self.logger.warning("No students found in database, trying CSV fallback...")
                self.students = data_loader.load_students_from_csv_fallback()
            
            self.role_map = data_loader.load_roles()
            self.logger.info(f"Loaded {len(self.students)} students and {len(self.role_map)} role mappings.")
        except Exception as e:
            self.logger.error(f"Failed to load data: {e}")
            raise

    async def _setup_verification_channel(self):
        """Setup the verification channel with rules and verification embeds"""
        if not config.VERIFICATION_CHANNEL_ID:
            self.logger.warning("No verification channel configured.")
            return

        try:
            channel = self.get_channel(config.VERIFICATION_CHANNEL_ID)
            if not channel:
                self.logger.error(f"Verification channel {config.VERIFICATION_CHANNEL_ID} not found.")
                return

            # check what messages already exist
            rules_found = False
            verify_found = False
            
            async for message in channel.history(limit=20):
                if message.author == self.user:
                    # detect rules embed by title
                    if message.embeds:
                        if any(embed.title == config.RULES_TITLE for embed in message.embeds):
                            rules_found = True
                        # detect verification embed by title as primary signal
                        if any(embed.title == config.EMBED_TITLE for embed in message.embeds):
                            verify_found = True
                    # fallback: detect verification button by custom_id without relying on class types
                    if not verify_found and message.components:
                        try:
                            if any(getattr(component, 'custom_id', None) == "persistent_verify_button"
                                   for row in message.components
                                   for component in getattr(row, 'children', [])):
                                verify_found = True
                        except Exception:
                            pass

            # post rules embed if not found
            if not rules_found:
                await self._post_rules_embed(channel)

            # post verification embed if not found
            if not verify_found:
                await self._post_verification_embed(channel)

        except Exception as e:
            self.logger.error(f"Failed to setup verification channel: {e}")

    async def _post_rules_embed(self, channel):
        """Post the server rules embed"""
        rules_embed = discord.Embed(
            title=config.RULES_TITLE,
            description=config.RULES_DESCRIPTION,
            color=config.RULES_COLOR
        )
        await channel.send(embed=rules_embed)
        self.logger.info("Rules embed posted to channel.")

    async def _post_verification_embed(self, channel):
        """Post the verification embed with button"""
        from cogs.verification import VerifyView
        verify_embed = discord.Embed(
            title=config.EMBED_TITLE, 
            description=config.EMBED_DESCRIPTION, 
            color=config.EMBED_COLOR
        )
        await channel.send(embed=verify_embed, view=VerifyView(self))
        self.logger.info("Verification embed posted to channel.")
    
    async def load_cogs(self):
        """Load all cogs from the cogs directory"""
        cog_count = 0
        cogs_dir = './cogs'
        
        if not os.path.exists(cogs_dir):
            self.logger.warning("Cogs directory not found.")
            return
        
        for filename in os.listdir(cogs_dir):
            if filename.endswith('.py') and not filename.startswith('__'):
                try:
                    cog_name = filename[:-3]
                    
                    # skip AI mention cog if disabled
                    if cog_name == 'ai_mention' and not config.AI_ENABLED:
                        self.logger.info(f"Skipped cog: {cog_name} (AI_ENABLED=False)")
                        continue
                    
                    await self.load_extension(f'cogs.{cog_name}')
                    cog_count += 1
                    self.logger.info(f"Loaded cog: {cog_name}")
                except Exception as e:
                    self.logger.error(f"Failed to load cog {filename}: {e}")
        
        self.logger.info(f"Successfully loaded {cog_count} cogs")


# define intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

# create bot instance
bot = VerificationBot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    """Event handler for when the bot is ready"""
    bot.logger.info(f"Logged in as {bot.user}")
    
    # validate guild and verified role
    guild = bot.get_guild(config.GUILD_ID)
    if guild:
        role = guild.get_role(config.VERIFIED_ROLE_ID)
        if role:
            bot.verified_role = role
            bot.logger.info(f"Successfully found Verified Role: '{role.name}' ({role.id})")
        else:
            bot.logger.error(f"VERIFIED_ROLE_ID '{config.VERIFIED_ROLE_ID}' not found in the server. Please check your .env file.")
    else:
        bot.logger.error(f"GUILD_ID '{config.GUILD_ID}' not found. The bot cannot see the server.")
    
    # setup verification channel after bot is ready
    await bot._setup_verification_channel()
    

async def main():
    """Main function to start the bot"""
    try:
        # setup logging
        logger.setup_logging()
        
        # setup database
        database.setup_database()
        
        # start the bot
        async with bot:
            # cog loading is now handled in setup_hook
            await bot.start(config.TOKEN)
    except Exception as e:
        bot.logger.error(f"Failed to start bot: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
