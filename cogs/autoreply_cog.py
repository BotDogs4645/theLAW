"""
Auto-reply cog - responds to messages containing configured trigger phrases
"""
import discord
from discord.ext import commands
from discord import app_commands
from utils.cog_base import BaseCog, slash_admin_only
from utils import logger
import yaml
import os
from typing import Dict, Optional

class AutoReplyCog(BaseCog):
    """Cog that responds to messages containing configured trigger phrases"""
    
    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self.responses: Dict[str, str] = {}
        self.config_file = "auto_replies.yml"
        self.load_responses()
        self.logger.info("AutoReplyCog initialized")
    
    def load_responses(self) -> None:
        """Load auto-reply responses from YAML file"""
        try:
            if not os.path.exists(self.config_file):
                self.logger.warning(f"Config file {self.config_file} not found. Creating default.")
                self._create_default_config()
                return
            
            with open(self.config_file, 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file)
                
            if 'responses' in config and isinstance(config['responses'], dict):
                self.responses = config['responses']
                self.logger.info(f"Loaded {len(self.responses)} auto-reply responses")
            else:
                self.logger.error("Invalid YAML structure. Expected 'responses' dictionary.")
                self.responses = {}
                
        except yaml.YAMLError as e:
            self.logger.error(f"Error parsing YAML file: {e}")
            self.responses = {}
        except Exception as e:
            self.logger.error(f"Error loading responses: {e}")
            self.responses = {}
    
    def _create_default_config(self) -> None:
        """Create a default configuration file"""
        default_config = {
            'responses': {
                'mistake': 'I made a mistake once... I advocated for the team and asked Mr. Berg not cancel practice.',
                'lerg': 'not real person actually',
            }
        }
        
        try:
            with open(self.config_file, 'w', encoding='utf-8') as file:
                yaml.dump(default_config, file, default_flow_style=False, allow_unicode=True)
            self.responses = default_config['responses']
            self.logger.info(f"Created default config file: {self.config_file}")
        except Exception as e:
            self.logger.error(f"Failed to create default config: {e}")
    
    def find_trigger(self, message_content: str) -> Optional[str]:
        """Find the first matching trigger in the message content"""
        content_lower = message_content.lower()
        for trigger in self.responses.keys():
            if trigger.lower() in content_lower:
                return trigger
        return None

    def get_hint_for_message(self, message_content: str) -> Optional[str]:
        """Return the auto-reply text for the first matching trigger, if any.

        This is used by the AI cog to seed a SYSTEM hint when the bot is mentioned.
        """
        trigger = self.find_trigger(message_content)
        if trigger:
            return self.responses.get(trigger)
        return None
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for messages and respond if they contain configured triggers"""
        # ignore messages from bots to prevent infinite loops
        if message.author.bot:
            return
        # if the bot is mentioned, let the AI cog handle it to prevent double replies
        if self.bot.user in getattr(message, "mentions", []):
            return
        
        # find matching trigger
        trigger = self.find_trigger(message.content)
        if trigger:
            response = self.responses[trigger]
            await message.channel.send(response)
    
    @app_commands.command(name="reload_autoreplies", description="Reload auto-reply responses from the YAML configuration file")
    @slash_admin_only()
    async def reload_autoreplies(self, interaction: discord.Interaction):
        """Reload auto-reply responses from the YAML configuration file"""
        old_count = len(self.responses)
        self.load_responses()
        new_count = len(self.responses)
        
        embed = discord.Embed(
            title="Auto-Reply Reload",
            description=f"Successfully reloaded auto-reply responses!",
            color=discord.Color.green()
        )
        embed.add_field(name="Previous Count", value=str(old_count), inline=True)
        embed.add_field(name="New Count", value=str(new_count), inline=True)
        embed.add_field(name="Triggers", value=", ".join(list(self.responses.keys())[:10]) + ("..." if len(self.responses) > 10 else ""), inline=False)
        
        await interaction.response.send_message(embed=embed)
        await self.log_action("Auto-replies reloaded", interaction.user, {"New Count": new_count})
    
async def setup(bot: commands.Bot):
    """Setup function for the cog"""
    cog = AutoReplyCog(bot)
    await bot.add_cog(cog)
    
    try:
        bot.tree.add_command(cog.reload_autoreplies)
    except Exception as e:
        bot.logger.error(f"Failed to register reload_autoreplies command: {e}")
