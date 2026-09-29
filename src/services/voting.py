"""Public voting rules, identity handling, moderation, and result gating."""

from contextlib import nullcontext
from datetime import timedelta
import hashlib
import hmac
import threading

from django.db import IntegrityError, connections, transaction
from django.db.models import Count
from django.utils import timezone

from accounts.actors import PermissionDenied, require
from accounts.models import EventMembership, EventRole
from events.models import Event, VotingAccess
from submissions.models import Project, ProjectStatus
from voting.models import Comment, Vote, VoteAttempt, VoteAttemptOutcome, VoteMode


RATE_LIMIT_ATTEMPTS = 5
RATE_LIMIT_WINDOW = timedelta(minutes=1)
COMMENT_MAX_LENGTH = 2000

_sqlite_locks = {}
_sqlite_locks_guard = threading.Lock()


def _event(value):
    if isinstance(value, Event):
        return value
    try:
        return Event.objects.get(slug=str(value))
    except Event.DoesNotExist:
        raise ValueError('Event not found.')


def _sqlite_event_mutex(event_id):
    if connections['default'].vendor != 'sqlite':
        return nullcontext()
    with _sqlite_locks_guard:
        lock = _sqlite_locks.setdefault(event_id, threading.RLock())
    return lock


def _event_row_for_update(event_id):
    return Event.objects.select_for_update().get(pk=event_id)


def _window_open(event, at=None):
    at = at or timezone.now()
    return bool(
        event.voting_opens_at is not None
        and at >= event.voting_opens_at
        and (event.voting_closes_at is None or at < event.voting_closes_at)
    )


def voting_is_open(event, at=None):
    return _window_open(_event(event), at)


def _closed_for_public_results(event, at=None):
    at = at or timezone.now()
    return event.voting_closes_at is not None and at > event.voting_closes_at


def _mode(event):
    return VoteMode(event.voting_access)


def _organizer_for(actor, event):
    if actor.is_anonymous:
        return False
    if actor.is_site_admin:
        return True
    if getattr(getattr(actor, 'event', None), 'pk', None) == event.pk:
        return actor.is_organizer
    return EventMembership.objects.filter(
        user=actor.user, event=event, role=EventRole.ORGANIZER,
    ).exists()


def _require_voter(actor, event):
    if _organizer_for(actor, event):
        raise PermissionDenied
    if event.voting_access == VotingAccess.AUTH and actor.is_anonymous:
        raise PermissionDenied


def _fingerprint(actor, event, *, ip=None, user_agent=None, fingerprint=None):
    if fingerprint is not None:
        value = str(fingerprint).strip()
        if not value:
            raise ValueError('fingerprint must not be empty')
        return value
    if event.voting_access == VotingAccess.AUTH:
        if actor.is_anonymous or getattr(actor.user, 'pk', None) is None:
            raise PermissionDenied
        return str(actor.user.pk)

    # The event's random seed is also the per-event secret salt for OPEN identities.
    # Deliberately use only REMOTE_ADDR, supplied by the view; X-Forwarded-For is untrusted.
    identity = f'{ip or ""}\0{user_agent or ""}'.encode('utf-8')
    return hmac.new(event.voting_seed.encode('utf-8'), identity, hashlib.sha256).hexdigest()


def _audit_fingerprint(fingerprint):
    return hashlib.sha256(fingerprint.encode('utf-8')).hexdigest()[:16]


def _record_attempt(event, project, mode, fingerprint, outcome, *, at=None):
    return VoteAttempt.objects.create(
        event=event,
        project=project,
        mode=mode,
        voter_fingerprint=fingerprint,
        outcome=outcome,
        created_at=at or timezone.now(),
    )


def _attempt_count(event, project, mode, fingerprint, at):
    return VoteAttempt.objects.filter(
        event=event,
        mode=mode,
        voter_fingerprint=fingerprint,
        created_at__gte=at - RATE_LIMIT_WINDOW,
    ).count()


def eligible_projects(event):
    event = _event(event)
    return Project.objects.filter(
        event=event,
        status=ProjectStatus.SUBMITTED,
        is_duplicate_of__isnull=True,
    ).select_related('track').order_by('pk')


