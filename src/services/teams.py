"""
services.teams: domain service entrypoint for teams.
Re-exports from teams.services.
"""

from teams.services import create_team, join_team

__all__ = ["create_team", "join_team"]
