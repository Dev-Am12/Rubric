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
)

__all__ = ["create", "update", "submit", "get", "gallery"]
