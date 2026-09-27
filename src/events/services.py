"""
Service layer for events, tracks, and prizes.

Design reference:
  - SCHEMA.md §0.1 (all mutations through service layer)
  - SCHEMA.md §1.1 (Event, Track, Prize models)
  - SCHEMA.md §3 (app services boundary)
  - API.md §2 (services.events.* endpoints)
  - AUTHZ.md §1 (Actor/AnonymousActor policy checks via require())

Views never touch the ORM directly for these entities — they call these
service functions exclusively.
"""

from datetime import timedelta
from django.utils import timezone
from django.utils.text import slugify

from accounts.actors import require, PermissionDenied
from accounts.models import EventMembership, EventRole
from events.models import Event, Track, Prize


def create_event(
    actor,
    name=None,
    slug=None,
    submissions_close_at=None,
    submissions_open_at=None,
    voting_opens_at=None,
    voting_closes_at=None,
    external_id=None,
    **kwargs,
):
    """
    Create a new event. Organizer-only operation.

    Enforces organizer role via require(). Sets created_by to the actor's
    user and automatically adds an ORGANIZER EventMembership for the user.
    """
    require(actor, actor.is_organizer or actor.is_site_admin)

    if name is None and slug is not None:
        name = slug
    elif name is not None and slug is None:
        slug = slugify(name)
    elif name is None and slug is None:
        raise ValueError("Event name or slug is required.")

    if submissions_close_at is None:
        submissions_close_at = timezone.now() + timedelta(days=30)

    user = actor.user if not actor.is_anonymous else None

    event = Event.objects.create(
        name=name,
        slug=slug,
        submissions_close_at=submissions_close_at,
        submissions_open_at=submissions_open_at,
        voting_opens_at=voting_opens_at,
        voting_closes_at=voting_closes_at,
        external_id=external_id,
        created_by=user,
        **kwargs,
    )

    if user is not None:
        EventMembership.objects.get_or_create(
            event=event,
            user=user,
            role=EventRole.ORGANIZER,
        )

    return event


def create_track(
    actor,
    arg1=None,
    arg2=None,
    *,
    event=None,
    name=None,
    external_id=None,
    **kwargs,
):
    """
    Create a new track for an event. Organizer-only operation.

    Supports flexible calling conventions:
      - create_track(actor, event, "Track Name")
      - create_track(actor, "Track Name", event=event)
      - create_track(actor, event=event, name="Track Name")
      - create_track(actor, "Track Name")  # when actor.event is set
    """
    require(actor, actor.is_organizer or actor.is_site_admin)

    resolved_event = event
    resolved_name = name

    if arg1 is not None:
        if isinstance(arg1, Event):
            resolved_event = arg1
            if arg2 is not None:
                resolved_name = str(arg2)
        elif isinstance(arg1, str):
            if isinstance(arg2, Event):
                resolved_name = arg1
                resolved_event = arg2
            elif arg2 is not None:
                resolved_event = arg1
                resolved_name = str(arg2)
            else:
                resolved_name = arg1

    if resolved_name is None:
        raise ValueError("Track name is required.")

    if resolved_event is None:
        resolved_event = actor.event

    if isinstance(resolved_event, str):
        resolved_event = Event.objects.get(slug=resolved_event)

    if resolved_event is None:
        raise ValueError("Event is required to create a track.")

    return Track.objects.create(
        event=resolved_event,
        name=resolved_name,
        external_id=external_id,
        **kwargs,
    )


def create_prize(
    actor,
    arg1=None,
    arg2=None,
    arg3=None,
    *,
    event=None,
    rank_label=None,
    description="",
    **kwargs,
):
    """
    Create a new prize for an event. Organizer-only operation.

    Supports flexible calling conventions:
      - create_prize(actor, event, "1st", "First place prize")
      - create_prize(actor, "1st", "First place prize", event=event)
      - create_prize(actor, event=event, rank_label="1st", description="...")
      - create_prize(actor, "1st")  # when actor.event is set
    """
    require(actor, actor.is_organizer or actor.is_site_admin)

    resolved_event = event
    resolved_rank_label = rank_label
    resolved_description = description

    if arg1 is not None:
        if isinstance(arg1, Event):
            resolved_event = arg1
            if arg2 is not None:
                resolved_rank_label = str(arg2)
            if arg3 is not None:
                resolved_description = str(arg3)
        elif isinstance(arg1, str):
            if isinstance(arg2, Event):
                resolved_rank_label = arg1
                resolved_event = arg2
                if arg3 is not None:
                    resolved_description = str(arg3)
            elif arg2 is not None:
                resolved_rank_label = arg1
                resolved_description = str(arg2)
                if isinstance(arg3, Event):
                    resolved_event = arg3
            else:
                resolved_rank_label = arg1

    if resolved_rank_label is None:
        raise ValueError("Prize rank_label is required.")

    if resolved_event is None:
        resolved_event = actor.event

    if isinstance(resolved_event, str):
        resolved_event = Event.objects.get(slug=resolved_event)

    if resolved_event is None:
        raise ValueError("Event is required to create a prize.")

    return Prize.objects.create(
        event=resolved_event,
        rank_label=resolved_rank_label,
        description=resolved_description,
        **kwargs,
    )


def get_event(slug_or_actor, slug=None):
    """
    Public read of an event by slug.
    No authentication or authorization required.
    """
    if slug is not None:
        target_slug = slug
    elif isinstance(slug_or_actor, str):
        target_slug = slug_or_actor
    else:
        target_slug = getattr(slug_or_actor, 'slug', str(slug_or_actor))

    return Event.objects.get(slug=target_slug)


# Alias per API.md §2 table
get = get_event
