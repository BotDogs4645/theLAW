import os
from dotenv import load_dotenv

load_dotenv()

# core bot secrets
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

# role and channel ids
VERIFIED_ROLE_ID = int(os.getenv("VERIFIED_ROLE_ID"))
VERIFICATION_CHANNEL_ID = int(os.getenv("VERIFICATION_CHANNEL_ID"))
MOD_LOG_CHANNEL_ID = int(os.getenv("MOD_LOG_CHANNEL_ID"))

# embeds
EMBED_TITLE = os.getenv("EMBED_TITLE", "Verification")
EMBED_DESCRIPTION = os.getenv("EMBED_DESCRIPTION", "Click the button below to get your roles.")
try:
    EMBED_COLOR = int(os.getenv("EMBED_COLOR", "0x5865F2"), 16)
except (ValueError, TypeError):
    EMBED_COLOR = 0x5865F2
