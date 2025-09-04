# /utils/database.py
import sqlite3
import os
from datetime import datetime

DB_FILE = "verified_users.db"

def setup_database():
    """Initializes the database and creates the tables."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS verified_users (
            discord_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL UNIQUE,
            verified_at TEXT NOT NULL,
            roles_last_checked_at TEXT,
            roles_last_updated_at TEXT,
            stored_roles TEXT
        )
    """)
    conn.commit()
    conn.close()
    print("Database setup complete with the new schema.")

def is_user_verified(discord_id: int) -> bool:
    """Checks if a user's Discord ID is already in the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM verified_users WHERE discord_id = ?", (discord_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def is_name_taken(full_name: str) -> bool:
    """Checks if a full name has already been claimed in the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM verified_users WHERE full_name = ?", (full_name,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def add_verified_user(discord_id: int, full_name: str, assigned_role_ids: list[int]):
    """Adds a newly verified user to the database with timestamps and assigned roles."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # get the current time in a format that's good for storing and sorting.
    now_iso = datetime.utcnow().isoformat()
    
    # convert the list of role IDs into a comma-separated string for storage.
    roles_str = ",".join(map(str, assigned_role_ids))
    
    try:
        cursor.execute("""
            INSERT INTO verified_users (
                discord_id, 
                full_name, 
                verified_at, 
                roles_last_checked_at, 
                roles_last_updated_at, 
                stored_roles
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (discord_id, full_name, now_iso, now_iso, now_iso, roles_str))
        conn.commit()
    except sqlite3.IntegrityError as e:
        print(f"Error adding user to database (likely already exists): {e}")
    finally:
        conn.close()
