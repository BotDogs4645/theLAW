# The LAW

A Discord bot for managing student verification and role assignment for Lane Tech Teams 4645 & 4863.


## Setup

1. **dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **env**:
   Create a `.env` file with the following variables:
   ```
   DISCORD_TOKEN=your_bot_token
   GUILD_ID=your_server_id
   VERIFIED_ROLE_ID=role_id_for_verified_users
   VERIFICATION_CHANNEL_ID=channel_id_for_verification
   MOD_LOG_CHANNEL_ID=channel_id_for_moderation_logs
   EMBED_TITLE=Verification
   EMBED_DESCRIPTION=Click the button below to get your roles.
   EMBED_COLOR=0x5865F2
   ```

3. **data files**:
   - `students.csv`: Student roster with columns: `first_name`, `last_name`, `teams`
   - `roles.json`: JSON mapping of team names to Discord role IDs

4. **run**:
   ```bash
   python main.py
   ```

## creating new cogs

Use the template in `cogs/template.py` as a starting point:

1. Copy `cogs/template.py` to `cogs/your_cog_name.py`
2. Rename the class from `TemplateCog` to `YourCogName`
3. Implement your functionality
4. The cog will be automatically loaded on bot startup
