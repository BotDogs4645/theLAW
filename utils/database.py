import sqlite3
import os
import logging
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from .enums import SubTeam

DB_FILE = "verified_users.db"
logger = logging.getLogger(__name__)

@contextmanager
def get_db_connection():
    """context manager for database connections with proper error handling"""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row  # enable column access by name
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
    """initializes the database and creates the tables"""
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
                CREATE TABLE IF NOT EXISTS ai_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_key TEXT NOT NULL UNIQUE,
                    memory_content TEXT NOT NULL,
                    memory_type TEXT NOT NULL DEFAULT 'general',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    created_by_discord_id INTEGER,
                    is_active BOOLEAN NOT NULL DEFAULT 1
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
            
            # AI interaction logging tables
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
    return datetime.utcnow().isoformat()

def start_ai_interaction(guild_id: int = None, channel_id: int = None, author_id: int = None, message_id: int = None, question: str = None, chat_history_json: str = None) -> Optional[int]:
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

def complete_ai_interaction(interaction_id: int, *, pro_mode: bool = None, model_name: str = None, response_text: str = None, total_elapsed_ms: float = None, gemini_total_ms: float = None, discord_reply_ms: float = None, tool_calls_count: int = None) -> bool:
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

def log_ai_gemini_call(interaction_id: int, *, model_name: str, tool_mode: str, allow_functions_json: str, started_at: str, elapsed_ms: float) -> bool:
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

def log_ai_function_call(interaction_id: int, *, sequence_index: int, function_name: str, params_json: str, result_json: str, started_at: str, elapsed_ms: float) -> bool:
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

def log_ai_discord_step(interaction_id: int, *, step_name: str, started_at: str, elapsed_ms: float, extra_json: str = None) -> bool:
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

def is_user_verified(discord_id: int) -> bool:
    """checks if a user's Discord ID is already in the database"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM verified_users WHERE discord_id = ?", (discord_id,))
            result = cursor.fetchone()
            return result is not None
    except sqlite3.Error as e:
        logger.error(f"Error checking if user is verified: {e}")
        return False

def is_name_taken(full_name: str) -> bool:
    """checks if a full name has already been claimed in the database"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM verified_users WHERE full_name = ?", (full_name,))
            result = cursor.fetchone()
            return result is not None
    except sqlite3.Error as e:
        logger.error(f"Error checking if name is taken: {e}")
        return False

def is_email_verified(email: str) -> bool:
    """checks if an email has already been verified in the database"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM verified_users WHERE email = ?", (email,))
            result = cursor.fetchone()
            return result is not None
    except sqlite3.Error as e:
        logger.error(f"Error checking if email is verified: {e}")
        return False

def add_verified_user(discord_id: int, full_name: str, email: str, assigned_role_ids: List[int]):
    """adds a newly verified user to the database with timestamps and assigned roles"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # get the current time in a format that's good for storing and sorting
            now_iso = datetime.utcnow().isoformat()
            
            # convert the list of role IDs into a comma-separated string for storage
            roles_str = ",".join(map(str, assigned_role_ids))
            
            cursor.execute("""
                INSERT INTO verified_users (
                    discord_id, 
                    full_name, 
                    email,
                    verified_at, 
                    roles_last_checked_at, 
                    roles_last_updated_at, 
                    stored_roles
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (discord_id, full_name, email, now_iso, now_iso, now_iso, roles_str))
            conn.commit()
            logger.info(f"Successfully added verified user: {full_name} ({email}) (ID: {discord_id})")
    except sqlite3.IntegrityError as e:
        logger.warning(f"User already exists in database: {e}")
    except sqlite3.Error as e:
        logger.error(f"Error adding user to database: {e}")
        raise

def get_verified_user(discord_id: int) -> Optional[dict]:
    """get verified user data by Discord ID"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM verified_users WHERE discord_id = ?", (discord_id,))
            result = cursor.fetchone()
            return dict(result) if result else None
    except sqlite3.Error as e:
        logger.error(f"Error getting verified user: {e}")
        return None

