import sqlite3
import os
import logging
from datetime import datetime
from typing import Optional, List
from contextlib import contextmanager

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
            
            conn.commit()
        logger.info("Database setup complete with the new schema.")
    except sqlite3.Error as e:
        logger.error(f"Failed to setup database: {e}")
        raise

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
