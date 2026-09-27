"""
services.events: domain service entrypoint for events, tracks, and prizes.
Re-exports from events.services.
"""

from events.services import (
    create_event,
    create_track,
    create_prize,
    get_event,
    get,
)

__all__ = [
    "create_event",
    "create_track",
    "create_prize",
    "get_event",
    "get",
]
