"""
URL configuration for rubric project.
"""

from django.urls import path

from accounts.views_debug import leaky_scores_view
from api.views import (
    judge_scores_view,
    csv_export_view,
    ballot_submit_view,
    organizer_progress_view,
)
from judging.views import (
    judge_queue_view,
    ballot_view,
    ballot_autosave_view,
    organizer_progress_page_view,
)
from judging.views_organizer import (
    organizer_dashboard_view,
    organizer_assignments_view,
    organizer_normalization_view,
)
from submissions.views import (
    gallery_view,
    submit_view,
    project_detail_view,
    project_edit_view,
    my_submissions_view,
)

# Admin is intentionally not shipped (PLAN.md P-08)
urlpatterns = [
    # -----------------------------------------------------------------------
    # Judging & Organizer UI routes (UX.md §1, §2, §3)
    # -----------------------------------------------------------------------
    path('judge/queue', judge_queue_view, name='judge_queue'),
    path('judge/ballots/<int:assignment_id>', ballot_view, name='judge_ballot'),
    path('judge/ballots/<int:assignment_id>/autosave', ballot_autosave_view, name='judge_ballot_autosave'),
    path('organizer', organizer_dashboard_view, name='organizer_dashboard'),
    path('organizer/assignments', organizer_assignments_view, name='organizer_assignments'),
    path('organizer/normalization', organizer_normalization_view, name='organizer_normalization'),
    path('organizer/progress', organizer_progress_page_view, name='organizer_progress_page'),

    # -----------------------------------------------------------------------
    # Submissions UI routes (UX.md §1, API.md §2)
    # -----------------------------------------------------------------------
    path('projects', gallery_view, name='gallery'),
    path('projects/new', submit_view, name='submit'),
    path('projects/<int:id>', project_detail_view, name='project_detail'),
    path('projects/<int:id>/edit', project_edit_view, name='project_edit'),
    path('my/submissions', my_submissions_view, name='my_submissions'),

    # -----------------------------------------------------------------------
    # P-11 routes (API.md §1, .dogfood.toml)
    # -----------------------------------------------------------------------
    path('api/judge/scores', judge_scores_view, name='judge_scores'),
    path('api/v1/ballots/<int:assignment_id>', ballot_submit_view, name='ballot_submit'),
    path('api/v1/organizer/progress', organizer_progress_view, name='organizer_progress'),
    path('api/export.csv', csv_export_view, name='csv_export'),

    # -----------------------------------------------------------------------
    # TODO(G8): REMOVE before submission freeze.
    # Deliberately leaky control-case route with NO policy check (AUTHZ.md §4).
    # Exists only so the authz coverage test can prove it catches undeclared
    # routes.  This is not something that should ship.
    # -----------------------------------------------------------------------
    path(
        'debug/_leaky_test_only/<str:judge_id>/scores',
        leaky_scores_view,
        name='debug_leaky_scores',
    ),
]
