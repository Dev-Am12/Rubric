"""
services.teams: domain service entrypoint for teams.
Re-exports from teams.services.
"""

from teams.services import create_team, join_team, join_by_code

__all__ = ["create_team", "join_team", "join_by_code"]