def get_ballot(actor, event, *, ip=None, user_agent=None, fingerprint=None):
    event = _event(event)
    if event.voting_access == VotingAccess.AUTH and actor.is_anonymous:
        raise PermissionDenied
    voter_fingerprint = _fingerprint(
        actor, event, ip=ip, user_agent=user_agent, fingerprint=fingerprint,
    )
    mode = _mode(event)
    own_votes = list(Vote.objects.filter(
        event=event,
        mode=mode,
        voter_fingerprint=voter_fingerprint,
    ).select_related('project').order_by('project_id'))
    own_project_ids = {vote.project_id for vote in own_votes}
    projects = list(eligible_projects(event))

    # V-03: stable HMAC order for the same voter/event, independent of refresh or DB order.
    key = (event.voting_seed + voter_fingerprint).encode('utf-8')
    projects.sort(key=lambda project: (
        hmac.new(key, str(project.pk).encode('ascii'), hashlib.sha256).digest(),
        project.pk,
    ))
    budget = event.votes_per_voter
    remaining = None if budget is None else max(0, budget - len(own_votes))
    now = timezone.now()
    if event.voting_closes_at and now >= event.voting_closes_at:
        state = 'closed'
    elif not event.voting_opens_at or now < event.voting_opens_at:
        state = 'not_started'
    else:
        state = 'open'
    can_vote = not _organizer_for(actor, event)
    return {
        'event': event,
        'mode': mode,
        'projects': projects,
        'cast_votes': own_votes,
        'cast_project_ids': own_project_ids,
        'vote_budget': budget,
        'remaining_budget': remaining,
        'voting_open': state == 'open',
        'voting_state': state,
        'can_vote': can_vote,
    }


def cast(actor, event, project, *, ip=None, user_agent=None, fingerprint=None):
    event = _event(event)
    project_id = project.pk if isinstance(project, Project) else int(project)
    with _sqlite_event_mutex(event.pk):
        with transaction.atomic():
            event = _event_row_for_update(event.pk)
            _require_voter(actor, event)
            mode = _mode(event)
            voter_fingerprint = _fingerprint(
                actor, event, ip=ip, user_agent=user_agent, fingerprint=fingerprint,
            )
            try:
                project = Project.objects.select_for_update().get(
                    pk=project_id,
                    event=event,
                    status=ProjectStatus.SUBMITTED,
                    is_duplicate_of__isnull=True,
                )
            except Project.DoesNotExist:
                raise PermissionDenied

            now = timezone.now()
            if not _window_open(event, now):
                return _record_attempt(
                    event, project, mode, voter_fingerprint,
                    VoteAttemptOutcome.REJECTED_CLOSED, at=now,
                )

            if _attempt_count(event, project, mode, voter_fingerprint, now) >= RATE_LIMIT_ATTEMPTS:
                return _record_attempt(
                    event, project, mode, voter_fingerprint,
                    VoteAttemptOutcome.REJECTED_RATE_LIMIT, at=now,
                )

            if event.votes_per_voter is not None:
                used = Vote.objects.filter(
                    event=event, mode=mode, voter_fingerprint=voter_fingerprint,
                ).count()
                if used >= event.votes_per_voter:
                    return _record_attempt(
                        event, project, mode, voter_fingerprint,
                        VoteAttemptOutcome.REJECTED_BUDGET, at=now,
                    )

            try:
                # The nested atomic block is a savepoint so an IntegrityError
                # leaves the outer transaction usable for its rejected attempt.
                with transaction.atomic():
                    vote = Vote.objects.create(
                        event=event,
                        project=project,
                        mode=mode,
                        voter_fingerprint=voter_fingerprint,
                        weight=1,
                        attempt=None,
                        created_at=now,
                    )
            except IntegrityError:
                return _record_attempt(
                    event, project, mode, voter_fingerprint,
                    VoteAttemptOutcome.REJECTED_DUPLICATE, at=now,
                )

            attempt = _record_attempt(
                event, project, mode, voter_fingerprint,
                VoteAttemptOutcome.ACCEPTED, at=now,
            )
            vote.attempt = attempt
            vote.save(update_fields=['attempt'])

            from services import audit
            audit.record(actor, 'voting.vote_cast', vote, {
                'event_id': event.pk,
                'project_id': project.pk,
                'mode': mode,
                'voter_fingerprint_hash': _audit_fingerprint(voter_fingerprint),
            })
            return attempt


