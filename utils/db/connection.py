"""Database connection and setup utilities."""
import sqlite3
import logging
from datetime import datetime
from contextlib import contextmanager

DB_FILE = "verified_users.db"
logger = logging.getLogger(__name__)


@contextmanager
def get_db_connection():
    """Context manager for database connections with proper error handling."""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        yield conn
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


def setup_database():
    """Initializes the database and creates the tables."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS verified_users (
                    discord_id INTEGER PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    verified_at TEXT NOT NULL,
                    roles_last_checked_at TEXT,
                    roles_last_updated_at TEXT,
                    stored_roles TEXT
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS students (
                    email TEXT PRIMARY KEY,
                    first_name TEXT NOT NULL,
                    last_name TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    teams TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    starts_at TEXT NOT NULL,
                    ends_at TEXT NOT NULL,
                    sub_team TEXT NOT NULL,
                    room TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    teachers_json TEXT NOT NULL,
                    slides_url TEXT,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    guild_id INTEGER,
                    channel_id INTEGER,
                    author_id INTEGER,
                    message_id INTEGER,
                    question TEXT,
                    chat_history_json TEXT,
                    pro_mode INTEGER,
                    model_name TEXT,
                    response_text TEXT,
                    total_elapsed_ms REAL,
                    gemini_total_ms REAL,
                    discord_reply_ms REAL,
                    tool_calls_count INTEGER
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_gemini_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    interaction_id INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL,
                    elapsed_ms REAL NOT NULL,
                    model_name TEXT,
                    tool_mode TEXT,
                    allow_functions_json TEXT,
                    FOREIGN KEY(interaction_id) REFERENCES ai_interactions(id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_function_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    interaction_id INTEGER NOT NULL,
                    sequence_index INTEGER NOT NULL,
                    function_name TEXT NOT NULL,
                    params_json TEXT,
                    result_json TEXT,
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL,
                    elapsed_ms REAL NOT NULL,
                    FOREIGN KEY(interaction_id) REFERENCES ai_interactions(id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_discord_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    interaction_id INTEGER NOT NULL,
                    step_name TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL,
                    elapsed_ms REAL NOT NULL,
                    extra_json TEXT,
                    FOREIGN KEY(interaction_id) REFERENCES ai_interactions(id)
                )
            """)

            conn.commit()
        logger.info("Database setup complete with the new schema.")
    except sqlite3.Error as e:
        logger.error(f"Failed to setup database: {e}")
        raise


def _now_iso() -> str:
    """Return current UTC time in ISO format."""
    return datetime.utcnow().isoformat()
