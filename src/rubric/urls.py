"""
URL configuration for rubric project.
"""

from django.urls import path

from accounts.views import (
    register_view,
    login_view,
    logout_view,
)
from accounts.views_debug import leaky_scores_view
from api.views import (
    judge_scores_view,
    csv_export_view,
    ballot_submit_view,
    organizer_progress_view,
    organizer_audit_log_view,
    organizer_audit_verify_view,
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
    organizer_audit_log_page_view,
    organizer_rubric_view,
    organizer_judges_view,
    judge_invite_accept_view,
)
from events.views import landing_page_view
from events.views_organizer import (
    organizer_events_view,
    organizer_event_dates_view,
    organizer_open_voting_now_view,
    organizer_close_voting_now_view,
    organizer_event_tracks_view,
    organizer_event_track_edit_view,
    organizer_event_prizes_view,
    organizer_event_prize_edit_view,
    organizer_event_make_current_view,
)
from teams.views import (
    team_create_view,
    team_join_view,
    team_detail_view,
)
from submissions.views import (
    gallery_view,
    submit_view,
    project_detail_view,
    project_edit_view,
    my_submissions_view,
)
from voting.views import (
    ballot_view as public_voting_ballot_view,
    cast_view,
    withdraw_view,
    results_view,
    project_comment_view,
    organizer_comment_flag_view,
    organizer_voting_summary_view,
)

# Admin is intentionally not shipped (PLAN.md P-08)
urlpatterns = [
    # -----------------------------------------------------------------------
    # Public Landing Page (UX.md §1)
    # -----------------------------------------------------------------------
    path('', landing_page_view, name='landing_page'),

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
    path('organizer/audit-log', organizer_audit_log_page_view, name='organizer_audit_log_page'),
    path('organizer/rubric', organizer_rubric_view, name='organizer_rubric'),
    path('organizer/events', organizer_events_view, name='organizer_events'),
    path('organizer/events/<int:event_id>/dates', organizer_event_dates_view, name='organizer_event_dates'),
    path('organizer/events/<int:event_id>/voting/open-now', organizer_open_voting_now_view, name='organizer_voting_open_now'),
    path('organizer/events/<int:event_id>/voting/close-now', organizer_close_voting_now_view, name='organizer_voting_close_now'),
    path('organizer/events/<int:event_id>/tracks', organizer_event_tracks_view, name='organizer_event_tracks'),
    path('organizer/events/<int:event_id>/tracks/<int:track_id>', organizer_event_track_edit_view, name='organizer_event_track_edit'),
    path('organizer/events/<int:event_id>/prizes', organizer_event_prizes_view, name='organizer_event_prizes'),
    path('organizer/events/<int:event_id>/prizes/<int:prize_id>', organizer_event_prize_edit_view, name='organizer_event_prize_edit'),
    path('organizer/events/<int:event_id>/make-current', organizer_event_make_current_view, name='organizer_event_make_current'),
    path('organizer/judges', organizer_judges_view, name='organizer_judges'),
    path('invite/judge/<str:token>', judge_invite_accept_view, name='judge_invite_accept'),

    # -----------------------------------------------------------------------
    # Teams UI routes (UX.md §1, API.md §2)
    # -----------------------------------------------------------------------
    path('teams/new', team_create_view, name='team_create'),
    path('teams/join/<str:code>', team_join_view, name='team_join'),
    path('teams/<int:id>', team_detail_view, name='team_detail'),

    # -----------------------------------------------------------------------
    # Accounts UI routes (UX.md §1, API.md §3)
    # -----------------------------------------------------------------------
    path('accounts/register', register_view, name='register'),
    path('login', login_view, name='login'),
    path('accounts/login', login_view, name='accounts_login'),
    path('logout', logout_view, name='logout'),
    path('accounts/logout', logout_view, name='accounts_logout'),

    # -----------------------------------------------------------------------
    # Submissions UI routes (UX.md §1, API.md §2)
    # -----------------------------------------------------------------------
    path('projects', gallery_view, name='gallery'),
    path('projects/new', submit_view, name='submit'),
    path('projects/<int:id>', project_detail_view, name='project_detail'),
    path('projects/<int:id>/edit', project_edit_view, name='project_edit'),
    path('my/submissions', my_submissions_view, name='my_submissions'),
    path('projects/<int:project_id>/comments', project_comment_view, name='project_comment_create'),

    # -----------------------------------------------------------------------
    # Public voting (T3; identity, rate limits, and visibility in services.voting)
    # -----------------------------------------------------------------------
    path('vote/<slug:event_slug>', public_voting_ballot_view, name='voting_ballot'),
    path('vote/<slug:event_slug>/<int:project_id>', cast_view, name='voting_cast'),
    path('vote/<slug:event_slug>/<int:project_id>/withdraw', withdraw_view, name='voting_withdraw'),
    path('results/<slug:event_slug>', results_view, name='voting_results'),
    path('api/v1/organizer/comments/<int:comment_id>/flag', organizer_comment_flag_view, name='organizer_comment_flag'),
    path('api/v1/organizer/voting/summary', organizer_voting_summary_view, name='organizer_voting_summary'),

    # -----------------------------------------------------------------------
    # P-11 routes (API.md §1, .dogfood.toml)
    # -----------------------------------------------------------------------
    path('api/judge/scores', judge_scores_view, name='judge_scores'),
    path('api/v1/ballots/<int:assignment_id>', ballot_submit_view, name='ballot_submit'),
    path('api/v1/organizer/progress', organizer_progress_view, name='organizer_progress'),
    path('api/v1/organizer/audit-log', organizer_audit_log_view, name='organizer_audit_log'),
    path('api/v1/organizer/audit-log/verify', organizer_audit_verify_view, name='organizer_audit_verify'),
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
