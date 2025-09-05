import csv
import json
from utils.database import get_all_students, setup_database
from utils.logger import get_logger

logger = get_logger(__name__)

def load_roles():
    """loads the role map from roles.json"""    
    try:
        with open("roles.json", "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Error loading roles.json: {e}")
        return {}

def load_students():
    """loads the student roster from database"""
    try:
        # ensure database is set up
        setup_database()
        
        # get all students from database
        students_data = get_all_students()
        
        # convert to the format expected by the verification system
        students = {}
        for student in students_data:
            lower_full_name = student['full_name'].lower()
            students[lower_full_name] = {
                'original_name': student['full_name'],
                'teams': student['teams'],
                'email': student['email']  # include email for future use
            }
        
        logger.info(f"Loaded {len(students)} students from database")
        return students
        
    except Exception as e:
        logger.error(f"Error loading students from database: {e}")
        return {}

def load_students_from_csv_fallback():
    """fallback method to load students from CSV if database is empty"""
    students = {}
    try:
        with open("students.csv", newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                first_name = row['first_name'].strip()
                last_name = row['last_name'].strip()
                lower_full_name = f"{first_name.lower()} {last_name.lower()}"
                original_full_name = f"{first_name} {last_name}"
                students[lower_full_name] = {
                    'original_name': original_full_name,
                    'teams': row['teams'].split(':') if row.get('teams') else [],
                    'email': None  # no email in CSV fallback
                }
        logger.info(f"Loaded {len(students)} students from CSV fallback")
        return students
    except FileNotFoundError:
        logger.warning("students.csv not found for fallback")
        return {}
    except KeyError:
        logger.error("CSV must have columns: 'first_name', 'last_name', 'teams'.")
        return {}