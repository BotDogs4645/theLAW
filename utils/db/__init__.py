"""Database module - re-exports all database functions for backward compatibility."""

from .connection import (
    DB_FILE,
    get_db_connection,
    setup_database,
)

from .verified_users import (
    is_user_verified,
    is_name_taken,
    is_email_verified,
    add_verified_user,
    get_verified_user,
    get_all_verified_users,
    update_verified_user_roles,
    delete_verified_user,
)

from .students import (
    add_or_update_student,
    get_student_by_email,
    get_student_by_name,
    get_all_students,
    delete_student,
)

from .schedules import (
    add_schedule,
    get_schedule_by_id,
    get_all_schedules,
    get_schedules_by_date_range,
    get_schedules_by_sub_team,
    update_schedule,
    delete_schedule,
    search_schedules,
    get_valid_subteams,
)

from .ai_interactions import (
    start_ai_interaction,
    complete_ai_interaction,
    log_ai_gemini_call,
    log_ai_function_call,
    log_ai_discord_step,
)

__all__ = [
    # Connection
    'DB_FILE',
    'get_db_connection',
    'setup_database',
    # Verified users
    'is_user_verified',
    'is_name_taken',
    'is_email_verified',
    'add_verified_user',
    'get_verified_user',
    'get_all_verified_users',
    'update_verified_user_roles',
    'delete_verified_user',
    # Students
    'add_or_update_student',
    'get_student_by_email',
    'get_student_by_name',
    'get_all_students',
    'delete_student',
    # Schedules
    'add_schedule',
    'get_schedule_by_id',
    'get_all_schedules',
    'get_schedules_by_date_range',
    'get_schedules_by_sub_team',
    'update_schedule',
    'delete_schedule',
    'search_schedules',
    'get_valid_subteams',
    # AI interactions
    'start_ai_interaction',
    'complete_ai_interaction',
    'log_ai_gemini_call',
    'log_ai_function_call',
    'log_ai_discord_step',
]