def get_all_verified_users() -> List[dict]:
    """get all verified users from the database"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM verified_users ORDER BY verified_at DESC")
            results = cursor.fetchall()
            return [dict(row) for row in results]
    except sqlite3.Error as e:
        logger.error(f"Error getting all verified users: {e}")
        return []


# role sync bookkeeping
def update_verified_user_roles(discord_id: int, stored_role_ids: List[int], *, checked_only: bool = False) -> bool:
    """Update verified user's stored roles and timestamps.

    When checked_only is True, only updates roles_last_checked_at and stored_roles.
    When False, updates both roles_last_checked_at and roles_last_updated_at in addition to stored_roles.
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            now_iso = datetime.utcnow().isoformat()
            roles_str = ",".join(map(str, stored_role_ids))

            if checked_only:
                cursor.execute(
                    """
                        UPDATE verified_users
                        SET roles_last_checked_at = ?, stored_roles = ?
                        WHERE discord_id = ?
                    """,
                    (now_iso, roles_str, discord_id),
                )
            else:
                cursor.execute(
                    """
                        UPDATE verified_users
                        SET roles_last_checked_at = ?, roles_last_updated_at = ?, stored_roles = ?
                        WHERE discord_id = ?
                    """,
                    (now_iso, now_iso, roles_str, discord_id),
                )

            conn.commit()
            return cursor.rowcount > 0
    except sqlite3.Error as e:
        logger.error(f"Error updating verified user roles: {e}")
        return False

# student management functions
def add_or_update_student(email: str, first_name: str, last_name: str, teams: List[str] = None):
    """Add a new student or update existing student by email"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # get the current time
            now_iso = datetime.utcnow().isoformat()
            full_name = f"{first_name} {last_name}"
            teams_str = ":".join(teams) if teams else ""
            
            # check if student exists
            cursor.execute("SELECT email FROM students WHERE email = ?", (email,))
            exists = cursor.fetchone() is not None
            
            if exists:
                # update existing student
                cursor.execute("""
                    UPDATE students 
                    SET first_name = ?, last_name = ?, full_name = ?, teams = ?, updated_at = ?
                    WHERE email = ?
                """, (first_name, last_name, full_name, teams_str, now_iso, email))
                logger.info(f"Updated student: {full_name} ({email})")
            else:
                # insert new student
                cursor.execute("""
                    INSERT INTO students (email, first_name, last_name, full_name, teams, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (email, first_name, last_name, full_name, teams_str, now_iso, now_iso))
                logger.info(f"Added new student: {full_name} ({email})")
            
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Error adding/updating student: {e}")
        raise

def get_student_by_email(email: str) -> Optional[dict]:
    """get student by email"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM students WHERE email = ?", (email,))
            result = cursor.fetchone()
            if result:
                student = dict(result)
                # parse teams back to list
                student['teams'] = student['teams'].split(':') if student['teams'] else []
                return student
            return None
    except sqlite3.Error as e:
        logger.error(f"Error getting student by email: {e}")
        return None

def get_student_by_name(full_name: str) -> Optional[dict]:
    """get student by full name (case insensitive)"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM students WHERE LOWER(full_name) = ?", (full_name.lower(),))
            result = cursor.fetchone()
            if result:
                student = dict(result)
                # parse teams back to list
                student['teams'] = student['teams'].split(':') if student['teams'] else []
                return student
            return None
    except sqlite3.Error as e:
        logger.error(f"Error getting student by name: {e}")
        return None

def get_all_students() -> List[dict]:
    """get all students from the database"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM students ORDER BY full_name")
            results = cursor.fetchall()
            students = []
            for row in results:
                student = dict(row)
                # parse teams back to list
                student['teams'] = student['teams'].split(':') if student['teams'] else []
                students.append(student)
            return students
    except sqlite3.Error as e:
        logger.error(f"Error getting all students: {e}")
        return []

def delete_student(email: str) -> bool:
    """delete a student by email"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM students WHERE email = ?", (email,))
            conn.commit()
            if cursor.rowcount > 0:
                logger.info(f"Deleted student with email: {email}")
                return True
            return False
    except sqlite3.Error as e:
        logger.error(f"Error deleting student: {e}")
        return False

