"""AI interaction logging database operations."""
import sqlite3
import logging
from typing import Optional

from .connection import get_db_connection, _now_iso

logger = logging.getLogger(__name__)


def start_ai_interaction(guild_id: int = None, channel_id: int = None, author_id: int = None,
                         message_id: int = None, question: str = None,
                         chat_history_json: str = None) -> Optional[int]:
    """Create a new AI interaction row and return its ID."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                    INSERT INTO ai_interactions (created_at, guild_id, channel_id, author_id, message_id, question, chat_history_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (_now_iso(), guild_id, channel_id, author_id, message_id, question, chat_history_json),
            )
            conn.commit()
            return cursor.lastrowid
    except sqlite3.Error as e:
        logger.error(f"Error starting AI interaction: {e}")
        return None


def complete_ai_interaction(interaction_id: int, *, pro_mode: bool = None, model_name: str = None,
                            response_text: str = None, total_elapsed_ms: float = None,
                            gemini_total_ms: float = None, discord_reply_ms: float = None,
                            tool_calls_count: int = None) -> bool:
    """Finalize an AI interaction with result metrics."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            update_fields = []
            update_values = []
            if pro_mode is not None:
                update_fields.append("pro_mode = ?")
                update_values.append(1 if pro_mode else 0)
            if model_name is not None:
                update_fields.append("model_name = ?")
                update_values.append(model_name)
            if response_text is not None:
                update_fields.append("response_text = ?")
                update_values.append(response_text)
            if total_elapsed_ms is not None:
                update_fields.append("total_elapsed_ms = ?")
                update_values.append(total_elapsed_ms)
            if gemini_total_ms is not None:
                update_fields.append("gemini_total_ms = ?")
                update_values.append(gemini_total_ms)
            if discord_reply_ms is not None:
                update_fields.append("discord_reply_ms = ?")
                update_values.append(discord_reply_ms)
            if tool_calls_count is not None:
                update_fields.append("tool_calls_count = ?")
                update_values.append(tool_calls_count)
            if not update_fields:
                return False
            update_values.append(interaction_id)
            cursor.execute(f"UPDATE ai_interactions SET {', '.join(update_fields)} WHERE id = ?", update_values)
            conn.commit()
            return cursor.rowcount > 0
    except sqlite3.Error as e:
        logger.error(f"Error completing AI interaction: {e}")
        return False


def log_ai_gemini_call(interaction_id: int, *, model_name: str, tool_mode: str,
                       allow_functions_json: str, started_at: str, elapsed_ms: float) -> bool:
    """Log a single Gemini API call timing and config."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            ended_at = _now_iso()
            cursor.execute(
                """
                    INSERT INTO ai_gemini_calls (interaction_id, started_at, ended_at, elapsed_ms, model_name, tool_mode, allow_functions_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (interaction_id, started_at, ended_at, elapsed_ms, model_name, tool_mode, allow_functions_json),
            )
            conn.commit()
            return True
    except sqlite3.Error as e:
        logger.error(f"Error logging Gemini call: {e}")
        return False


def log_ai_function_call(interaction_id: int, *, sequence_index: int, function_name: str,
                         params_json: str, result_json: str, started_at: str,
                         elapsed_ms: float) -> bool:
    """Log a single tool/function call and timing."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            ended_at = _now_iso()
            cursor.execute(
                """
                    INSERT INTO ai_function_calls (interaction_id, sequence_index, function_name, params_json, result_json, started_at, ended_at, elapsed_ms)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (interaction_id, sequence_index, function_name, params_json, result_json, started_at, ended_at, elapsed_ms),
            )
            conn.commit()
            return True
    except sqlite3.Error as e:
        logger.error(f"Error logging function call: {e}")
        return False


def log_ai_discord_step(interaction_id: int, *, step_name: str, started_at: str,
                        elapsed_ms: float, extra_json: str = None) -> bool:
    """Log a Discord-related step timing (e.g., sending reply, uploads)."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            ended_at = _now_iso()
            cursor.execute(
                """
                    INSERT INTO ai_discord_steps (interaction_id, step_name, started_at, ended_at, elapsed_ms, extra_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                (interaction_id, step_name, started_at, ended_at, elapsed_ms, extra_json),
            )
            conn.commit()
            return True
    except sqlite3.Error as e:
        logger.error(f"Error logging Discord step: {e}")
        return False
