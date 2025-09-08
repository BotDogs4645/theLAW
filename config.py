import os
from dotenv import load_dotenv
from typing import Optional
from utils.prompt_loader import load_generic_prompt, load_lite_model_prompt, load_advanced_model_prompt, load_experience_prompt

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
AI_PROVIDER = get_optional_env("AI_PROVIDER", "gemini")  # "gemini" or "local"
AI_GEMINI_API_KEY = get_optional_env("AI_GEMINI_API_KEY")
AI_GEMINI_MODEL = get_optional_env("AI_GEMINI_MODEL", "gemini-2.5-flash-lite")  # 2.5 Flash Lite for regular responses
AI_GEMINI_PRO_MODEL = get_optional_env("AI_GEMINI_PRO_MODEL", "gemini-2.5-flash")  # 2.5 Flash model for complex problems
AI_MAX_TOKENS = get_int_env("AI_MAX_TOKENS", 100)
AI_MAX_TOKENS_PRO = get_int_env("AI_MAX_TOKENS_PRO", 500)  # Higher token limit for pro model
AI_TEMPERATURE = float(get_optional_env("AI_TEMPERATURE", "0.7"))
AI_TEMPERATURE_PRO = float(get_optional_env("AI_TEMPERATURE_PRO", "0.3"))  # Lower temperature for more focused reasoning
AI_TOP_P = float(get_optional_env("AI_TOP_P", "0.9"))
AI_TOP_P_PRO = float(get_optional_env("AI_TOP_P_PRO", "0.8"))  # Slightly lower for more focused responses
AI_REPETITION_PENALTY = float(get_optional_env("AI_REPETITION_PENALTY", "1.1"))
AI_INCLUDE_EXPERIENCE = get_bool_env("AI_INCLUDE_EXPERIENCE", True)

# Logging configuration
LOG_LEVEL = get_optional_env("LOG_LEVEL", "INFO")

# Legacy local model config (for backward compatibility)
AI_MODEL_NAME = get_optional_env("AI_MODEL_NAME", "meta-llama/Meta-Llama-3.1-8B-Instruct")
AI_HF_TOKEN = get_optional_env("AI_HF_TOKEN")
AI_USE_4BIT = get_bool_env("AI_USE_4BIT", True)
AI_USE_GPU = get_bool_env("AI_USE_GPU", True)

# AI System Prompt
def _load_system_prompt():
    """Load the system prompt from files"""
    try:
        generic = load_generic_prompt()
        lite_specific = load_lite_model_prompt()
        if AI_INCLUDE_EXPERIENCE:
            try:
                experience = load_experience_prompt()
            except FileNotFoundError:
                experience = ""
        else:
            experience = ""
        parts = [generic, lite_specific]
        if experience:
            parts.append(experience)
        return "\n\n".join([p for p in parts if p])
    except FileNotFoundError:
        # Fallback to hardcoded prompt if files don't exist
        return """You are **the LAW**, a mischievous presence created by First Robotics Competition (FRC) Team 4645."""

AI_SYSTEM_PROMPT = get_optional_env("AI_SYSTEM_PROMPT", _load_system_prompt())

# AI Advanced System Prompt (for complex coding problems)
def _load_advanced_system_prompt():
    """Load the advanced system prompt from files"""
    try:
        generic = load_generic_prompt()
        advanced_specific = load_advanced_model_prompt()
        if AI_INCLUDE_EXPERIENCE:
            try:
                experience = load_experience_prompt()
            except FileNotFoundError:
                experience = ""
        else:
            experience = ""
        parts = [generic, advanced_specific]
        if experience:
            parts.append(experience)
        return "\n\n".join([p for p in parts if p])
    except FileNotFoundError:
        # Fallback to hardcoded prompt if files don't exist
        return """You are **the LAW**, a knowledgeable presence created by First Robotics Competition (FRC) Team 4645."""

AI_ADVANCED_SYSTEM_PROMPT = get_optional_env("AI_ADVANCED_SYSTEM_PROMPT", _load_advanced_system_prompt())

# Validate required configuration
if not TOKEN:
    raise ValueError("DISCORD_TOKEN is required")
if not GUILD_ID:
    raise ValueError("GUILD_ID is required")
if not VERIFIED_ROLE_ID:
    raise ValueError("VERIFIED_ROLE_ID is required")

# Validate AI configuration if enabled
if AI_ENABLED:
    if AI_PROVIDER == "gemini" and not AI_GEMINI_API_KEY:
        raise ValueError("AI_GEMINI_API_KEY is required when AI_PROVIDER is 'gemini'")
    elif AI_PROVIDER == "local" and not AI_HF_TOKEN:
        raise ValueError("AI_HF_TOKEN is required when AI_PROVIDER is 'local'")
