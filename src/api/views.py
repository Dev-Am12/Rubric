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

from django.http import JsonResponse, HttpResponse


from submissions.views import gallery_view, submit_view


def judge_scores_view(request):
    """P-11 judge_scores placeholder (/api/judge/scores) — filled in at G3."""
    return JsonResponse(
        {"status": "placeholder", "route": "judge_scores"},
        status=200,
    )


def peer_scores_view(request):
    """P-11 peer_scores placeholder (/api/judge/scores?judge=...) — filled in at G3."""
    return JsonResponse(
        {"status": "placeholder", "route": "peer_scores"},
        status=200,
    )


def csv_export_view(request):
    """P-11 csv_export placeholder (/api/export.csv) — filled in at G4."""
    return HttpResponse(
        "rank,project_id,score\n",
        content_type="text/csv",
        status=200,
    )