def delete_verified_user(discord_id: int) -> bool:
    """delete a verified user by Discord ID"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM verified_users WHERE discord_id = ?", (discord_id,))
            conn.commit()
            if cursor.rowcount > 0:
                logger.info(f"Deleted verified user with Discord ID: {discord_id}")
                return True
            else:
                logger.info(f"No verified user found with Discord ID: {discord_id}")
                return False
    except sqlite3.Error as e:
        logger.error(f"Error deleting verified user: {e}")
        return False

# AI Memory Management Functions
def add_ai_memory(memory_key: str, memory_content: str, memory_type: str = "general", created_by_discord_id: int = None) -> bool:
    """Add a new AI memory"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            now_iso = datetime.utcnow().isoformat()
            
            cursor.execute("""
                INSERT INTO ai_memories (memory_key, memory_content, memory_type, created_at, updated_at, created_by_discord_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (memory_key, memory_content, memory_type, now_iso, now_iso, created_by_discord_id))
            conn.commit()
            logger.info(f"Added AI memory: {memory_key}")
            return True
    except sqlite3.IntegrityError:
        logger.warning(f"Memory key already exists: {memory_key}")
        return False
    except sqlite3.Error as e:
        logger.error(f"Error adding AI memory: {e}")
        return False

def get_ai_memory(memory_key: str) -> Optional[dict]:
    """Get an AI memory by key"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM ai_memories WHERE memory_key = ? AND is_active = 1", (memory_key,))
            result = cursor.fetchone()
            return dict(result) if result else None
    except sqlite3.Error as e:
        logger.error(f"Error getting AI memory: {e}")
        return None

def update_ai_memory(memory_key: str, memory_content: str, memory_type: str = None) -> bool:
    """Update an existing AI memory"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            now_iso = datetime.utcnow().isoformat()
            
            if memory_type:
                cursor.execute("""
                    UPDATE ai_memories 
                    SET memory_content = ?, memory_type = ?, updated_at = ?
                    WHERE memory_key = ? AND is_active = 1
                """, (memory_content, memory_type, now_iso, memory_key))
            else:
                cursor.execute("""
                    UPDATE ai_memories 
                    SET memory_content = ?, updated_at = ?
                    WHERE memory_key = ? AND is_active = 1
                """, (memory_content, now_iso, memory_key))
            
            conn.commit()
            if cursor.rowcount > 0:
                logger.info(f"Updated AI memory: {memory_key}")
                return True
            return False
    except sqlite3.Error as e:
        logger.error(f"Error updating AI memory: {e}")
        return False

def delete_ai_memory(memory_key: str) -> bool:
    """Soft delete an AI memory (set is_active to 0)"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            now_iso = datetime.utcnow().isoformat()
            
            cursor.execute("""
                UPDATE ai_memories 
                SET is_active = 0, updated_at = ?
                WHERE memory_key = ?
            """, (now_iso, memory_key))
            
            conn.commit()
            if cursor.rowcount > 0:
                logger.info(f"Deleted AI memory: {memory_key}")
                return True
            return False
    except sqlite3.Error as e:
        logger.error(f"Error deleting AI memory: {e}")
        return False

