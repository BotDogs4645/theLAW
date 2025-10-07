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
   - `students.csv`: Student roster with columns: `first_name`, `last_name`, `email`, `teams`
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

## Importing/Updating the Student Roster

Use the CSV importer to upsert students into the SQLite database.

1. Prepare a CSV file with headers:
   - `first_name`
   - `last_name`
   - `email`
   - `teams` (optional, `:` separated, e.g. `V25:JV26`)

2. Run the importer from the project root:

```bash
python utils/import_students.py /absolute/path/to/students.csv
```

The importer treats `email` as the unique key and will update existing rows or insert new rows.

### Syncing Roles After Roster Changes

After importing, reconcile Discord roles for verified users based on the latest roster and `roles.json` with the admin-only slash command inside your server:

- `/sync_roles` — Updates roles for all verified users.
  - Ensures the Verified role is present
  - Adds team roles found for the user's email
  - Removes roles the bot controls that no longer apply
