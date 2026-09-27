from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from accounts.actors import PermissionDenied
from judging.models import Ballot, BallotScore, JudgeAssignment, AssignmentStatus
from submissions.models import Project


def get_scores(actor, judge_external_id=None):
    if actor.is_organizer:
        if judge_external_id:
            return Ballot.objects.filter(assignment__judge__external_id=judge_external_id, assignment__event=actor.event)
        return Ballot.objects.filter(assignment__event=actor.event)
    if not actor.is_judge:
        raise PermissionDenied
    if judge_external_id and judge_external_id != actor.judge_external_id:
        raise PermissionDenied
    return Ballot.objects.filter(assignment__judge=actor.user, assignment__event=actor.event)


def get_my_assignments(actor):
    if not actor.is_judge:
        raise PermissionDenied
    return JudgeAssignment.objects.filter(
        judge=actor.user, event=actor.event,
    ).select_related(
        'project', 'project__track', 'project__team',
    ).prefetch_related(
        'ballot', 'ballot__scores', 'ballot__scores__criterion',
    ).order_by('id')


def get_assignment_for_judge(actor, assignment_id):
    if not actor.is_judge:
        raise PermissionDenied
    try:
        return JudgeAssignment.objects.select_related(
            'event', 'judge', 'project', 'project__track', 'project__team',
        ).prefetch_related(
            'ballot', 'ballot__scores', 'ballot__scores__criterion',
        ).get(
            pk=assignment_id, event=actor.event, judge=actor.user,
        )
    except JudgeAssignment.DoesNotExist:
        raise PermissionDenied


def get_next_pending_assignment(actor, current_assignment_id=None):
    if not actor.is_judge:
        raise PermissionDenied
    qs = JudgeAssignment.objects.filter(
        judge=actor.user, event=actor.event, status=AssignmentStatus.PENDING,
    )
    if current_assignment_id:
        qs = qs.exclude(pk=current_assignment_id)
    return qs.order_by('id').first()


@transaction.atomic
def save_ballot(actor, assignment_id, scores, comment=None, is_complete=False):
    if not actor.is_judge:
        raise PermissionDenied
    try:
        assignment = JudgeAssignment.objects.select_for_update().select_related('event', 'judge', 'project__event').get(
            pk=assignment_id, event=actor.event, judge=actor.user,
        )
    except JudgeAssignment.DoesNotExist:
        raise PermissionDenied

    ballot, _ = Ballot.objects.get_or_create(assignment=assignment)
    if not is_complete and ballot.is_complete:
        return ballot
    if comment is not None:
        ballot.comment = comment

    rubric = assignment.project.event.rubrics.first()
    if scores and rubric is None:
        raise ValueError('This event has no rubric')
    criteria = {}
    if rubric is not None:
        rubric_criteria = list(rubric.criteria.all())
        criteria = {str(c.pk): c for c in rubric_criteria}
        criteria.update({c.name: c for c in rubric_criteria})

    validated_scores = []
    if scores:
        entries = scores.items() if hasattr(scores, 'items') else (
            (item.get('criterion_id', item.get('criterion')), item.get('value'))
            for item in scores
        )
        for criterion_key, value in entries:
            if value is None or str(value).strip() == '':
                continue
            criterion = criteria.get(str(criterion_key))
            if criterion is None:
                raise ValueError(f'Unknown rubric criterion: {criterion_key}')
            try:
                numeric_value = Decimal(str(value))
            except (InvalidOperation, ValueError, TypeError):
                raise ValueError(f'Score for {criterion.name} must be a number between 0 and {criterion.max_score}.')
            if not numeric_value.is_finite() or numeric_value < 0 or numeric_value > criterion.max_score:
                raise ValueError(f'Score for {criterion.name} must be between 0 and {criterion.max_score}.')
            validated_scores.append((criterion, numeric_value))

    if is_complete:
        ballot.is_complete = True
        ballot.submitted_at = timezone.now()
    ballot.save()
    if is_complete:
        assignment.status = AssignmentStatus.COMPLETED
        assignment.save(update_fields=['status'])

    for criterion, numeric_value in validated_scores:
        BallotScore.objects.update_or_create(
            ballot=ballot, criterion=criterion, defaults={'value': numeric_value},
        )
    return ballot


def save_ballot_draft(actor, assignment_id, scores, comment=None):
    return save_ballot(actor, assignment_id, scores, comment=comment, is_complete=False)


@transaction.atomic
def submit_ballot(actor, assignment_id, scores, comment=''):
    return save_ballot(actor, assignment_id, scores, comment=comment or '', is_complete=True)


def progress(actor):
    if not actor.is_organizer:
        raise PermissionDenied
    projects = Project.objects.filter(event=actor.event)
    total = projects.count()
    completed = projects.filter(judge_assignments__status=AssignmentStatus.COMPLETED).distinct().count()
    return {'completed_projects': completed, 'total_projects': total}
