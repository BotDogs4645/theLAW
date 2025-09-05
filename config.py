import os
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

def get_required_env(key: str) -> str:
    """Get a required environment variable, raising an error if not found"""
    value = os.getenv(key)
    if not value:
        raise ValueError(f"Required environment variable {key} is not set")
    return value

def get_optional_env(key: str, default: str = None) -> Optional[str]:
    """Get an optional environment variable with a default value"""
    return os.getenv(key, default)

def get_int_env(key: str, default: Optional[int] = None) -> Optional[int]:
    """Get an environment variable as an integer"""
    value = os.getenv(key)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"Environment variable {key} must be a valid integer, got: {value}")

def get_hex_color_env(key: str, default: int = 0x5865F2) -> int:
    """Get an environment variable as a hex color"""
    value = os.getenv(key)
    if not value:
        return default
    try:
        return int(value, 16)
    except ValueError:
        return default

# Core bot configuration
TOKEN = get_required_env("DISCORD_TOKEN")
GUILD_ID = get_int_env("GUILD_ID")

# Role and channel IDs
VERIFIED_ROLE_ID = get_int_env("VERIFIED_ROLE_ID")
VERIFICATION_CHANNEL_ID = get_int_env("VERIFICATION_CHANNEL_ID")
MOD_LOG_CHANNEL_ID = get_int_env("MOD_LOG_CHANNEL_ID")

# Embed configuration
EMBED_TITLE = get_optional_env("EMBED_TITLE", "Verification")
EMBED_DESCRIPTION = get_optional_env("EMBED_DESCRIPTION", "Click the button below to get your roles.")
EMBED_COLOR = get_hex_color_env("EMBED_COLOR", 0x5865F2)

# Rules configuration
RULES_TITLE = get_optional_env("RULES_TITLE", "Server Rules")
RULES_DESCRIPTION = get_optional_env("RULES_DESCRIPTION", 
    "1. Treat everyone equally. Discrimination based on gender, race, religion etc is prohibited.\n\n"
    "2. Use common sense.\n\n"
    "3. Follow [Discord's Terms of Service](https://discord.com/terms).\n\n---\n\n"
    "This Discord server is an extension of both Lane Tech and Teams 4645 & 4863. "
    "Your actions here may have consequences within the team and with Lane Tech administration."
)
RULES_COLOR = get_hex_color_env("RULES_COLOR", 0xFF8C00)  # Orange color

# Validate required configuration
if not TOKEN:
    raise ValueError("DISCORD_TOKEN is required")
if not GUILD_ID:
    raise ValueError("GUILD_ID is required")
if not VERIFIED_ROLE_ID:
    raise ValueError("VERIFIED_ROLE_ID is required")
