"""
Placeholder views for P-11 route skeleton.

These endpoints establish the exact route paths declared in .dogfood.toml
and API.md §1:
  - gallery (/projects)
  - submit (/projects/new)
  - judge_scores (/api/judge/scores)
  - peer_scores (/api/judge/scores?judge=...)
  - csv_export (/api/export.csv)

These are simple 200 placeholder views for G1 Step 2, to be filled in with
real business logic and service calls in G2/G3.
"""

import json

from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_GET, require_POST


from submissions.views import gallery_view, submit_view
from services.judging import get_scores, progress, submit_ballot


def judge_scores_view(request):
    """Shared P-11 route; services.judging owns every visibility decision."""
    ballots = get_scores(request.actor, request.GET.get('judge'))
    rows = []
    for ballot in ballots.select_related('assignment__judge', 'assignment__project').prefetch_related('scores__criterion'):
        rows.append({
            'judge': ballot.assignment.judge.external_id,
            'project': ballot.assignment.project.external_id,
            'comment': ballot.comment,
            'submitted_at': ballot.submitted_at.isoformat() if ballot.submitted_at else None,
            'is_complete': ballot.is_complete,
            'criteria': {score.criterion.name: str(score.value) for score in ballot.scores.all()},
        })
    return JsonResponse({'scores': rows})


@require_POST
def ballot_submit_view(request, assignment_id):
    try:
        payload = json.loads(request.body or '{}')
        ballot = submit_ballot(request.actor, assignment_id, payload.get('scores', {}), payload.get('comment', ''))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        return JsonResponse({'error': 'invalid_request', 'detail': str(exc)}, status=400)
    return JsonResponse({'ballot_id': ballot.pk, 'is_complete': ballot.is_complete}, status=200)


@require_GET
def organizer_progress_view(request):
    return JsonResponse(progress(request.actor))


def csv_export_view(request):
    """P-11 csv_export placeholder (/api/export.csv) — filled in at G4."""
    return HttpResponse(
        "rank,project_id,score\n",
        content_type="text/csv",
        status=200,
    )
