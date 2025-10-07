import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import re
from utils.logger import log_attempt
from utils import database
from utils.cog_base import BaseCog
import config
from typing import Optional


class VerificationModal(Modal, title="Verify Your Identity"):    
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    full_name = TextInput(label="Full Name", placeholder="First Last", min_length=3)
    email = TextInput(label="Email Address", placeholder="your.email@cps.edu", min_length=5)

    @staticmethod
    def create_error_embed(title: str, description: str) -> discord.Embed:
        embed = discord.Embed(
            title=f"❌ {title}",
            description=description,
            color=0xff0000
        )
        embed.add_field(
            name="Please verify:",
            value="• Your first name and last name are in the expected email format\n• You provided the correct @cps.edu email address\n• You are enrolled in the **latest** Google Classroom",
            inline=False
        )
        embed.add_field(
            name="Need help?",
            value="If you continue to have issues, please contact an admin for assistance.",
            inline=False
        )
        return embed

    def validate_inputs(self, name_input: str, email_input: str) -> tuple[bool, str]:
        # validate email format
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email_input):
            return False, "Please enter a valid email address."
        
        # validte name format
        if not re.match(r"^\S+\s.+", name_input):
            return False, "Please enter your full name in the format `First Last`."
        
        return True, ""

    async def handle_verification_failure(self, interaction: discord.Interaction, 
                                        name_input: str, email_input: str, 
                                        reason: str) -> None:
        """Handle verification failure with consistent error messaging"""
        embed = self.create_error_embed("Verification Failed", "We couldn't find you on the roster.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await log_attempt(self.bot, interaction, f"{name_input} ({email_input})", f"Attempt failed: {reason}", success=False)

    async def assign_roles_and_nickname(self, interaction: discord.Interaction, 
                                      member: discord.Member, student_data: dict) -> tuple[list, str]:
        """Assign roles and set nickname for verified user"""
        roles_to_add = []
        roles_added_names = []
        
        # add verified role
        verified_role = interaction.guild.get_role(config.VERIFIED_ROLE_ID)
        if verified_role:
            roles_to_add.append(verified_role)
        else:
            self.bot.logger.warning(f"Verified role ID {config.VERIFIED_ROLE_ID} not found in server.")
        
        # add team-specific roles
        for team in student_data['teams']:
            role_id = self.bot.role_map.get(team)
            if role_id:
                role = interaction.guild.get_role(role_id)
                if role and role not in roles_to_add:
                    roles_to_add.append(role)
                    roles_added_names.append(role.name)
        
        # apply roles
        if roles_to_add:
            await member.add_roles(*roles_to_add, reason="Verified via bot")
        
        # set nickname
        nickname = student_data['original_name']
        nickname_status = ""
        try:
            await member.edit(nick=nickname)
            nickname_status = f" Your nickname has been set to **{nickname}**."
        except discord.Forbidden:
            nickname_status = " Could not set your nickname due to permissions."
        
        return roles_added_names, nickname_status

    async def on_submit(self, interaction: discord.Interaction):
        """Handle verification form submission"""
        name_input = self.full_name.value.strip()
        email_input = self.email.value.strip().lower()
        member = interaction.user
        lower_name = name_input.lower()

        # validate inputs
        is_valid, error_message = self.validate_inputs(name_input, email_input)
        if not is_valid:
            await interaction.response.send_message(f"❌ {error_message}", ephemeral=True)
            return await log_attempt(self.bot, interaction, f"{name_input} ({email_input})", f"Attempt failed: {error_message}", success=False)

        # check if user is already verified
        if database.is_user_verified(member.id):
            return await self.handle_verification_failure(interaction, name_input, email_input, "User is already verified.")

        # check if email is already verified by another user
        if database.is_email_verified(email_input):
            return await self.handle_verification_failure(interaction, name_input, email_input, "Email already verified by another user.")

        # look up student by email
        student_data = self._find_student_by_email(email_input)
        if not student_data:
            return await self.handle_verification_failure(interaction, name_input, email_input, "Email not found in the roster.")

        # verify name matches
        if student_data['original_name'].lower() != lower_name:
            return await self.handle_verification_failure(interaction, name_input, email_input, f"Name mismatch. Expected: {student_data['original_name']}")

        # assign roles and set nickname
        roles_added_names, nickname_status = await self.assign_roles_and_nickname(interaction, member, student_data)
        
        # save to database
        assigned_role_ids = [role.id for role in interaction.guild.get_role(config.VERIFIED_ROLE_ID) and [interaction.guild.get_role(config.VERIFIED_ROLE_ID)] or []]
        for team in student_data['teams']:
            role_id = self.bot.role_map.get(team)
            if role_id:
                role = interaction.guild.get_role(role_id)
                if role:
                    assigned_role_ids.append(role.id)
        
        database.add_verified_user(member.id, lower_name, email_input, assigned_role_ids)
        
        # send success message
        await self._send_success_message(interaction, roles_added_names, nickname_status)
        
        # log successful verification
        outcome = f"Roles assigned: {', '.join(roles_added_names)}." if roles_added_names else "No additional roles assigned."
        await log_attempt(self.bot, interaction, f"{name_input} ({email_input})", f"{outcome}{nickname_status}", success=True)

    def _find_student_by_email(self, email_input: str) -> Optional[dict]:
        """Find student data by email address"""
        for student in self.bot.students.values():
            if student.get('email', '').lower() == email_input:
                return student
        return None

    async def _send_success_message(self, interaction: discord.Interaction, roles_added_names: list, nickname_status: str) -> None:
        """Send success message to user"""
        if roles_added_names:
            roles_list = ', '.join(roles_added_names)
            role_word = "role" if len(roles_added_names) == 1 else "roles"
            message = f"✅ Success! We're glad to have you here. We've given you the following {role_word}: {roles_list}. If you think something is missing, please message an admin."
        else:
            message = "✅ Success! We're glad to have you here. If you think something is missing, please message an admin."
        
        await interaction.response.send_message(f"{message}{nickname_status}", ephemeral=True)

class VerifyView(View):
    """Persistent view for the verification button"""
    
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Verify Me", style=discord.ButtonStyle.primary, custom_id="persistent_verify_button")
    async def verify(self, interaction: discord.Interaction, button: Button):
        """Handle verification button click"""
        await interaction.response.send_modal(VerificationModal(self.bot))


class Verification(BaseCog):
    """Cog for handling user verification"""
    
    def __init__(self, bot):
        super().__init__(bot)
        self.bot.add_view(VerifyView(self.bot))


async def setup(bot):
    """Setup function for the verification cog"""
    await bot.add_cog(Verification(bot))
