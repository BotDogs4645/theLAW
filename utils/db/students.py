"""Students database operations."""
import sqlite3
import logging
from datetime import datetime
from typing import Optional, List

from .connection import get_db_connection

logger = logging.getLogger(__name__)


def add_or_update_student(email: str, first_name: str, last_name: str, teams: List[str] = None):
    """Add a new student or update existing student by email."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            now_iso = datetime.utcnow().isoformat()
            full_name = f"{first_name} {last_name}"
            teams_str = ":".join(teams) if teams else ""

            cursor.execute("SELECT email FROM students WHERE email = ?", (email,))
            exists = cursor.fetchone() is not None

            if exists:
                cursor.execute("""
                    UPDATE students
                    SET first_name = ?, last_name = ?, full_name = ?, teams = ?, updated_at = ?
                    WHERE email = ?
                """, (first_name, last_name, full_name, teams_str, now_iso, email))
                logger.info(f"Updated student: {full_name} ({email})")
            else:
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
    """Get student by email."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM students WHERE email = ?", (email,))
            result = cursor.fetchone()
            if result:
                student = dict(result)
                student['teams'] = student['teams'].split(':') if student['teams'] else []
                return student
            return None
    except sqlite3.Error as e:
        logger.error(f"Error getting student by email: {e}")
        return None


def get_student_by_name(full_name: str) -> Optional[dict]:
    """Get student by full name (case insensitive)."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM students WHERE LOWER(full_name) = ?", (full_name.lower(),))
            result = cursor.fetchone()
            if result:
                student = dict(result)
                student['teams'] = student['teams'].split(':') if student['teams'] else []
                return student
            return None
    except sqlite3.Error as e:
        logger.error(f"Error getting student by name: {e}")
        return None


def get_all_students() -> List[dict]:
    """Get all students from the database."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM students ORDER BY full_name")
            results = cursor.fetchall()
            students = []
            for row in results:
                student = dict(row)
                student['teams'] = student['teams'].split(':') if student['teams'] else []
                students.append(student)
            return students
    except sqlite3.Error as e:
        logger.error(f"Error getting all students: {e}")
        return []


def delete_student(email: str) -> bool:
    """Delete a student by email."""
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
