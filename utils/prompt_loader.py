"""
Prompt loader utility for loading system prompts from markdown files
"""
import os
from pathlib import Path

def load_prompt(prompt_name: str) -> str:
    """Load a prompt from the prompts folder"""
    prompts_dir = Path(__file__).parent.parent / "prompts"
    prompt_file = prompts_dir / f"{prompt_name}.md"
    
    if not prompt_file.exists():
        # fallback for when running from a different working directory
        prompts_dir = Path.cwd() / "prompts"
        prompt_file = prompts_dir / f"{prompt_name}.md"
        if not prompt_file.exists():
            raise FileNotFoundError(f"Prompt file not found in primary or fallback path: {prompt_file}")
    
    with open(prompt_file, 'r', encoding='utf-8') as f:
        return f.read().strip()

def load_generic_prompt() -> str:
    """Load the generic persona prompt"""
    return load_prompt("generic")

def load_lite_model_prompt() -> str:
    """Load the complete prompt for the lite model."""
    generic_prompt = load_generic_prompt()
    lite_instructions = load_prompt("lite_model")
    return f"{generic_prompt}\n\n{lite_instructions}"

def load_advanced_model_prompt() -> str:
    """Load the complete prompt for the advanced model."""
    generic_prompt = load_generic_prompt()
    advanced_instructions = load_prompt("advanced_model")
    return f"{generic_prompt}\n\n{advanced_instructions}"

def load_experience_prompt() -> str:
    """Load the FRC experience handbook prompt"""
    try:
        return load_prompt("experience")
    except FileNotFoundError:
        return ""