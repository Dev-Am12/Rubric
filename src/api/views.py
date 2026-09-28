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


from accounts.actors import PermissionDenied
from submissions.views import gallery_view, submit_view
from services.judging import get_scores, progress, submit_ballot, export_csv
from services import audit as audit_services


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


@require_GET
def csv_export_view(request):
    """P-11 csv_export endpoint (/api/export.csv). Organizer-only."""
    content = export_csv(request.actor)
    response = HttpResponse(content, content_type="text/csv; charset=utf-8", status=200)
    response['Content-Disposition'] = 'attachment; filename="export.csv"'
    return response


@require_GET
def organizer_audit_log_view(request):
    """
    GET /api/v1/organizer/audit-log (?page=&page_size=)
    Organizer-only. Returns paginated audit log entries.
    """
    if not (request.actor.is_organizer or getattr(request.actor, 'is_site_admin', False)):
        raise PermissionDenied

    page = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', 20)
    try:
        page = int(page)
        page_size = int(page_size)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'invalid_parameters', 'detail': 'page and page_size must be integers'}, status=400)

    data = audit_services.list(request.actor, page=page, page_size=page_size)
    entries = []
    for entry in data['results']:
        entries.append({
            'seq': entry.seq,
            'prev_hash': entry.prev_hash,
            'entry_hash': entry.entry_hash,
            'created_at': entry.created_at,
            'actor': {
                'user_id': entry.actor_user_id,
                'label': entry.actor_label or None,
            },
            'action': entry.action,
            'target': {
                'type': entry.target_type,
                'id': entry.target_id,
            },
            'payload': entry.payload,
        })

    return JsonResponse({
        'entries': entries,
        'page': data['page'],
        'page_size': data['page_size'],
        'total': data['total'],
        'pages': data['pages'],
    })


@require_GET
def organizer_audit_verify_view(request):
    """
    GET /api/v1/organizer/audit-log/verify (result, head hash, export download)
    Organizer-only.
    """
    if not (request.actor.is_organizer or getattr(request.actor, 'is_site_admin', False)):
        raise PermissionDenied

    if request.GET.get('download') or request.GET.get('export'):
        content = audit_services.export_chain()
        response = HttpResponse(content, content_type="application/json; charset=utf-8", status=200)
        response['Content-Disposition'] = 'attachment; filename="audit-log-export.json"'
        return response

    valid, first_bad_seq, head_hash = audit_services.verify(request.actor)
    return JsonResponse({
        'valid': valid,
        'first_bad_seq': first_bad_seq,
        'head_hash': head_hash,
    })


