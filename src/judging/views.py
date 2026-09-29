"""
Views for judge-facing UI and organizer progress.

Design reference:
  - UX.md §1 (screen inventory: /judge/queue, /judge/ballots/{id}, /organizer/progress)
  - UX.md §2 (the ballot screen: two-pane layout, fixed submission material,
              independently scrolling rubric, autosave via HTMX, keyboard shortcuts,
              strictly zero leak of peer scores)
  - UX.md §4 (clean, minimal, professional, quietly sophisticated)
  - AUTHZ.md §3.2 (judging isolation, organizer progress)
"""

import json
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from accounts.actors import PermissionDenied
from judging.models import AssignmentStatus, BallotScore
from services import judging as judging_services

# Behavioral anchor descriptions per NORMALIZATION.md and UX.md §2
CRITERION_ANCHORS = {
    'functionality': {
        1: 'Does not function / crashes immediately',
        2: 'Partially functional / core workflow broken',
        3: 'Baseline functionality / works with minor flaws',
        4: 'Robust / works smoothly across all main use cases',
        5: 'Exceptional / production-ready, handles edge cases gracefully',
    },
    'quality': {
        1: 'Unstructured / lack of architecture or documentation',
        2: 'Rough / difficult to follow or maintain',
        3: 'Solid / clean structure and readable design',
        4: 'High quality / thoughtful architecture and UX',
        5: 'Exemplary / elegant craftsmanship and best practices',
    },
    'innovation': {
        1: 'Derivative / direct clone with no novel aspect',
        2: 'Minor / slight twist on existing tools',
        3: 'Creative / interesting perspective or angle',
        4: 'Novel / solves a real problem in an original way',
        5: 'Breakthrough / highly inventive or transformative',
    },
}

DEFAULT_ANCHORS = {
    1: 'Poor / does not meet expectations',
    2: 'Below average / partially meets expectations',
    3: 'Good / meets baseline expectations',
    4: 'Very good / exceeds expectations',
    5: 'Outstanding / exceptional achievement',
}


def _extract_scores_from_post(post_data):
    scores = {}
    for key, value in post_data.items():
        if key.startswith('score_') and str(value).strip():
            criterion_id = key[len('score_'):]
            scores[criterion_id] = str(value).strip()
    return scores


@require_GET
def judge_queue_view(request):
    """
    Judge assignment queue (/judge/queue).
    Shows the judge's own assignments partitioned into pending and completed.
    Zero code path to any other judge's data.
    """
    assignments = list(judging_services.get_my_assignments(request.actor))
    pending_assignments = [a for a in assignments if a.status == AssignmentStatus.PENDING]
    completed_assignments = [a for a in assignments if a.status == AssignmentStatus.COMPLETED]

    total_count = len(assignments)
    completed_count = len(completed_assignments)
    pending_count = len(pending_assignments)
    percent_complete = int((completed_count / total_count * 100)) if total_count else 0

    first_pending = pending_assignments[0] if pending_assignments else None

    context = {
        'assignments': assignments,
        'pending_assignments': pending_assignments,
        'completed_assignments': completed_assignments,
        'total_count': total_count,
        'completed_count': completed_count,
        'pending_count': pending_count,
        'percent_complete': percent_complete,
        'first_pending': first_pending,
    }
    return render(request, 'judging/queue.html', context)


@require_http_methods(['GET', 'POST'])
def ballot_view(request, assignment_id):
    """
    Two-pane ballot scoring screen (/judge/ballots/{assignment_id}).
    Left pane: submission material (fixed).
    Right pane: rubric criteria + comment (scrolls independently).
    Submitting advances to the next pending assignment.
    """
    assignment = judging_services.get_assignment_for_judge(request.actor, assignment_id)

    if request.method == 'POST':
        scores = _extract_scores_from_post(request.POST)
        comment = request.POST.get('comment', '').strip()
        judging_services.submit_ballot(request.actor, assignment.pk, scores, comment=comment)

        next_pending = judging_services.get_next_pending_assignment(
            request.actor, current_assignment_id=assignment.pk,
        )
        if next_pending:
            return redirect('judge_ballot', assignment_id=next_pending.pk)
        return redirect('judge_queue')

    # GET request: load ballot and rubric criteria
    ballot = getattr(assignment, 'ballot', None)
    existing_scores = {}
    if ballot:
        for s in ballot.scores.all():
            existing_scores[s.criterion_id] = s.value

    # Compute queue position
    my_assignments = list(judging_services.get_my_assignments(request.actor))
    total_assigned = len(my_assignments)
    current_index = 1
    prev_assignment = None
    next_assignment = None
    for i, a in enumerate(my_assignments):
        if a.pk == assignment.pk:
            current_index = i + 1
            if i > 0:
                prev_assignment = my_assignments[i - 1]
            if i < len(my_assignments) - 1:
                next_assignment = my_assignments[i + 1]
            break

    # Build rubric criteria with anchor descriptions
    rubric = assignment.project.event.rubrics.first()
    criteria = rubric.criteria.all().order_by('order', 'id') if rubric else []
    criteria_data = []
    for c in criteria:
        c_name = c.name.lower()
        anchors = CRITERION_ANCHORS.get(c_name, {})
        curr_val = existing_scores.get(c.pk)
        curr_val_int = int(curr_val) if curr_val is not None else None
        options = []
        max_score = int(c.max_score) if c.max_score else 5
        for val in range(1, max_score + 1):
            options.append({
                'value': val,
                'anchor': anchors.get(val, ''),
                'is_selected': (curr_val_int == val),
            })
        criteria_data.append({
            'criterion': c,
            'current_value': curr_val_int,
            'options': options,
        })

    context = {
        'assignment': assignment,
        'project': assignment.project,
        'ballot': ballot,
        'criteria_data': criteria_data,
        'total_assigned': total_assigned,
        'current_index': current_index,
        'prev_assignment': prev_assignment,
        'next_assignment': next_assignment,
    }
    return render(request, 'judging/ballot.html', context)


@require_POST
def ballot_autosave_view(request, assignment_id):
    """
    HTMX autosave endpoint (/judge/ballots/{assignment_id}/autosave).
    Posts partial save with hx-trigger="change, keyup delay:1s".
    Updates draft scores and comment without completing the ballot.
    """
    # Verify assignment belongs to requesting judge
    judging_services.get_assignment_for_judge(request.actor, assignment_id)

    scores = _extract_scores_from_post(request.POST)
    comment = request.POST.get('comment', None)

    ballot = judging_services.save_ballot_draft(
        request.actor, assignment_id, scores, comment=comment,
    )

    if request.headers.get('Accept') == 'application/json':
        return JsonResponse({
            'saved': True,
            'ballot_id': ballot.pk,
            'is_complete': ballot.is_complete,
        })

    now_str = timezone.now().strftime('%H:%M:%S')
    return HttpResponse(
        f'<span class="autosave-status saved" id="autosave-status">✓ Draft autosaved at {now_str}</span>'
    )


@require_GET
def organizer_progress_page_view(request):
    """
    Minimal organizer progress dashboard (/organizer/progress).
    Calls services.judging.progress() for raw numbers.
    Accessible only to organizer actor.
    """
    data = judging_services.progress(request.actor)

    if request.headers.get('Accept') == 'application/json':
        return JsonResponse(data)

    total = data['total_projects']
    completed = data['completed_projects']
    percent = int((completed / total * 100)) if total else 0

    context = {
        'total_projects': total,
        'completed_projects': completed,
        'percent_complete': percent,
    }
    return render(request, 'judging/organizer_progress.html', context)