def withdraw(actor, event, project, *, ip=None, user_agent=None, fingerprint=None):
    event = _event(event)
    project_id = project.pk if isinstance(project, Project) else int(project)
    with _sqlite_event_mutex(event.pk):
        with transaction.atomic():
            event = _event_row_for_update(event.pk)
            _require_voter(actor, event)
            mode = _mode(event)
            voter_fingerprint = _fingerprint(
                actor, event, ip=ip, user_agent=user_agent, fingerprint=fingerprint,
            )
            now = timezone.now()
            if not _window_open(event, now):
                try:
                    project = Project.objects.get(pk=project_id, event=event)
                except Project.DoesNotExist:
                    raise ValueError('Project not found.')
                return _record_attempt(
                    event, project, mode, voter_fingerprint,
                    VoteAttemptOutcome.REJECTED_CLOSED, at=now,
                )
            try:
                vote = Vote.objects.select_for_update().select_related('project').get(
                    event=event,
                    project_id=project_id,
                    mode=mode,
                    voter_fingerprint=voter_fingerprint,
                )
            except Vote.DoesNotExist:
                raise ValueError('No active vote to withdraw.')
            project = vote.project
            vote.delete()
            attempt = _record_attempt(
                event, project, mode, voter_fingerprint,
                VoteAttemptOutcome.WITHDRAWN, at=now,
            )
            from services import audit
            audit.record(actor, 'voting.vote_withdrawn', project, {
                'event_id': event.pk,
                'project_id': project.pk,
                'mode': mode,
                'voter_fingerprint_hash': _audit_fingerprint(voter_fingerprint),
            })
            return attempt


def get_results(actor, event):
    event = _event(event)
    if not _organizer_for(actor, event) and not _closed_for_public_results(event):
        raise PermissionDenied
    counts = dict(
        Vote.objects.filter(event=event)
        .values('project_id').annotate(total=Count('id'))
        .values_list('project_id', 'total')
    )
    results = [
        {'project': project, 'vote_count': counts.get(project.pk, 0)}
        for project in eligible_projects(event)
    ]
    results.sort(key=lambda row: (-row['vote_count'], row['project'].pk))
    return {'event': event, 'results': results}


def _comment_target(project_id):
    try:
        return Project.objects.select_related('event').get(pk=project_id)
    except Project.DoesNotExist:
        raise ValueError('Project not found.')


def comment(actor, project, body, *, ip=None, user_agent=None, fingerprint=None):
    project_id = project.pk if isinstance(project, Project) else int(project)
    initial_project = _comment_target(project_id)
    event_id = initial_project.event_id
    body = str(body or '').strip()
    if not body:
        raise ValueError('Comment cannot be empty.')
    if len(body) > COMMENT_MAX_LENGTH:
        raise ValueError(f'Comment must be at most {COMMENT_MAX_LENGTH} characters.')

    with _sqlite_event_mutex(event_id):
        with transaction.atomic():
            event = _event_row_for_update(event_id)
            _require_voter(actor, event)
            mode = _mode(event)
            voter_fingerprint = _fingerprint(
                actor, event, ip=ip, user_agent=user_agent, fingerprint=fingerprint,
            )
            try:
                project = Project.objects.select_for_update().get(
                    pk=project_id,
                    event=event,
                    status=ProjectStatus.SUBMITTED,
                    is_duplicate_of__isnull=True,
                )
            except Project.DoesNotExist:
                raise PermissionDenied
            now = timezone.now()
            if not _window_open(event, now):
                return _record_attempt(
                    event, project, mode, voter_fingerprint,
                    VoteAttemptOutcome.REJECTED_CLOSED, at=now,
                )
            if _attempt_count(event, project, mode, voter_fingerprint, now) >= RATE_LIMIT_ATTEMPTS:
                return _record_attempt(
                    event, project, mode, voter_fingerprint,
                    VoteAttemptOutcome.REJECTED_RATE_LIMIT, at=now,
                )

            attempt = _record_attempt(
                event, project, mode, voter_fingerprint,
                VoteAttemptOutcome.ACCEPTED, at=now,
            )
            comment = Comment.objects.create(
                project=project,
                author=actor.user if mode == VoteMode.AUTH else None,
                mode=mode,
                voter_fingerprint=voter_fingerprint,
                body=body,
                created_at=now,
            )
            from services import audit
            audit.record(actor, 'voting.comment_created', comment, {
                'project_id': project.pk,
                'comment_id': comment.pk,
                'mode': mode,
                'voter_fingerprint_hash': _audit_fingerprint(voter_fingerprint),
                'body_length': len(body),
                'attempt_id': attempt.pk,
            })
            return comment


