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

    if is_complete:
        from services import audit
        audit.record(
            actor=actor,
            action='ballot.submit',
            target=ballot,
            payload={
                'assignment_id': assignment.pk,
                'project_id': assignment.project_id,
                'scores_count': len(validated_scores),
            },
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


def export_csv(actor):
    """Export real per-project data as CSV: raw mean, normalized mean, rank, review count, flags."""
    if not actor.is_organizer:
        raise PermissionDenied
    import csv
    import io
    from judging.models import NormalizationRun
    from services import normalization as norm_services

    run_record = NormalizationRun.objects.filter(event=actor.event).order_by('-computed_at', '-id').first()
    if run_record is None:
        run_record = norm_services.run(actor)

    params = run_record.parameters
    flags_map = params.get('project_flags', {})
    review_counts = params.get('project_review_counts', {})

    score_rows = list(run_record.scores.select_related('project'))
    score_rows.sort(
        key=lambda r: (
            0 if r.rank is not None else 1,
            r.rank if r.rank is not None else 0,
            r.project.external_id or f'{r.project.pk:020d}',
        )
    )

    output = io.StringIO(newline='')
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(['project_id', 'raw_mean', 'normalized_mean', 'rank', 'review_count', 'flags'])
    for row in score_rows:
        project_key = row.project.external_id or f'project:{row.project.pk}'
        proj_flags = flags_map.get(project_key, [])
        flag_labels = []
        for f in proj_flags:
            ftype = f.get('type', str(f)) if isinstance(f, dict) else str(f)
            flag_labels.append(ftype)
            if ftype == 'thin_batch':
                flag_labels.append('thin')
            elif ftype == 'constant_judge':
                flag_labels.append('constant-judge')
        if row.project.is_duplicate_of is not None and 'duplicate' not in "".join(flag_labels):
            flag_labels.append('duplicate')

        # Stable de-duplication preserving order
        deduped_flags = []
        seen = set()
        for fl in flag_labels:
            if fl not in seen:
                seen.add(fl)
                deduped_flags.append(fl)

        flags_str = ";".join(deduped_flags)
        writer.writerow([
            project_key,
            f"{row.raw_mean:.4f}" if row.raw_mean is not None else '',
            f"{row.normalized_mean:.4f}" if row.normalized_mean is not None else '',
            row.rank if row.rank is not None else '',
            review_counts.get(project_key, 0),
            flags_str,
        ])
    return output.getvalue()


def get_rubric(actor, event=None):
    """Get or create the default rubric for the event."""
    target_event = event or getattr(actor, 'event', None)
    if target_event is None:
        from events.models import Event
        target_event = Event.objects.first()
    if target_event is None:
        return None
    from judging.models import Rubric
    rubric, _ = Rubric.objects.get_or_create(event=target_event, defaults={'name': 'Default Rubric'})
    return rubric


@transaction.atomic
def configure_rubric(actor, criteria):
    """
    Configure the rubric criteria and weights for an event (organizer-only).

    Validates:
      - At least one criterion.
      - Finite positive weights (> 0).
      - Positive max_score (> 0).
      - Criteria that already have BallotScore rows cannot be deleted.
      - Weight changes are recorded in the audit log with before/after values.
    """
    if not (actor.is_organizer or getattr(actor, 'is_site_admin', False)):
        raise PermissionDenied

    target_event = getattr(actor, 'event', None)
    if target_event is None:
        from events.models import Event
        target_event = Event.objects.first()
    if target_event is None:
        raise ValueError("An event is required to configure a rubric.")

    if not criteria or len(criteria) == 0:
        raise ValueError("At least one criterion is required.")

    from judging.models import Rubric, RubricCriterion, BallotScore
    from services import audit

    validated_items = []
    seen_names = set()
    for idx, item in enumerate(criteria):
        name = item.get('name') if isinstance(item, dict) else getattr(item, 'name', None)
        if not name or not str(name).strip():
            raise ValueError("Criterion name cannot be empty.")
        name = str(name).strip().lower()
        if name in seen_names:
            raise ValueError(f"Duplicate criterion name: '{name}'. Criterion names must be unique.")
        seen_names.add(name)

        raw_weight = item.get('weight') if isinstance(item, dict) else getattr(item, 'weight', None)
        try:
            weight = Decimal(str(raw_weight))
            if not weight.is_finite() or weight <= 0:
                raise ValueError()
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError(f"Weight for criterion '{name}' must be a finite positive number.")

        raw_max = item.get('max_score', 5) if isinstance(item, dict) else getattr(item, 'max_score', 5)
        try:
            max_score = Decimal(str(raw_max))
            if not max_score.is_finite() or max_score <= 0:
                raise ValueError()
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError(f"Max score for criterion '{name}' must be a positive number.")

        order = item.get('order', idx) if isinstance(item, dict) else getattr(item, 'order', idx)
        validated_items.append({
            'name': name,
            'weight': weight,
            'max_score': max_score,
            'order': int(order) if str(order).isdigit() else idx,
        })

    rubric, _ = Rubric.objects.get_or_create(event=target_event, defaults={'name': 'Default Rubric'})
    existing_criteria = {c.name: c for c in rubric.criteria.all()}

    # Check deletion policy: criteria that already have BallotScore rows cannot be deleted
    for name, c in existing_criteria.items():
        if name not in seen_names:
            if BallotScore.objects.filter(criterion=c).exists():
                raise ValueError(
                    f"Cannot delete criterion '{c.name}' because ballots have already been scored against it."
                )

    # Check for weight changes
    weight_changes = []
    for item in validated_items:
        name = item['name']
        if name in existing_criteria:
            old_c = existing_criteria[name]
            if old_c.weight != item['weight']:
                weight_changes.append({
                    'name': name,
                    'before': float(old_c.weight),
                    'after': float(item['weight']),
                })

    # Perform mutations
    for name, c in list(existing_criteria.items()):
        if name not in seen_names:
            c.delete()

    for item in validated_items:
        RubricCriterion.objects.update_or_create(
            rubric=rubric,
            name=item['name'],
            defaults={
                'weight': item['weight'],
                'max_score': item['max_score'],
                'order': item['order'],
            },
        )

    # Audit log entry with before/after weight changes
    audit.record(
        actor=actor,
        action='rubric.configure',
        target=rubric,
        payload={
            'event_id': target_event.external_id or str(target_event.pk),
            'criteria_count': len(validated_items),
            'weight_changes': weight_changes,
            'criteria': [
                {
                    'name': item['name'],
                    'weight': float(item['weight']),
                    'max_score': float(item['max_score']),
                }
                for item in validated_items
            ],
        },
    )

    return rubric
