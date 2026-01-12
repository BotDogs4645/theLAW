"""Verified users database operations."""
import sqlite3
import logging
from datetime import datetime
from typing import Optional, List

from .connection import get_db_connection

logger = logging.getLogger(__name__)


def is_user_verified(discord_id: int) -> bool:
    """Checks if a user's Discord ID is already in the database."""
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
    """Checks if a full name has already been claimed in the database."""
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
    """Checks if an email has already been verified in the database."""
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
    """Adds a newly verified user to the database with timestamps and assigned roles."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            now_iso = datetime.utcnow().isoformat()
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
    """Get verified user data by Discord ID."""
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
    """Get all verified users from the database."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM verified_users ORDER BY verified_at DESC")
            results = cursor.fetchall()
            return [dict(row) for row in results]
    except sqlite3.Error as e:
        logger.error(f"Error getting all verified users: {e}")
        return []


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


def delete_verified_user(discord_id: int) -> bool:
    """Delete a verified user by Discord ID."""
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
