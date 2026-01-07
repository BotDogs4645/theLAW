"""
AI conversation handling utilities for building messages and managing conversations.
"""
from datetime import datetime
from typing import List, Dict, Any
import re


def clean_message_content(content: str, bot_id: int) -> str:
    """Removes bot mentions and normalizes whitespace."""
    content = re.sub(r'<@!?\d+>', '', content).strip()
    return " ".join(content.split())


def current_time_str() -> str:
    """Returns the current UTC time as an ISO string."""
    return datetime.utcnow().isoformat(timespec='seconds') + 'Z'


def build_system_prompt(*, pro: bool, prompt_loader) -> str:
    """
    Builds the system prompt with appropriate guidelines for the model.

    The lite model handles simple questions and escalates complex technical issues.
    The pro model provides detailed technical expertise after escalation.
    """
    base = prompt_loader.load_advanced_model_prompt() if pro else prompt_loader.load_lite_model_prompt()
    now = current_time_str()

    # General operational guidelines
    guidelines = (
        "Tool Usage: Prefer answering directly. Only call tools when necessary for the user's explicit request. "
        "Context Awareness: Use information from prior tool responses without calling more tools. "
        "No Fabrication: Never invent schedules, names, links, or data. If unknown, say so. "
        "Tone: For technical questions, be direct and helpful. For greetings or casual chat, use your persona."
    )

    # Model-specific tool guidelines
    if pro:
        tool_guideline = (
            "You are the ADVANCED MODEL. You were escalated to handle a complex technical problem. "
            "Do NOT call 'think_harder' - you are already the advanced reasoning tier. "
            "Provide detailed, accurate technical guidance."
        )
    else:
        tool_guideline = (
            "You are the LITE MODEL. Handle simple questions directly. "
            "Call 'think_harder' to escalate for: code implementation requests, debugging help, "
            "detailed engineering calculations, or architectural questions. "
            "Do NOT escalate for: greetings, simple concept explanations, or schedule questions."
        )

    return (
        f"Current datetime: {now}\n\n"
        f"Operational Guidelines:\n{guidelines}\n\n"
        f"Model Role:\n{tool_guideline}\n\n"
        f"---\n\n"
        f"{base}"
    )


def build_conversation_messages(history, asker, question, *, pro: bool, message_id: int, bot_user_id: int, prompt_loader) -> List[Dict[str, Any]]:
    """
    Build the conversation messages including system prompt, history, and current question.

    Args:
        history: List of discord.Message objects from channel history
        asker: discord.Member who asked the question
        question: The cleaned question text
        pro: Whether this is for the pro model
        message_id: The ID of the message being replied to
        bot_user_id: The bot's user ID
        prompt_loader: The prompt_loader module for loading prompts

    Returns:
        List of message dicts in OpenAI format
    """
    system_prompt = build_system_prompt(pro=pro, prompt_loader=prompt_loader)
    messages = [{"role": "system", "content": system_prompt}]

    # Add conversation history
    for msg in history:
        cleaned = clean_message_content(msg.content, bot_user_id)
        if not cleaned:
            continue

        if msg.author.id == bot_user_id:
            # Assistant messages: just the content (no timestamp/name to avoid the model copying the format)
            messages.append({"role": "assistant", "content": cleaned})
        else:
            # User messages: include timestamp and name for context
            ts = msg.created_at.isoformat(timespec="seconds") + "Z"
            author_name = msg.author.display_name
            content = f"[{ts}] {author_name}: {cleaned}"
            messages.append({"role": "user", "content": content})

    # Add current question with clear context
    now = current_time_str()
    user_line = f"[{now}] {asker.display_name} @mentions you (message ID {message_id}):\n{question}"
    messages.append({"role": "user", "content": user_line})

    return messages
