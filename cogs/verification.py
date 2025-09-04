import discord
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
import re
from utils.logger import log_attempt
from utils import database
import config

class NameModal(Modal, title="Enter Your Full Name"):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    full_name = TextInput(label="Full Name", placeholder="First Last", min_length=3)

    async def on_submit(self, interaction: discord.Interaction):
        name_input = self.full_name.value.strip()
        member = interaction.user
        lower_name = name_input.lower()

        if database.is_user_verified(member.id):
            await interaction.response.send_message("❌ You are already verified.", ephemeral=True)
            return await log_attempt(self.bot, interaction, name_input, "Attempt failed: User is already verified.", success=False)

        if database.is_name_taken(lower_name):
            await interaction.response.send_message("❌ This name has already been claimed. Please contact an admin.", ephemeral=True)
            return await log_attempt(self.bot, interaction, name_input, "Attempt failed: Name is already taken.", success=False)

        if not re.match(r"^\S+\s.+", name_input):
            return await interaction.response.send_message("❌ Please enter your full name in the format `First Last`.", ephemeral=True)

        if lower_name in self.bot.students:
            student_data = self.bot.students[lower_name]
            nickname = student_data['original_name']
            roles_to_add = []
            roles_added_names = []

            verified_role = interaction.guild.get_role(config.VERIFIED_ROLE_ID)
            if verified_role:
                roles_to_add.append(verified_role)
                roles_added_names.append(f"**{verified_role.name}**")
            else:
                print(f"WARNING: Verified role ID {config.VERIFIED_ROLE_ID} could not be found in the server.")

            # add team-specific roles
            for team in student_data['teams']:
                role_id = self.bot.role_map.get(team)
                if role_id:
                    role = interaction.guild.get_role(role_id)
                    if role and role not in roles_to_add:
                        roles_to_add.append(role)
                        roles_added_names.append(role.name)

            if roles_to_add:
                await member.add_roles(*roles_to_add, reason="Verified via bot")
            
            nickname_status = ""
            try:
                await member.edit(nick=nickname)
                nickname_status = f" Your nickname has been set to **{nickname}**."
            except discord.Forbidden:
                nickname_status = " Could not set your nickname due to permissions."

            assigned_role_ids = [role.id for role in roles_to_add]
            database.add_verified_user(member.id, lower_name, assigned_role_ids)
            
            outcome = f"Roles assigned: {', '.join(roles_added_names)}."
            await interaction.response.send_message(f"✅ Success! {outcome}{nickname_status}", ephemeral=True)
            await log_attempt(self.bot, interaction, name_input, f"{outcome}{nickname_status}", success=True)
        else:
            outcome = "Name not found in the roster."
            await interaction.response.send_message(f"❌ {outcome} Please check spelling or contact an admin.", ephemeral=True)
            await log_attempt(self.bot, interaction, name_input, outcome, success=False)

class VerifyView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Verify Me", style=discord.ButtonStyle.primary, custom_id="persistent_verify_button")
    async def verify(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(NameModal(self.bot))

class Verification(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(VerifyView(self.bot))

async def setup(bot):
    await bot.add_cog(Verification(bot))
