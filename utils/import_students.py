#!/usr/bin/env python3
"""
Utility to import student data from CSV to database.
Supports email as unique key and updates existing records.
"""

import csv
import sys
import os
import re
import json
from typing import List, Dict, Optional

# add the parent directory to the path so we can import utils
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import setup_database, add_or_update_student, get_all_students, get_all_verified_users, update_verified_user_roles
from utils.logger import get_logger

logger = get_logger(__name__)

def validate_email(email: str) -> bool:
    """validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def load_role_mappings() -> Dict[str, int]:
    """Load role mappings from roles.json file"""
    try:
        roles_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'roles.json')
        if os.path.exists(roles_file):
            with open(roles_file, 'r') as f:
                role_map = json.load(f)
                logger.info(f"Loaded {len(role_map)} role mappings from roles.json")
                return role_map
        else:
            logger.warning("roles.json file not found, no role mappings available")
            return {}
    except Exception as e:
        logger.error(f"Error loading role mappings: {e}")
        return {}

def sync_roles_for_verified_users(role_map: Dict[str, int], verified_role_id: Optional[int] = None) -> Dict[str, int]:
    """
    Sync roles for verified users based on updated student data.
    
    Args:
        role_map: Dictionary mapping team names to Discord role IDs
        verified_role_id: Optional verified role ID to include
        
    Returns:
        Dictionary with sync statistics
    """
    stats = {"synced": 0, "skipped": 0, "errors": 0}
    
    try:
        # get all verified users
        verified_users = get_all_verified_users()
        logger.info(f"Found {len(verified_users)} verified users to check for role updates")
        
        # get all students (updated from CSV)
        all_students = get_all_students()
        students_by_email = {student['email'].lower(): student for student in all_students}
        
        for verified_user in verified_users:
            try:
                email = verified_user['email'].lower()
                discord_id = verified_user['discord_id']
                
                # find corresponding student data
                student = students_by_email.get(email)
                if not student:
                    logger.debug(f"No student data found for verified user {email}")
                    stats["skipped"] += 1
                    continue
                
                # calculate desired roles
                desired_role_ids = []
                
                # add verified role if specified
                if verified_role_id:
                    desired_role_ids.append(verified_role_id)
                
                # add team-specific roles
                for team in student.get('teams', []):
                    role_id = role_map.get(team)
                    if role_id:
                        desired_role_ids.append(role_id)

                success = update_verified_user_roles(discord_id, desired_role_ids, checked_only=False)
                
                if success:
                    logger.info(f"Updated role tracking for verified user {email} (Discord ID: {discord_id})")
                    stats["synced"] += 1
                else:
                    logger.warning(f"Failed to update role tracking for verified user {email}")
                    stats["errors"] += 1
                    
            except Exception as e:
                logger.error(f"Error syncing roles for verified user {verified_user.get('email', 'unknown')}: {e}")
                stats["errors"] += 1
                continue
        
        logger.info(f"Role sync completed. Synced: {stats['synced']}, Skipped: {stats['skipped']}, Errors: {stats['errors']}")
        return stats
        
    except Exception as e:
        logger.error(f"Error during role sync: {e}")
        stats["errors"] += 1
        return stats

def import_students_from_csv(csv_file: str, email_column: str = 'email', sync_roles: bool = True, verified_role_id: Optional[int] = None) -> Dict[str, int]:
    """
    import students from CSV file to database.
    
    Args:
        csv_file: path to CSV file
        email_column: name of the email column in CSV
        sync_roles: whether to sync roles for verified users after import
        verified_role_id: optional verified role ID for role syncing
        
    Returns:
        dict with import statistics
    """
    if not os.path.exists(csv_file):
        logger.error(f"CSV file not found: {csv_file}")
        return {"error": 1, "added": 0, "updated": 0, "skipped": 0}
    
    # setup database
    try:
        setup_database()
    except Exception as e:
        logger.error(f"Failed to setup database: {e}")
        return {"error": 1, "added": 0, "updated": 0, "skipped": 0}
    
    stats = {"error": 0, "added": 0, "updated": 0, "skipped": 0}
    
    try:
        with open(csv_file, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            
            # check if required columns exist
            required_columns = ['first_name', 'last_name', email_column]
            missing_columns = [col for col in required_columns if col not in reader.fieldnames]
            if missing_columns:
                logger.error(f"Missing required columns: {missing_columns}")
                return {"error": 1, "added": 0, "updated": 0, "skipped": 0}
            
            logger.info(f"Starting import from {csv_file}")
            logger.info(f"CSV columns: {reader.fieldnames}")
            
            # load existing emails once for efficiency
            existing_students = get_all_students()
            existing_emails = {student['email'] for student in existing_students}

            for row_num, row in enumerate(reader, start=2):  # start at 2 since header is row 1
                try:
                    # extract data from row
                    email = row[email_column].strip()
                    first_name = row['first_name'].strip()
                    last_name = row['last_name'].strip()
                    teams = row.get('teams', '').strip()
                    
                    # validate required fields
                    if not email or not first_name or not last_name:
                        logger.warning(f"Row {row_num}: Missing required data, skipping")
                        stats["skipped"] += 1
                        continue
                    
                    # validate email format
                    if not validate_email(email):
                        logger.warning(f"Row {row_num}: Invalid email format '{email}', skipping")
                        stats["skipped"] += 1
                        continue
                    
                    # parse teams
                    team_list = teams.split(':') if teams else []
                    team_list = [team.strip() for team in team_list if team.strip()]
                    
                    if email in existing_emails:
                        logger.info(f"Row {row_num}: Updating existing student {first_name} {last_name} ({email})")
                        stats["updated"] += 1
                    else:
                        logger.info(f"Row {row_num}: Adding new student {first_name} {last_name} ({email})")
                        stats["added"] += 1
                    
                    # add or update student
                    add_or_update_student(email, first_name, last_name, team_list)
                    # keep the in-memory set in sync to avoid duplicate add counts
                    existing_emails.add(email)
                    
                except Exception as e:
                    logger.error(f"Row {row_num}: Error processing row - {e}")
                    stats["error"] += 1
                    continue
            
            logger.info(f"Import completed. Added: {stats['added']}, Updated: {stats['updated']}, Skipped: {stats['skipped']}, Errors: {stats['error']}")
            
            # sync roles for verified users if requested
            if sync_roles and (stats['added'] > 0 or stats['updated'] > 0):
                logger.info("Starting role sync for verified users...")
                try:
                    role_map = load_role_mappings()
                    if role_map:
                        role_sync_stats = sync_roles_for_verified_users(role_map, verified_role_id)
                        stats['role_sync'] = role_sync_stats
                        logger.info(f"Role sync completed. Synced: {role_sync_stats['synced']}, Skipped: {role_sync_stats['skipped']}, Errors: {role_sync_stats['errors']}")
                    else:
                        logger.warning("No role mappings available, skipping role sync")
                        stats['role_sync'] = {"synced": 0, "skipped": 0, "errors": 0}
                except Exception as e:
                    logger.error(f"Error during role sync: {e}")
                    stats['role_sync'] = {"synced": 0, "skipped": 0, "errors": 1}
            else:
                stats['role_sync'] = {"synced": 0, "skipped": 0, "errors": 0}
            
            return stats
            
    except Exception as e:
        logger.error(f"Error reading CSV file: {e}")
        return {"error": 1, "added": 0, "updated": 0, "skipped": 0}

def create_sample_csv(filename: str = "students_with_email.csv"):
    """create a sample CSV file with email column"""
    sample_data = [
        ["first_name", "last_name", "email", "teams"],
        ["John", "Doe", "john.doe@cps.edu", "V25:JV26"],
        ["Jane", "Smith", "jane.smith@cps.edu", ""],
        ["Bob", "Johnson", "bob.johnson@cps.edu", "GRAD"]
    ]
    
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerows(sample_data)
    
    logger.info(f"Created sample CSV file: {filename}")

def main():
    """main function for command line usage"""
    if len(sys.argv) < 2:
        print("Usage: python import_students.py <csv_file> [email_column_name] [--no-sync-roles]")
        print("Example: python import_students.py students.csv email")
        print("         python import_students.py students.csv")
        print("         python import_students.py students.csv email --no-sync-roles")
        sys.exit(1)
    
    csv_file = sys.argv[1]
    email_column = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith('--') else 'email'
    sync_roles = '--no-sync-roles' not in sys.argv
    
    print(f"Importing students from {csv_file}...")
    if not sync_roles:
        print("Role syncing disabled (--no-sync-roles flag used)")
    
    stats = import_students_from_csv(csv_file, email_column, sync_roles=sync_roles)
    
    if stats["error"] > 0:
        print(f"Import completed with errors. Check logs for details.")
        print(f"Added: {stats['added']}, Updated: {stats['updated']}, Skipped: {stats['skipped']}, Errors: {stats['error']}")
        if 'role_sync' in stats:
            role_sync = stats['role_sync']
            print(f"Role Sync: Synced: {role_sync['synced']}, Skipped: {role_sync['skipped']}, Errors: {role_sync['errors']}")
        sys.exit(1)
    else:
        print(f"Import successful!")
        print(f"Added: {stats['added']}, Updated: {stats['updated']}, Skipped: {stats['skipped']}")
        if 'role_sync' in stats:
            role_sync = stats['role_sync']
            print(f"Role Sync: Synced: {role_sync['synced']}, Skipped: {role_sync['skipped']}, Errors: {role_sync['errors']}")
            if role_sync['synced'] > 0:
                print("Note: Role changes have been recorded in the database. Run the bot's /sync_roles command to apply changes to Discord.")

if __name__ == "__main__":
    main()