def get_all_ai_memories(memory_type: str = None) -> List[dict]:
    """Get all active AI memories, optionally filtered by type"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if memory_type:
                cursor.execute("""
                    SELECT * FROM ai_memories 
                    WHERE memory_type = ? AND is_active = 1 
                    ORDER BY updated_at DESC
                """, (memory_type,))
            else:
                cursor.execute("""
                    SELECT * FROM ai_memories 
                    WHERE is_active = 1 
                    ORDER BY updated_at DESC
                """)
            results = cursor.fetchall()
            return [dict(row) for row in results]
    except sqlite3.Error as e:
        logger.error(f"Error getting AI memories: {e}")
        return []

def search_ai_memories(search_term: str) -> List[dict]:
    """Search AI memories by content"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM ai_memories 
                WHERE (memory_content LIKE ? OR memory_key LIKE ?) AND is_active = 1 
                ORDER BY updated_at DESC
            """, (f"%{search_term}%", f"%{search_term}%"))
            results = cursor.fetchall()
            return [dict(row) for row in results]
    except sqlite3.Error as e:
        logger.error(f"Error searching AI memories: {e}")
        return []

# schedule management functions
def add_schedule(starts_at: str, ends_at: str, sub_team: str, room: str, title: str, 
                teachers: List[Dict[str, Any]], description: str = None, 
                slides_url: str = None, notes: str = None) -> bool:
    """Add a new schedule item"""
    try:
        # validate subteam
        if not SubTeam.is_valid(sub_team):
            logger.error(f"Invalid subteam: {sub_team}. Valid options: {SubTeam.get_all_values()}")
            return False
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            now_iso = datetime.utcnow().isoformat()
            
            # convert teachers list to JSON string
            teachers_json = json.dumps(teachers)
            
            cursor.execute("""
                INSERT INTO schedules (
                    starts_at, ends_at, sub_team, room, title, description, 
                    teachers_json, slides_url, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (starts_at, ends_at, sub_team, room, title, description, 
                  teachers_json, slides_url, notes, now_iso, now_iso))
            
            conn.commit()
            logger.info(f"Added schedule item: {title} at {starts_at}")
            return True
    except sqlite3.Error as e:
        logger.error(f"Error adding schedule item: {e}")
        return False

def get_schedule_by_id(schedule_id: int, include_notes: bool = False) -> Optional[dict]:
    """Get a schedule item by ID"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,))
            result = cursor.fetchone()
            if result:
                schedule = dict(result)
                # parse teachers JSON back to list
                schedule['teachers'] = json.loads(schedule['teachers_json'])
                del schedule['teachers_json']  # Remove the JSON field
                
                # gate notes unless specifically requested
                if not include_notes:
                    schedule['notes'] = None
                    schedule['slides_url'] = None
                
                return schedule
            return None
    except sqlite3.Error as e:
        logger.error(f"Error getting schedule by ID: {e}")
        return None

def get_all_schedules() -> List[dict]:
    """Get all schedule items"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM schedules ORDER BY starts_at ASC")
            results = cursor.fetchall()
            schedules = []
            for row in results:
                schedule = dict(row)
                # parse teachers JSON back to list
                schedule['teachers'] = json.loads(schedule['teachers_json'])
                del schedule['teachers_json']
                
                # gate notes and slides_url to save context
                schedule['notes'] = None
                schedule['slides_url'] = None
                
                schedules.append(schedule)
            return schedules
    except sqlite3.Error as e:
        logger.error(f"Error getting all schedules: {e}")
        return []

def get_schedules_by_date_range(start_date: str, end_date: str) -> List[dict]:
    """Get schedules within a date range"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM schedules 
                WHERE starts_at >= ? AND starts_at <= ? 
                ORDER BY starts_at ASC
            """, (start_date, end_date))
            results = cursor.fetchall()
            schedules = []
            for row in results:
                schedule = dict(row)
                # parse teachers JSON back to list
                schedule['teachers'] = json.loads(schedule['teachers_json'])
                del schedule['teachers_json']
                
                # gate notes and slides_url to save context
                schedule['notes'] = None
                schedule['slides_url'] = None
                
                schedules.append(schedule)
            return schedules
    except sqlite3.Error as e:
        logger.error(f"Error getting schedules by date range: {e}")
        return []

