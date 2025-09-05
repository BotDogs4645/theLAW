"""
Member management cog for handling Discord member events
"""
import discord
from discord.ext import commands
from utils.cog_base import BaseCog
from utils import database, logger

class MemberManagementCog(BaseCog):
    """Cog for handling member join/leave events and related management"""
    
    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
    
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Event listener for when a member leaves the server"""
        self.logger.info(f"Member left: {member.name} ({member.id})")
        
        # check if the user was verified and delete their record
        if database.is_user_verified(member.id):
            success = database.delete_verified_user(member.id)
            if success:
                self.logger.info(f"Successfully deleted verified user record for {member.name} ({member.id})")
            else:
                self.logger.warning(f"Failed to delete verified user record for {member.name} ({member.id})")
        else:
            self.logger.info(f"Member {member.name} ({member.id}) was not verified, no database cleanup needed")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Event listener for when a member joins the server"""
        self.logger.info(f"Member joined: {member.name} ({member.id})")

async def setup(bot: commands.Bot):
    """Setup function for the member management cog"""
    await bot.add_cog(MemberManagementCog(bot))
