"""
services.events: domain service entrypoint for events, tracks, and prizes.
Re-exports from events.services.
"""

from events.services import (
    current_event,
    create_event,
    update_event,
    set_current_event,
    create_track,
    update_track,
    create_prize,
    update_prize,
    get_event,
    get,
)

__all__ = [
    "current_event",
    "create_event",
    "update_event",
    "set_current_event",
    "create_track",
    "update_track",
    "create_prize",
    "update_prize",
    "get_event",
    "get",
]
