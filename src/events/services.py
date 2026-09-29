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

from datetime import datetime, timedelta
from django.utils import timezone
from django.utils.text import slugify

from accounts.actors import require, PermissionDenied
from accounts.models import EventMembership, EventRole
from events.models import Event, Track, Prize, VotingAccess


def current_event():
    """
    Return the single current active event, or None if no event exists.
    Queries for the event with is_current=True. If no event is marked current
    (e.g. in synthetic unit tests), falls back to Event.objects.first().
    """
    evt = Event.objects.filter(is_current=True).first()
    if evt is not None:
        return evt
    return Event.objects.first()


def _check_datetime(dt, field_name):
    if dt is None:
        return None
    if isinstance(dt, str):
        val = dt.strip()
        if not val:
            return None
        if val.endswith('Z'):
            val = val[:-1] + '+00:00'
        try:
            dt = datetime.fromisoformat(val)
        except ValueError as exc:
            raise ValueError(f"Invalid datetime format for {field_name}: {exc}")
    if not isinstance(dt, datetime):
        raise ValueError(f"{field_name} must be a datetime or ISO string.")
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError(f"Naive datetimes are not allowed for {field_name}; datetimes must be timezone-aware.")
    return dt


def _validate_dates(submissions_open_at, submissions_close_at, voting_opens_at, voting_closes_at):
    if submissions_open_at and submissions_close_at:
        if submissions_close_at <= submissions_open_at:
            raise ValueError("Submissions close date must be after submissions open date.")
    if voting_opens_at and voting_closes_at:
        if voting_closes_at <= voting_opens_at:
            raise ValueError("Voting close date must be after voting open date.")


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
    Creating an event NEVER auto-switches is_current.
    """
    require(actor, actor.is_organizer or actor.is_site_admin)

    if name is None and slug is not None:
        name = slug
    elif name is not None and slug is None:
        slug = slugify(name)
    elif name is None and slug is None:
        raise ValueError("Event name or slug is required.")

    submissions_open_at = _check_datetime(submissions_open_at, 'submissions_open_at')
    submissions_close_at = _check_datetime(submissions_close_at, 'submissions_close_at')
    voting_opens_at = _check_datetime(voting_opens_at, 'voting_opens_at')
    voting_closes_at = _check_datetime(voting_closes_at, 'voting_closes_at')

    if submissions_close_at is None:
        submissions_close_at = timezone.now() + timedelta(days=30)

    _validate_dates(submissions_open_at, submissions_close_at, voting_opens_at, voting_closes_at)

    user = actor.user if not actor.is_anonymous else None

    # Never auto-switch on creation
    is_current = kwargs.pop('is_current', False)

    from django.db import transaction
    from services import audit

    with transaction.atomic():
        event = Event.objects.create(
            name=name,
            slug=slug,
            submissions_close_at=submissions_close_at,
            submissions_open_at=submissions_open_at,
            voting_opens_at=voting_opens_at,
            voting_closes_at=voting_closes_at,
            external_id=external_id,
            is_current=is_current,
            created_by=user,
            **kwargs,
        )

        if user is not None:
            EventMembership.objects.get_or_create(
                event=event,
                user=user,
                role=EventRole.ORGANIZER,
            )

        audit.record(actor, 'event.create', event, {
            'slug': event.slug,
            'name': event.name,
            'submissions_close_at': event.submissions_close_at.isoformat() if event.submissions_close_at else None,
            'voting_access': event.voting_access,
            'votes_per_voter': event.votes_per_voter,
            'is_current': event.is_current,
        })

    return event


def update_event(
    actor,
    event_or_id,
    name=None,
    slug=None,
    submissions_open_at=...,
    submissions_close_at=...,
    voting_opens_at=...,
    voting_closes_at=...,
    voting_access=...,
    votes_per_voter=...,
):
    """
    Update an event's name and dates. Organizer-only.
    All changes are audit-logged with before/after state.
    """
    require(actor, actor.is_organizer or actor.is_site_admin)
    if isinstance(event_or_id, Event):
        event = event_or_id
    elif isinstance(event_or_id, int):
        event = Event.objects.get(pk=event_or_id)
    else:
        event = Event.objects.get(slug=str(event_or_id))

    before = {
        'name': event.name,
        'slug': event.slug,
        'submissions_open_at': event.submissions_open_at.isoformat() if event.submissions_open_at else None,
        'submissions_close_at': event.submissions_close_at.isoformat() if event.submissions_close_at else None,
        'voting_opens_at': event.voting_opens_at.isoformat() if event.voting_opens_at else None,
        'voting_closes_at': event.voting_closes_at.isoformat() if event.voting_closes_at else None,
        'voting_access': event.voting_access,
        'votes_per_voter': event.votes_per_voter,
    }

    new_sub_open = event.submissions_open_at if submissions_open_at is Ellipsis else _check_datetime(submissions_open_at, 'submissions_open_at')
    new_sub_close = event.submissions_close_at if submissions_close_at is Ellipsis else _check_datetime(submissions_close_at, 'submissions_close_at')
    new_vote_open = event.voting_opens_at if voting_opens_at is Ellipsis else _check_datetime(voting_opens_at, 'voting_opens_at')
    new_vote_close = event.voting_closes_at if voting_closes_at is Ellipsis else _check_datetime(voting_closes_at, 'voting_closes_at')
    new_voting_access = event.voting_access if voting_access is Ellipsis else str(voting_access).upper()
    new_vote_budget = event.votes_per_voter if votes_per_voter is Ellipsis else votes_per_voter

    if new_voting_access not in VotingAccess.values:
        raise ValueError('voting_access must be OPEN or AUTH.')
    if new_vote_budget is not None:
        if isinstance(new_vote_budget, bool):
            raise ValueError('votes_per_voter must be a non-negative integer or blank.')
        if isinstance(new_vote_budget, str):
            normalized_budget = new_vote_budget.strip()
            if not normalized_budget.isdecimal():
                raise ValueError('votes_per_voter must be a non-negative integer or blank.')
            new_vote_budget = int(normalized_budget)
        elif not isinstance(new_vote_budget, int):
            raise ValueError('votes_per_voter must be a non-negative integer or blank.')
        if new_vote_budget < 0:
            raise ValueError('votes_per_voter must be a non-negative integer or blank.')

    if new_sub_close is None:
        raise ValueError("submissions_close_at cannot be None.")

    _validate_dates(new_sub_open, new_sub_close, new_vote_open, new_vote_close)

    from django.db import transaction
    from services import audit

    with transaction.atomic():
        if name is not None:
            event.name = name
        if slug is not None:
            event.slug = slug
        if submissions_open_at is not Ellipsis:
            event.submissions_open_at = new_sub_open
        if submissions_close_at is not Ellipsis:
            event.submissions_close_at = new_sub_close
        if voting_opens_at is not Ellipsis:
            event.voting_opens_at = new_vote_open
        if voting_closes_at is not Ellipsis:
            event.voting_closes_at = new_vote_close
        if voting_access is not Ellipsis:
            event.voting_access = new_voting_access
        if votes_per_voter is not Ellipsis:
            event.votes_per_voter = new_vote_budget
        event.save()

        after = {
            'name': event.name,
            'slug': event.slug,
            'submissions_open_at': event.submissions_open_at.isoformat() if event.submissions_open_at else None,
            'submissions_close_at': event.submissions_close_at.isoformat() if event.submissions_close_at else None,
            'voting_opens_at': event.voting_opens_at.isoformat() if event.voting_opens_at else None,
            'voting_closes_at': event.voting_closes_at.isoformat() if event.voting_closes_at else None,
            'voting_access': event.voting_access,
            'votes_per_voter': event.votes_per_voter,
        }

        audit.record(actor, 'event.update', event, {
            'before': before,
            'after': after,
        })

    return event


def set_current_event(actor, event_or_id):
    """
    Explicitly set an event as the single current event. Organizer-only.
    All changes are audit-logged with before/after state.
    """
    require(actor, actor.is_organizer or actor.is_site_admin)
    if isinstance(event_or_id, Event):
        target = event_or_id
    elif isinstance(event_or_id, int):
        target = Event.objects.get(pk=event_or_id)
    else:
        target = Event.objects.get(slug=str(event_or_id))

    from django.db import transaction
    from services import audit

    with transaction.atomic():
        prev_current = Event.objects.select_for_update().filter(is_current=True).first()
        prev_slug = prev_current.slug if prev_current else None

        if prev_current and prev_current.pk != target.pk:
            prev_current.is_current = False
            prev_current.save(update_fields=['is_current'])

        target.is_current = True
        target.save(update_fields=['is_current'])

        audit.record(actor, 'event.make_current', target, {
            'before': prev_slug,
            'after': target.slug,
        })

    return target


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

    from django.db import transaction
    from services import audit

    with transaction.atomic():
        track = Track.objects.create(
            event=resolved_event,
            name=resolved_name,
            external_id=external_id,
            **kwargs,
        )
        audit.record(actor, 'track.create', track, {
            'event_slug': track.event.slug,
            'name': track.name,
            'external_id': track.external_id,
        })

    return track


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

    from django.db import transaction
    from services import audit

    with transaction.atomic():
        prize = Prize.objects.create(
            event=resolved_event,
            rank_label=resolved_rank_label,
            description=resolved_description,
            **kwargs,
        )
        audit.record(actor, 'prize.create', prize, {
            'event_slug': prize.event.slug,
            'rank_label': prize.rank_label,
        })

    return prize


def update_track(actor, track_or_id, name=None, external_id=Ellipsis):
    """
    Update a track. Organizer-only operation.
    All changes are audit-logged with before/after state.
    """
    require(actor, actor.is_organizer or actor.is_site_admin)
    if isinstance(track_or_id, Track):
        track = track_or_id
    else:
        track = Track.objects.get(pk=track_or_id)

    before = {
        'name': track.name,
        'external_id': track.external_id,
    }

    from django.db import transaction
    from services import audit

    with transaction.atomic():
        if name is not None:
            track.name = name
        if external_id is not Ellipsis:
            track.external_id = external_id
        track.save()

        after = {
            'name': track.name,
            'external_id': track.external_id,
        }

        audit.record(actor, 'track.update', track, {
            'event_slug': track.event.slug,
            'before': before,
            'after': after,
        })

    return track


def update_prize(actor, prize_or_id, rank_label=None, description=None):
    """
    Update a prize. Organizer-only operation.
    All changes are audit-logged with before/after state.
    """
    require(actor, actor.is_organizer or actor.is_site_admin)
    if isinstance(prize_or_id, Prize):
        prize = prize_or_id
    else:
        prize = Prize.objects.get(pk=prize_or_id)

    before = {
        'rank_label': prize.rank_label,
        'description': prize.description,
    }

    from django.db import transaction
    from services import audit

    with transaction.atomic():
        if rank_label is not None:
            prize.rank_label = rank_label
        if description is not None:
            prize.description = description
        prize.save()

        after = {
            'rank_label': prize.rank_label,
            'description': prize.description,
        }

        audit.record(actor, 'prize.update', prize, {
            'event_slug': prize.event.slug,
            'before': before,
            'after': after,
        })

    return prize


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
