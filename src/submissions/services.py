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

import difflib
import logging
import re

from django.db import transaction
from django.utils import timezone

from accounts.actors import require, require_event_role, PermissionDenied
from accounts.models import EventRole
from submissions.models import Project, ProjectStatus
from submissions.url_validation import URL_FIELDS, validate_external_url
from teams.models import Team, TeamMembership

logger = logging.getLogger(__name__)


def _is_event_organizer(actor, event):
    try:
        require_event_role(actor, event, EventRole.ORGANIZER)
    except PermissionDenied:
        return False
    return True


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

    repo_url = validate_external_url('repo_url', repo_url)
    demo_video_url = validate_external_url('demo_video_url', demo_video_url)
    live_url = validate_external_url('live_url', live_url)

    event = team.event

    # Deadline check: reject if event submissions are closed (unless organizer)
    is_org = _is_event_organizer(actor, event)
    if not is_org:
        if event.submissions_close_at and timezone.now() > event.submissions_close_at:
            raise PermissionDenied()

    from services import audit

    with transaction.atomic():
        project = Project.objects.create(
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
        audit.record(actor, 'submission.create', project, {
            'team_id': team.id,
            'track_id': track.id if track else None,
            'title': project.title,
            'status': project.status,
        })

    return project


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

    from services import audit

    with transaction.atomic():
        try:
            project = Project.objects.select_for_update().get(id=project_id)
        except Project.DoesNotExist:
            raise ValueError("Project not found.")

        is_owner = _is_team_member(actor, project.team)
        is_org = _is_event_organizer(actor, project.event)

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
        updated_keys = []
        for key, value in fields.items():
            if key in allowed_fields:
                if key in URL_FIELDS:
                    value = validate_external_url(key, value)
                setattr(project, key, value)
                updated_keys.append(key)

        project.save()

        audit.record(actor, 'submission.update', project, {
            'updated_fields': sorted(updated_keys),
            'title': project.title,
        })

    return project


def are_titles_near_identical(title_a, title_b, threshold=0.70):
    """
    Check if two titles are identical or near-identical per NORMALIZATION.md D-02.
    Collapses whitespace and lowercases before comparison.
    Returns (is_match, similarity_ratio).
    """
    norm_a = ' '.join((title_a or '').lower().split())
    norm_b = ' '.join((title_b or '').lower().split())

    if not norm_a or not norm_b:
        return False, 0.0

    if norm_a == norm_b:
        return True, 1.0

    ratio = difflib.SequenceMatcher(None, norm_a, norm_b).ratio()
    if ratio >= threshold:
        return True, ratio

    # Check with punctuation stripped
    clean_a = re.sub(r'[^\w\s]', '', norm_a).strip()
    clean_b = re.sub(r'[^\w\s]', '', norm_b).strip()
    if clean_a == clean_b:
        return True, 1.0

    clean_ratio = difflib.SequenceMatcher(None, clean_a, clean_b).ratio()
    if clean_ratio >= threshold:
        return True, clean_ratio

    # Prefix match (e.g. "Project Nebula" and "Project Nebula (Final Version)")
    if clean_a.startswith(clean_b) or clean_b.startswith(clean_a):
        shorter = min(len(clean_a), len(clean_b))
        if shorter >= 4:
            return True, max(ratio, clean_ratio)

    # Word subset match for multi-word titles
    words_a = set(clean_a.split())
    words_b = set(clean_b.split())
    if words_a and words_b and min(len(words_a), len(words_b)) >= 2:
        if words_a.issubset(words_b) or words_b.issubset(words_a):
            return True, max(ratio, clean_ratio)

    return False, ratio


def _format_time_gap(t1, t2):
    """Format the time difference between two timestamps in a human-readable way."""
    if not t1 or not t2:
        return "recently"
    diff = abs((t2 - t1).total_seconds())
    hours = int(diff // 3600)
    minutes = int((diff % 3600) // 60)
    if hours > 0 and minutes > 0:
        return f"~{hours}h {minutes}m"
    elif hours > 0:
        return f"~{hours}h"
    elif minutes > 0:
        return f"~{minutes}m"
    else:
        return f"~{int(diff)}s"


def detect_and_flag_duplicates(project):
    """
    General duplicate-submission detector per NORMALIZATION.md D-02:
    Checks for an existing SUBMITTED project by the same team with a near-identical
    title, submitted in the same event.

    On a match:
      - The EARLIER submission flags itself against the LATER one:
        earlier.is_duplicate_of = later
      - The LATER submission is canonical:
        later.is_duplicate_of = None
      - Fill duplicate_flag_reason with actual reason found:
        (team, title similarity, time gap)
      - Log the action with audit.record('duplicate-detection policy v1', ...).

    Returns the flagged earlier project if a duplicate was detected, or None.
    """
    if project.status != ProjectStatus.SUBMITTED:
        return None

    if getattr(project, 'duplicate_override', False):
        return None

    candidates = Project.objects.filter(
        team_id=project.team_id,
        event_id=project.event_id,
        status=ProjectStatus.SUBMITTED,
    ).exclude(id=project.id)

    from services import audit

    for candidate in candidates:
        if getattr(candidate, 'duplicate_override', False):
            continue

        is_match, similarity = are_titles_near_identical(project.title, candidate.title)
        if is_match:
            t_proj = project.submitted_at or project.created_at
            t_cand = candidate.submitted_at or candidate.created_at

            if t_proj < t_cand or (t_proj == t_cand and project.id < candidate.id):
                earlier, later = project, candidate
            else:
                earlier, later = candidate, project

            if getattr(earlier, 'duplicate_override', False):
                continue

            if earlier.is_duplicate_of_id == later.pk:
                return earlier

            with transaction.atomic():
                time_str = _format_time_gap(earlier.submitted_at, later.submitted_at)
                team_label = earlier.team.external_id or earlier.team.name

                earlier.is_duplicate_of = later
                earlier.duplicate_flag_reason = (
                    f"Same team ({team_label}), near-identical title "
                    f"({similarity:.0%} match), submitted {time_str} apart. "
                    f"Earlier submission flagged against later canonical one per NORMALIZATION.md D-02."
                )
                earlier.save(update_fields=['is_duplicate_of', 'duplicate_flag_reason'])

                later.is_duplicate_of = None
                later.duplicate_flag_reason = None
                later.save(update_fields=['is_duplicate_of', 'duplicate_flag_reason'])

                audit.record(
                    actor="duplicate-detection policy v1",
                    action="duplicate.flag",
                    target=earlier,
                    payload={
                        "earlier_id": earlier.pk,
                        "earlier_external_id": earlier.external_id,
                        "canonical_id": later.pk,
                        "canonical_external_id": later.external_id,
                        "reason": earlier.duplicate_flag_reason,
                        "similarity": round(similarity, 4),
                    },
                )

            logger.info(
                "Duplicate detected per D-02: %s flagged as duplicate of %s (%s)",
                earlier.external_id or f"Project#{earlier.id}",
                later.external_id or f"Project#{later.id}",
                earlier.duplicate_flag_reason,
            )
            return earlier

    return None


def detect_duplicates_for_event(event):
    """
    Scan all submitted projects in an event for duplicates per D-02.
    Processes projects in chronological order per team.
    Returns list of flagged (earlier) projects.
    """
    teams = Team.objects.filter(event=event)
    flagged = []
    for team in teams:
        projects = list(
            Project.objects.filter(
                team=team,
                event=event,
                status=ProjectStatus.SUBMITTED,
            ).order_by('submitted_at', 'id')
        )
        for p in projects:
            result = detect_and_flag_duplicates(p)
            if result and result not in flagged:
                flagged.append(result)
    return flagged


def submit(actor, project_id):
    """
    Submit a project (transition from DRAFT to SUBMITTED).

    Owner (team member) only, before deadline.
    Sets status=SUBMITTED and submitted_at=now().
    Runs duplicate detection per NORMALIZATION.md D-02.
    """
    require(actor, not actor.is_anonymous)

    from services import audit

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

        audit.record(actor, 'submission.submit', project, {
            'team_id': project.team_id,
            'submitted_at': project.submitted_at.isoformat(),
            'title': project.title,
        })

        # Run general duplicate detection per NORMALIZATION.md D-02
        detect_and_flag_duplicates(project)

    return project


def restore_duplicate(actor, project_id):
    """
    Restore a duplicate submission (organizer-only).
    Clears is_duplicate_of and sets duplicate_override=True so the detector
    never re-flags it on submit() or seed_fixtures re-runs.
    Logs an audit entry.
    """
    require(actor, not actor.is_anonymous)

    from services import audit

    with transaction.atomic():
        try:
            if isinstance(project_id, int) or (isinstance(project_id, str) and project_id.isdigit()):
                project = Project.objects.select_for_update().get(id=int(project_id))
            else:
                project = Project.objects.select_for_update().get(external_id=str(project_id))
        except Project.DoesNotExist:
            raise ValueError(f"Project not found: {project_id}")

        require_event_role(actor, project.event, EventRole.ORGANIZER)

        project.is_duplicate_of = None
        project.duplicate_override = True
        project.duplicate_flag_reason = "Duplicate flag overridden and restored by organizer"
        project.save(update_fields=['is_duplicate_of', 'duplicate_override', 'duplicate_flag_reason'])

        audit.record(
            actor=actor,
            action='duplicate.restore',
            target=project,
            payload={
                'project_id': project.pk,
                'external_id': project.external_id,
                'title': project.title,
            },
        )

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
    is_org = _is_event_organizer(actor, project.event)

    require(actor, is_owner or is_org)
    return project


def gallery(actor, q=None, track=None, tag=None):
    """
    Public gallery of SUBMITTED projects.

    No auth required — all submitted projects are public (D-13: drafts
    are excluded). No pagination yet (deferred, cheap to add later, not
    needed at fixture scale of 41 projects).
    """
    target_event = getattr(actor, 'event', None)
    if target_event is None:
        from events.services import current_event
        target_event = current_event()

    qs = Project.objects.filter(
        status=ProjectStatus.SUBMITTED,
        is_duplicate_of__isnull=True,
    )
    if target_event is not None:
        qs = qs.filter(event=target_event)

    qs = qs.select_related('team', 'track', 'event').order_by('-submitted_at')

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
