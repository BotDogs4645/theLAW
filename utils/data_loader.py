import csv
import json

def load_roles():
    """Loads the role map from roles.json"""
    try:
        with open("roles.json", "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"error loading roles.json: {e}")
        return {}

def load_students():
    """loads the student roster from students.csv"""
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
                    'teams': row['teams'].split(':') if row.get('teams') else []
                }
        return students
    except FileNotFoundError:
        print("error: students.csv not found.")
        return {}
    except KeyError:
        print("error: CSV must have columns: 'first_name', 'last_name', 'teams'.")
        return {}