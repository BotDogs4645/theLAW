import os
from dotenv import load_dotenv
from typing import Optional
# Prompt loading is now handled directly in the AI cog

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

def get_bool_env(key: str, default: bool = False) -> bool:
    """Get an environment variable as a boolean"""
    value = os.getenv(key, "").lower()
    return value in ("true", "1", "yes", "on")

# Core bot configuration
TOKEN = get_required_env("DISCORD_TOKEN")
GUILD_ID = get_int_env("GUILD_ID")

# Role and channel IDs
VERIFIED_ROLE_ID = get_int_env("VERIFIED_ROLE_ID")
VERIFICATION_CHANNEL_ID = get_int_env("VERIFICATION_CHANNEL_ID")
MOD_LOG_CHANNEL_ID = get_int_env("MOD_LOG_CHANNEL_ID")
AI_BANNED_ROLE_ID = get_int_env("AI_BANNED_ROLE_ID")

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

# AI Configuration
AI_ENABLED = get_bool_env("AI_ENABLED", False)
AI_PROVIDER = get_optional_env("AI_PROVIDER", "openai")  # "openai", "gemini", or "local"

# OpenAI
AI_OPENAI_API_KEY = get_optional_env("OPENAI_API_KEY")
AI_OPENAI_MODEL = get_optional_env("AI_OPENAI_MODEL", "gpt-5-nano")
AI_OPENAI_PRO_MODEL = get_optional_env("AI_OPENAI_PRO_MODEL", "gpt-5-mini")  # advanced reasoning

# Gemini
AI_GEMINI_API_KEY = get_optional_env("AI_GEMINI_API_KEY")
AI_GEMINI_MODEL = get_optional_env("AI_GEMINI_MODEL", "gemini-2.5-flash-lite")      
AI_GEMINI_PRO_MODEL = get_optional_env("AI_GEMINI_PRO_MODEL", "gemini-2.5-flash")  # 2.5 Flash model for complex problems
AI_MAX_TOKENS = get_int_env("AI_MAX_TOKENS", 100)
AI_MAX_TOKENS_PRO = get_int_env("AI_MAX_TOKENS_PRO", 500)  # Higher token limit for pro model
AI_TEMPERATURE = float(get_optional_env("AI_TEMPERATURE", "0.7"))
AI_TEMPERATURE_PRO = float(get_optional_env("AI_TEMPERATURE_PRO", "0.3"))  # Lower temperature for more focused reasoning
AI_TOP_P = float(get_optional_env("AI_TOP_P", "0.9"))
AI_TOP_P_PRO = float(get_optional_env("AI_TOP_P_PRO", "0.8"))  # Slightly lower for more focused responses
AI_REPETITION_PENALTY = float(get_optional_env("AI_REPETITION_PENALTY", "1.1"))
AI_INCLUDE_EXPERIENCE = get_bool_env("AI_INCLUDE_EXPERIENCE", True)
AI_INCLUDE_FOOTER = get_bool_env("AI_INCLUDE_FOOTER", False)  # Whether to append timing/token footer to replies

# Logging configuration
LOG_LEVEL = get_optional_env("LOG_LEVEL", "INFO")

# Legacy local model config (for backward compatibility)
AI_MODEL_NAME = get_optional_env("AI_MODEL_NAME", "meta-llama/Meta-Llama-3.1-8B-Instruct")
AI_HF_TOKEN = get_optional_env("AI_HF_TOKEN")
AI_USE_4BIT = get_bool_env("AI_USE_4BIT", True)
AI_USE_GPU = get_bool_env("AI_USE_GPU", True)

# Note: System prompts are now loaded directly in the AI cog via prompt_loader
# This avoids duplication and makes the prompts easier to maintain

# Operational Limits
CHANNEL_HISTORY_LIMIT = get_int_env("CHANNEL_HISTORY_LIMIT", 5)
MAX_TOOL_CYCLES = get_int_env("MAX_TOOL_CYCLES", 5)
HTTP_TIMEOUT_SECONDS = float(get_optional_env("HTTP_TIMEOUT_SECONDS", "10.0"))
ATTACHMENT_MAX_SIZE_BYTES = get_int_env("ATTACHMENT_MAX_SIZE_BYTES", 5000)
DISCORD_MESSAGE_CHUNK_SIZE = get_int_env("DISCORD_MESSAGE_CHUNK_SIZE", 1900)
INSPECT_HISTORY_LIMIT = get_int_env("INSPECT_HISTORY_LIMIT", 50)
VERIFICATION_HISTORY_LIMIT = get_int_env("VERIFICATION_HISTORY_LIMIT", 20)

# AI Tool Configuration
AI_LITE_ALLOWED_TOOLS = {
    "read_attachment_file", "get_schedule_today", "get_schedule_date",
    "get_next_meeting", "find_meeting", "get_meeting_notes", "think_harder"
}

# Validate required configuration
if not TOKEN:
    raise ValueError("DISCORD_TOKEN is required")
if not GUILD_ID:
    raise ValueError("GUILD_ID is required")
if not VERIFIED_ROLE_ID:
    raise ValueError("VERIFIED_ROLE_ID is required")

# Validate AI configuration if enabled
if AI_ENABLED:
    if AI_PROVIDER == "openai" and not AI_OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is required when AI_PROVIDER is 'openai'")
    elif AI_PROVIDER == "gemini" and not AI_GEMINI_API_KEY:
        raise ValueError("AI_GEMINI_API_KEY is required when AI_PROVIDER is 'gemini'")
    elif AI_PROVIDER == "local" and not AI_HF_TOKEN:
        raise ValueError("AI_HF_TOKEN is required when AI_PROVIDER is 'local'")
