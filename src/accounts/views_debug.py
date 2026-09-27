"""
Deliberately leaky debug route — the control case for the authz coverage test.

AUTHZ.md §4: this route has NO policy check at all.  It exists purely so
the route×role coverage test can prove it catches an undeclared route.

TODO(G8): REMOVE THIS ENTIRE FILE AND ITS URL BEFORE SUBMISSION FREEZE.
This is not something that should ship.  It should be deleted in the
hardening pass (PLAN.md §5.6, G8).
"""

from django.http import JsonResponse


def leaky_scores_view(request, judge_id):
    """
    WARNING: This view has NO authorization check.  ANY request — anonymous,
    participant, wrong judge — gets through.  This is intentional for the
    control case only.
    """
    return JsonResponse({
        'warning': 'THIS IS A DELIBERATELY LEAKY DEBUG ENDPOINT',
        'judge_id': judge_id,
        'scores': [],
    })
