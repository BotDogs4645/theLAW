"""Schedules database operations."""
import sqlite3
import logging
import json
from datetime import datetime
from typing import Optional, List, Dict, Any

from .connection import get_db_connection
from ..enums import SubTeam

logger = logging.getLogger(__name__)


def _parse_schedule_row(row) -> dict:
    """Parse a schedule row and convert teachers JSON to list."""
    schedule = dict(row)
    schedule['teachers'] = json.loads(schedule['teachers_json'])
    del schedule['teachers_json']
    schedule['notes'] = None
    schedule['slides_url'] = None
    return schedule


def add_schedule(starts_at: str, ends_at: str, sub_team: str, room: str, title: str,
                 teachers: List[Dict[str, Any]], description: str = None,
                 slides_url: str = None, notes: str = None) -> bool:
    """Add a new schedule item."""
    try:
        if not SubTeam.is_valid(sub_team):
            logger.error(f"Invalid subteam: {sub_team}. Valid options: {SubTeam.get_all_values()}")
            return False

        with get_db_connection() as conn:
            cursor = conn.cursor()
            now_iso = datetime.utcnow().isoformat()
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
    """Get a schedule item by ID."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,))
            result = cursor.fetchone()
            if result:
                schedule = dict(result)
                schedule['teachers'] = json.loads(schedule['teachers_json'])
                del schedule['teachers_json']
                if not include_notes:
                    schedule['notes'] = None
                    schedule['slides_url'] = None
                return schedule
            return None
    except sqlite3.Error as e:
        logger.error(f"Error getting schedule by ID: {e}")
        return None


def get_all_schedules() -> List[dict]:
    """Get all schedule items."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM schedules ORDER BY starts_at ASC")
            results = cursor.fetchall()
            return [_parse_schedule_row(row) for row in results]
    except sqlite3.Error as e:
        logger.error(f"Error getting all schedules: {e}")
        return []


def get_schedules_by_date_range(start_date: str, end_date: str) -> List[dict]:
    """Get schedules within a date range."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM schedules
                WHERE starts_at >= ? AND starts_at <= ?
                ORDER BY starts_at ASC
            """, (start_date, end_date))
            results = cursor.fetchall()
            return [_parse_schedule_row(row) for row in results]
    except sqlite3.Error as e:
        logger.error(f"Error getting schedules by date range: {e}")
        return []


def get_schedules_by_sub_team(sub_team: str) -> List[dict]:
    """Get schedules for a specific sub team."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM schedules
                WHERE sub_team = ?
                ORDER BY starts_at ASC
            """, (sub_team,))
            results = cursor.fetchall()
            return [_parse_schedule_row(row) for row in results]
    except sqlite3.Error as e:
        logger.error(f"Error getting schedules by sub team: {e}")
        return []


def update_schedule(schedule_id: int, starts_at: str = None, ends_at: str = None,
                    sub_team: str = None, room: str = None, title: str = None,
                    description: str = None, teachers: List[Dict[str, Any]] = None,
                    slides_url: str = None, notes: str = None) -> bool:
    """Update an existing schedule item."""
    try:
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
                return False

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
    """Delete a schedule item by ID."""
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
    """Search schedules by title, description, or sub team."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM schedules
                WHERE (title LIKE ? OR description LIKE ? OR sub_team LIKE ? OR room LIKE ?)
                ORDER BY starts_at ASC
            """, (f"%{search_term}%", f"%{search_term}%", f"%{search_term}%", f"%{search_term}%"))
            results = cursor.fetchall()
            return [_parse_schedule_row(row) for row in results]
    except sqlite3.Error as e:
        logger.error(f"Error searching schedules: {e}")
        return []


def get_valid_subteams() -> List[str]:
    """Get all valid subteam values."""
    return SubTeam.get_all_values()
