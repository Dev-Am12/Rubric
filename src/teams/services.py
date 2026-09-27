"""
Service layer for teams.

Design reference:
  - SCHEMA.md §0.1 (all mutations through service layer)
  - SCHEMA.md §1.1 (Team, TeamMembership fields)
  - API.md §2 (services.teams.create, services.teams.join)
"""

import secrets

from django.db import IntegrityError

from accounts.actors import require, PermissionDenied
from accounts.models import EventMembership, EventRole
from teams.models import Team, TeamMembership


def _generate_invite_code():
    """Generate a URL-safe random invite code."""
    return secrets.token_urlsafe(16)


def create_team(actor, event, name, external_id=None, invite_code=None,
                created_by_user=None):
    """
    Create a new team for an event.

    Any registered (non-anonymous) user can create a team.
    Automatically adds the creator as a team member and ensures they
    have a PARTICIPANT EventMembership for the event.
    """
    require(actor, not actor.is_anonymous)

    user = created_by_user or actor.user

    if invite_code is None:
        invite_code = _generate_invite_code()

    team = Team.objects.create(
        event=event,
        name=name,
        invite_code=invite_code,
        external_id=external_id,
        created_by=user,
    )

    # Creator becomes a member
    TeamMembership.objects.get_or_create(team=team, user=user)

    # Ensure the creator has a PARTICIPANT membership for the event
    EventMembership.objects.get_or_create(
        event=event,
        user=user,
        role=EventRole.PARTICIPANT,
    )

    return team


def join_team(actor, team_id, code):
    """
    Join an existing team by providing the correct invite code.

    Any registered (non-anonymous) user can join a team if they provide
    the correct invite code.
    """
    require(actor, not actor.is_anonymous)

    try:
        team = Team.objects.get(id=team_id)
    except Team.DoesNotExist:
        raise ValueError("Team not found.")

    if team.invite_code != code:
        raise ValueError("Invalid invite code.")

    membership, created = TeamMembership.objects.get_or_create(
        team=team,
        user=actor.user,
    )

    if created:
        # Ensure the joiner has a PARTICIPANT membership for the event
        EventMembership.objects.get_or_create(
            event=team.event,
            user=actor.user,
            role=EventRole.PARTICIPANT,
        )

    return membership
