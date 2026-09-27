"""
Test-specific settings — uses SQLite in-memory for test speed and to avoid
needing CREATEDB privileges on the local PostgreSQL instance.

This file imports everything from the main settings and only overrides
the database backend.
"""

from rubric.settings import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}
