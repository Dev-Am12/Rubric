"""
Test-specific settings — uses SQLite in-memory for test speed and to avoid
needing CREATEDB privileges on the local PostgreSQL instance.

This file imports everything from the main settings and only overrides
the database backend.
"""

import os
import dj_database_url

# Capture if DATABASE_URL was explicitly passed in the environment before
# rubric.settings loads local dev variables from src/.env
_explicit_db_url = os.environ.get('DATABASE_URL')

from rubric.settings import *  # noqa: F401,F403

if _explicit_db_url:
    DATABASES = {
        'default': dj_database_url.parse(_explicit_db_url)
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        }
    }