def _set_voting_window_now(actor, event, *, open_window):
    from services import audit

    event = _event(event)
    with transaction.atomic():
        event = _event_row_for_update(event.pk)
        require(actor, _organizer_for(actor, event))
        before = {
            'voting_opens_at': event.voting_opens_at.isoformat() if event.voting_opens_at else None,
            'voting_closes_at': event.voting_closes_at.isoformat() if event.voting_closes_at else None,
        }
        now = timezone.now()
        if open_window:
            event.voting_opens_at = now
            action = 'event.voting_opened_now'
        else:
            event.voting_closes_at = now
            action = 'event.voting_closed_now'
        event.save(update_fields=['voting_opens_at', 'voting_closes_at'])
        after = {
            'voting_opens_at': event.voting_opens_at.isoformat() if event.voting_opens_at else None,
            'voting_closes_at': event.voting_closes_at.isoformat() if event.voting_closes_at else None,
        }
        audit.record(actor, action, event, {'before': before, 'after': after})
    return event


def open_voting_now(actor, event):
    return _set_voting_window_now(actor, event, open_window=True)


def close_voting_now(actor, event):
    return _set_voting_window_now(actor, event, open_window=False)


def public_comments(actor, project):
    project_id = project.pk if isinstance(project, Project) else int(project)
    return Comment.objects.filter(
        project_id=project_id,
        is_flagged=False,
    ).select_related('author').order_by('created_at', 'pk')


def organizer_comments(actor, project):
    project_id = project.pk if isinstance(project, Project) else int(project)
    target = Project.objects.select_related('event').get(pk=project_id)
    require(actor, _organizer_for(actor, target.event))
    return Comment.objects.filter(
        project_id=project_id,
    ).select_related('author').order_by('created_at', 'pk')


def comments_for_project_page(actor, project):
    project_id = project.pk if isinstance(project, Project) else int(project)
    target = Project.objects.select_related('event').get(pk=project_id)
    if _organizer_for(actor, target.event):
        return organizer_comments(actor, target)
    return public_comments(actor, target)


def _set_comment_flag(actor, comment_id, flagged):
    from services import audit
    with transaction.atomic():
        try:
            row = Comment.objects.select_for_update().get(pk=comment_id)
        except Comment.DoesNotExist:
            raise ValueError('Comment not found.')
        row_project = Project.objects.select_related('event').get(pk=row.project_id)
        require(actor, _organizer_for(actor, row_project.event))
        before = row.is_flagged
        if before != flagged:
            row.is_flagged = flagged
            row.save(update_fields=['is_flagged'])
            audit.record(actor, 'voting.comment_flagged' if flagged else 'voting.comment_unflagged', row, {
                'comment_id': row.pk,
                'project_id': row.project_id,
                'before': before,
                'after': flagged,
            })
        return row


def flag_comment(actor, comment_id):
    return _set_comment_flag(actor, comment_id, True)


def unflag_comment(actor, comment_id):
    return _set_comment_flag(actor, comment_id, False)


def integrity_summary(actor, event):
    if event is None:
        require(actor, actor.is_organizer or actor.is_site_admin)
        event = actor.event
    event = _event(event)
    require(actor, _organizer_for(actor, event))
    outcome_counts = {key: 0 for key, _ in VoteAttemptOutcome.choices}
    for row in VoteAttempt.objects.filter(event=event).values('outcome').annotate(total=Count('id')):
        outcome_counts[row['outcome']] = row['total']

    attempts_by_project = {
        row['project_id']: row['total']
        for row in VoteAttempt.objects.filter(event=event)
        .values('project_id').annotate(total=Count('id'))
    }
    blocked_by_project = {
        row['project_id']: row['total']
        for row in VoteAttempt.objects.filter(event=event)
        .exclude(outcome__in=[VoteAttemptOutcome.ACCEPTED, VoteAttemptOutcome.WITHDRAWN])
        .values('project_id').annotate(total=Count('id'))
    }
    votes_by_project = {
        row['project_id']: row['total']
        for row in Vote.objects.filter(event=event)
        .values('project_id').annotate(total=Count('id'))
    }
    project_counts = [
        {
            'project_id': project.pk,
            'external_id': project.external_id,
            'title': project.title,
            'is_duplicate': project.is_duplicate_of_id is not None,
            'attempts': attempts_by_project.get(project.pk, 0),
            'blocked_attempts': blocked_by_project.get(project.pk, 0),
            'active_votes': votes_by_project.get(project.pk, 0),
        }
        for project in Project.objects.filter(event=event).order_by('pk')
    ]
    return {
        'event': event,
        'outcomes': outcome_counts,
        'total_attempts': sum(outcome_counts.values()),
        'projects': project_counts,
    }
