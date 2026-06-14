"""
canary_db.py  —  compatibility shim
=====================================
Re-exports everything from database.canary_db so that any legacy imports
like `import canary_db` or `from canary_db import ...` keep working.
"""
from database.canary_db import (   # noqa: F401
    init_db,
    get_db_path,
    get_connection,
    get_user_count,
    get_user,
    get_all_users,
    upsert_user,
    update_preferences,
    get_preferences,
    delete_user,
    list_enrolled,
)