def get_schedules_by_sub_team(sub_team: str) -> List[dict]:
    """Get schedules for a specific sub team"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM schedules 
                WHERE sub_team = ? 
                ORDER BY starts_at ASC
            """, (sub_team,))
            results = cursor.fetchall()
            schedules = []
            for row in results:
                schedule = dict(row)
                # parse teachers JSON back to list
                schedule['teachers'] = json.loads(schedule['teachers_json'])
                del schedule['teachers_json']
                
                # gate notes and slides_url to save context
                schedule['notes'] = None
                schedule['slides_url'] = None
                
                schedules.append(schedule)
            return schedules
    except sqlite3.Error as e:
        logger.error(f"Error getting schedules by sub team: {e}")
        return []

def update_schedule(schedule_id: int, starts_at: str = None, ends_at: str = None, 
                   sub_team: str = None, room: str = None, title: str = None, 
                   description: str = None, teachers: List[Dict[str, Any]] = None, 
                   slides_url: str = None, notes: str = None) -> bool:
    """Update an existing schedule item"""
    try:
        # validate subteam if provided
        if sub_team is not None and not SubTeam.is_valid(sub_team):
            logger.error(f"Invalid subteam: {sub_team}. Valid options: {SubTeam.get_all_values()}")
            return False
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            now_iso = datetime.utcnow().isoformat()
            
            update_fields = []
            update_values = []
            
            if starts_at is not None:
                update_fields.append("starts_at = ?")
                update_values.append(starts_at)
            if ends_at is not None:
                update_fields.append("ends_at = ?")
                update_values.append(ends_at)
            if sub_team is not None:
                update_fields.append("sub_team = ?")
                update_values.append(sub_team)
            if room is not None:
                update_fields.append("room = ?")
                update_values.append(room)
            if title is not None:
                update_fields.append("title = ?")
                update_values.append(title)
            if description is not None:
                update_fields.append("description = ?")
                update_values.append(description)
            if teachers is not None:
                update_fields.append("teachers_json = ?")
                update_values.append(json.dumps(teachers))
            if slides_url is not None:
                update_fields.append("slides_url = ?")
                update_values.append(slides_url)
            if notes is not None:
                update_fields.append("notes = ?")
                update_values.append(notes)
            
            if not update_fields:
                return False  # No fields to update
            
            update_fields.append("updated_at = ?")
            update_values.append(now_iso)
            update_values.append(schedule_id)
            
            query = f"UPDATE schedules SET {', '.join(update_fields)} WHERE id = ?"
            cursor.execute(query, update_values)
            
            conn.commit()
            if cursor.rowcount > 0:
                logger.info(f"Updated schedule item ID: {schedule_id}")
                return True
            return False
    except sqlite3.Error as e:
        logger.error(f"Error updating schedule: {e}")
        return False

def delete_schedule(schedule_id: int) -> bool:
    """Delete a schedule item by ID"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
            conn.commit()
            if cursor.rowcount > 0:
                logger.info(f"Deleted schedule item ID: {schedule_id}")
                return True
            return False
    except sqlite3.Error as e:
        logger.error(f"Error deleting schedule: {e}")
        return False

def search_schedules(search_term: str) -> List[dict]:
    """Search schedules by title, description, or sub team"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM schedules 
                WHERE (title LIKE ? OR description LIKE ? OR sub_team LIKE ? OR room LIKE ?) 
                ORDER BY starts_at ASC
            """, (f"%{search_term}%", f"%{search_term}%", f"%{search_term}%", f"%{search_term}%"))
            results = cursor.fetchall()
            schedules = []
            for row in results:
                schedule = dict(row)
                # parse teachers JSON back to list
                schedule['teachers'] = json.loads(schedule['teachers_json'])
                del schedule['teachers_json']
                
                # gate notes and slides_url to save context
                schedule['notes'] = None
                schedule['slides_url'] = None
                
                schedules.append(schedule)
            return schedules
    except sqlite3.Error as e:
        logger.error(f"Error searching schedules: {e}")
        return []

def get_valid_subteams() -> List[str]:
    """Get all valid subteam values"""
    return SubTeam.get_all_values()
