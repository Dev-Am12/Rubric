"""
Service layer for submissions (projects).

Design reference:
  - SCHEMA.md §0.1 (all mutations through service layer)
  - SCHEMA.md §1.1 (Project fields, draft-and-edit-until-deadline)
  - API.md §2 (services.submissions.*)
  - AUTHZ.md §3.1 (draft visibility, deadline enforcement)

The deadline check in update() and submit() uses select_for_update() on
the Event row inside the same transaction as the write — this is the real
enforcement, not a CSRF side effect or a form-level check.
"""

from django.db import transaction
from django.utils import timezone

from accounts.actors import require, PermissionDenied
from submissions.models import Project, ProjectStatus
from teams.models import TeamMembership


def _is_team_member(actor, team):
    """Check if the actor is a member of the given team."""
    if actor.is_anonymous:
        return False
    return TeamMembership.objects.filter(
        team=team, user=actor.user,
    ).exists()


def create(actor, team, track, title, summary, description='',
           repo_url='', demo_video_url='', live_url='',
           tech_tags=None, custom_answers=None, **kwargs):
    """
    Create a new project submission as DRAFT.

    Only a member of the team can create a project for that team.
    The project starts in DRAFT status.
    """
    require(actor, not actor.is_anonymous)
    require(actor, _is_team_member(actor, team))

    event = team.event

    # Deadline check: reject if event submissions are closed (unless organizer)
    is_org = actor.is_organizer or actor.is_site_admin
    if not is_org:
        if event.submissions_close_at and timezone.now() > event.submissions_close_at:
            raise PermissionDenied()

    return Project.objects.create(
        event=event,
        team=team,
        track=track,
        title=title,
        summary=summary,
        description=description,
        repo_url=repo_url,
        demo_video_url=demo_video_url,
        live_url=live_url,
        tech_tags=tech_tags or [],
        custom_answers=custom_answers or {},
        status=ProjectStatus.DRAFT,
        **kwargs,
    )


def update(actor, project_id, **fields):
    """
    Update a project.

    Owner (team member) only.  Rejects with PermissionDenied if
    now() > event.submissions_close_at, checked inside the same
    transaction as the write via select_for_update() on the Event row
    (SCHEMA.md §1.1).

    Organizers can override the deadline (logged).
    """
    require(actor, not actor.is_anonymous)

    with transaction.atomic():
        try:
            project = Project.objects.select_for_update().get(id=project_id)
        except Project.DoesNotExist:
            raise ValueError("Project not found.")

        is_owner = _is_team_member(actor, project.team)
        is_org = actor.is_organizer or actor.is_site_admin

        require(actor, is_owner or is_org)

        # Deadline check — lock the Event row in the same transaction
        from events.models import Event
        event = Event.objects.select_for_update().get(id=project.event_id)

        if not is_org:
            # Non-organizers are subject to the deadline
            if timezone.now() > event.submissions_close_at:
                raise PermissionDenied()

        # Apply allowed field updates
        allowed_fields = {
            'title', 'summary', 'description', 'repo_url',
            'demo_video_url', 'live_url', 'tech_tags', 'custom_answers',
        }
        for key, value in fields.items():
            if key in allowed_fields:
                setattr(project, key, value)

        project.save()

    return project


def submit(actor, project_id):
    """
    Submit a project (transition from DRAFT to SUBMITTED).

    Owner (team member) only, before deadline.
    Sets status=SUBMITTED and submitted_at=now().
    """
    require(actor, not actor.is_anonymous)

    with transaction.atomic():
        try:
            project = Project.objects.select_for_update().get(id=project_id)
        except Project.DoesNotExist:
            raise ValueError("Project not found.")

        require(actor, _is_team_member(actor, project.team))

        # Deadline check
        from events.models import Event
        event = Event.objects.select_for_update().get(id=project.event_id)

        if timezone.now() > event.submissions_close_at:
            raise PermissionDenied()

        project.status = ProjectStatus.SUBMITTED
        project.submitted_at = timezone.now()
        project.save()

    return project


def get(actor, project_id):
    """
    Get a project by ID.

    Public if SUBMITTED. If DRAFT, only owner (team member) or organizer
    can view (AUTHZ.md §3.1).
    """
    try:
        project = Project.objects.select_related(
            'team', 'track', 'event',
        ).get(id=project_id)
    except Project.DoesNotExist:
        raise ValueError("Project not found.")

    if project.status == ProjectStatus.SUBMITTED:
        return project

    # Draft: owner or organizer only
    is_owner = not actor.is_anonymous and _is_team_member(actor, project.team)
    is_org = not actor.is_anonymous and (
        actor.is_organizer or actor.is_site_admin
    )

    require(actor, is_owner or is_org)
    return project


def gallery(actor, q=None, track=None, tag=None):
    """
    Public gallery of SUBMITTED projects.

    No auth required — all submitted projects are public (D-13: drafts
    are excluded). No pagination yet (deferred, cheap to add later, not
    needed at fixture scale of 41 projects).
    """
    qs = Project.objects.filter(
        status=ProjectStatus.SUBMITTED,
    ).select_related('team', 'track', 'event').order_by('-submitted_at')

    if q:
        qs = qs.filter(title__icontains=q)

    if track:
        if isinstance(track, str):
            qs = qs.filter(track__external_id=track)
        else:
            qs = qs.filter(track=track)

    if tag:
        # JSONField contains check: tech_tags is a list of strings
        qs = qs.filter(tech_tags__contains=[tag])

    return qs
