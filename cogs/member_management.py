"""
Member management cog for handling Discord member events
"""
import discord
from discord.ext import commands
from utils.cog_base import BaseCog, slash_admin_only
from discord import app_commands
from utils import logger, data_loader
from utils.db import (
    is_user_verified, delete_verified_user, get_all_verified_users, update_verified_user_roles
)

class MemberManagementCog(BaseCog):
    """Cog for handling member join/leave events and related management"""
    
    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
    
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Event listener for when a member leaves the server"""
        self.logger.info(f"Member left: {member.name} ({member.id})")
        
        # check if the user was verified and delete their record
        if is_user_verified(member.id):
            success = delete_verified_user(member.id)
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

    @app_commands.command(name="sync_roles", description="Sync roles for all verified users from the roster")
    @slash_admin_only()
    async def sync_roles(self, interaction: discord.Interaction):
        """Admin-only command to reconcile roles based on current roster and role map"""
        await interaction.response.defer(ephemeral=True, thinking=True)

        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("Guild not found.", ephemeral=True)
            return

        # ensure bot has current data
        self.bot.students = data_loader.load_students()
        students_by_email = {s.get('email').lower(): s for s in self.bot.students.values() if s.get('email')}
        role_map = getattr(self.bot, 'role_map', {}) or {}

        verified_users = get_all_verified_users()
        updated_count = 0
        checked_count = 0
        missing_members = 0

        for vu in verified_users:
            discord_id = vu['discord_id']
            email = (vu.get('email') or '').lower()
            member = guild.get_member(discord_id)
            if member is None:
                missing_members += 1
                continue

            desired_roles = []
            # always include the verified role if configured on bot
            if getattr(self.bot, 'verified_role', None):
                desired_roles.append(self.bot.verified_role)

            student = students_by_email.get(email)
            if student:
                for team in student.get('teams', []):
                    role_id = role_map.get(team)
                    if role_id:
                        role = guild.get_role(role_id)
                        if role and role not in desired_roles:
                            desired_roles.append(role)

            # compute current vs desired
            current_roles = list(member.roles)
            roles_to_add = [r for r in desired_roles if r not in current_roles]

            # only remove roles that are in our control (verified or mapped roles)
            controlled_role_ids = {getattr(self.bot.verified_role, 'id', 0)} | {rid for rid in role_map.values() if isinstance(rid, int)}
            roles_to_remove = [r for r in current_roles if r.id in controlled_role_ids and r not in desired_roles]

            # apply changes if any
            if roles_to_add or roles_to_remove:
                try:
                    if roles_to_add:
                        await member.add_roles(*roles_to_add, reason="Roster sync")
                    if roles_to_remove:
                        await member.remove_roles(*roles_to_remove, reason="Roster sync")
                    updated_count += 1
                    # update stored roles snapshot
                    new_role_ids = [r.id for r in desired_roles]
                    update_verified_user_roles(discord_id, new_role_ids, checked_only=False)
                except discord.Forbidden:
                    self.logger.warning(f"Insufficient permissions to modify roles for {member} ({member.id})")
                except Exception as e:
                    self.logger.error(f"Error syncing roles for {member} ({member.id}): {e}")
            else:
                # still record check timestamp
                snapshot_ids = [r.id for r in desired_roles]
                update_verified_user_roles(discord_id, snapshot_ids, checked_only=True)
                checked_count += 1

        await interaction.followup.send(
            f"Sync complete. Updated: {updated_count}, Up-to-date: {checked_count}, Missing members: {missing_members}",
            ephemeral=True,
        )

async def setup(bot: commands.Bot):
    """Setup function for the member management cog"""
    await bot.add_cog(MemberManagementCog(bot))
