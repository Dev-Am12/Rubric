"""
services.submissions: domain service entrypoint for submissions/projects.
Re-exports from submissions.services.
"""

from submissions.services import (
    create,
    update,
    submit,
    get,
    gallery,
    restore_duplicate,
    detect_and_flag_duplicates,
    detect_duplicates_for_event,
)

__all__ = [
    "create",
    "update",
    "submit",
    "get",
    "gallery",
    "restore_duplicate",
    "detect_and_flag_duplicates",
    "detect_duplicates_for_event",
]
