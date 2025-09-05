#!/usr/bin/env python3
"""
Utility to import student data from CSV to database.
Supports email as unique key and updates existing records.
"""

import csv
import sys
import os
import re
from typing import List, Dict, Optional

# add the parent directory to the path so we can import utils
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import setup_database, add_or_update_student, get_all_students
from utils.logger import get_logger

logger = get_logger(__name__)

def validate_email(email: str) -> bool:
    """validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def import_students_from_csv(csv_file: str, email_column: str = 'email') -> Dict[str, int]:
    """
    import students from CSV file to database.
    
    Args:
        csv_file: path to CSV file
        email_column: name of the email column in CSV
        
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
                    
                    # check if student already exists
                    existing_students = get_all_students()
                    existing_emails = {student['email'] for student in existing_students}
                    
                    if email in existing_emails:
                        logger.info(f"Row {row_num}: Updating existing student {first_name} {last_name} ({email})")
                        stats["updated"] += 1
                    else:
                        logger.info(f"Row {row_num}: Adding new student {first_name} {last_name} ({email})")
                        stats["added"] += 1
                    
                    # add or update student
                    add_or_update_student(email, first_name, last_name, team_list)
                    
                except Exception as e:
                    logger.error(f"Row {row_num}: Error processing row - {e}")
                    stats["error"] += 1
                    continue
            
            logger.info(f"Import completed. Added: {stats['added']}, Updated: {stats['updated']}, Skipped: {stats['skipped']}, Errors: {stats['error']}")
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
        print("Usage: python import_students.py <csv_file> [email_column_name]")
        print("Example: python import_students.py students.csv email")
        print("         python import_students.py students.csv")
        sys.exit(1)
    
    csv_file = sys.argv[1]
    email_column = sys.argv[2] if len(sys.argv) > 2 else 'email'
    
    print(f"Importing students from {csv_file}...")
    stats = import_students_from_csv(csv_file, email_column)
    
    if stats["error"] > 0:
        print(f"Import completed with errors. Check logs for details.")
        print(f"Added: {stats['added']}, Updated: {stats['updated']}, Skipped: {stats['skipped']}, Errors: {stats['error']}")
        sys.exit(1)
    else:
        print(f"Import successful!")
        print(f"Added: {stats['added']}, Updated: {stats['updated']}, Skipped: {stats['skipped']}")

if __name__ == "__main__":
    main()
