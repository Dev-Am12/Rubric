"""
Tests for G2 Step 1:
  1. Duplicate direction: prj_07.is_duplicate_of → prj_41 (pinned by test)
  2. Deadline enforcement via services.submissions.update() (select_for_update)
  3. CSRF split: header-auth POST without CSRF token succeeds;
     cookie-auth POST without CSRF token is rejected
  4. Team creation, invite-code join, and service-layer authorization
  5. Submission create/update/submit/get/gallery service functions
  6. Fixture import idempotency and count verification
"""

import json
from datetime import timedelta
from pathlib import Path

from django.test import TestCase, Client, RequestFactory, override_settings
from django.utils import timezone

from accounts.actors import Actor, AnonymousActor, PermissionDenied
from accounts.models import (
    AuthToken, EventMembership, EventRole, JudgeTrackEligibility, User,
)
from events.models import Event, Track
from submissions.models import Project, ProjectStatus
from submissions.services import (
    create as create_submission,
    update as update_submission,
    submit as submit_submission,
    get as get_submission,
    gallery,
)
from teams.models import Team, TeamMembership
from teams.services import create_team, join_team


# -----------------------------------------------------------------------
# 1. Duplicate direction — the single most important fact to pin down
# -----------------------------------------------------------------------

class DuplicateDirectionTest(TestCase):
    """
    The earlier submission (prj_07, submitted 04:29) flags itself against
    the later canonical one (prj_41, submitted 17:57):
      prj_07.is_duplicate_of = prj_41
      prj_41.is_duplicate_of = None
    This is the corrected direction where the earlier submission points to the later canonical one.
    """

    def setUp(self):
        """Create the two projects with the correct direction."""
        self.event = Event.objects.create(
            slug='dup-test', name='Dup Test',
            submissions_close_at=timezone.now() + timedelta(days=7),
            external_id='evt_dup',
        )
        self.track = Track.objects.create(
            event=self.event, name='Track 3', external_id='trk_dup_03',
        )
        self.user = User.objects.create_user(
            email='dup@example.org', display_name='Dup Tester',
        )
        self.team = Team.objects.create(
            event=self.event, name='Team 07', invite_code='dup-test-code',
            external_id='tm_dup_07', created_by=self.user,
        )

        # The LATER submission is the canonical one (no flag)
        self.prj_41 = Project.objects.create(
            event=self.event, team=self.team, track=self.track,
            title='Dry Harbour', summary='Test',
            status=ProjectStatus.SUBMITTED,
            submitted_at=timezone.now(),
            external_id='prj_dup_41',
        )

        # The EARLIER submission flags itself against the later one
        self.prj_07 = Project.objects.create(
            event=self.event, team=self.team, track=self.track,
            title='Dry Harbour', summary='Test',
            status=ProjectStatus.SUBMITTED,
            submitted_at=timezone.now() - timedelta(hours=13),
            external_id='prj_dup_07',
            is_duplicate_of=self.prj_41,
            duplicate_flag_reason='Same team, same title, submitted earlier.',
        )

    def test_earlier_flags_itself_against_later(self):
        """prj_07 (earlier) → prj_41 (later, canonical)."""
        self.assertEqual(self.prj_07.is_duplicate_of_id, self.prj_41.id)
        self.assertIsNotNone(self.prj_07.duplicate_flag_reason)

    def test_later_canonical_is_not_flagged(self):
        """prj_41 (later, canonical) has no duplicate flag."""
        self.assertIsNone(self.prj_41.is_duplicate_of_id)
        self.assertIsNone(self.prj_41.duplicate_flag_reason)


# -----------------------------------------------------------------------
# 2. Deadline enforcement — services.submissions.update()
# -----------------------------------------------------------------------

class DeadlineEnforcementTest(TestCase):
    """
    services.submissions.update() must reject writes when the event is
    closed, via select_for_update() on the Event row — NOT via CSRF or
    any other side effect.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='deadline@example.org', display_name='Deadline User',
        )
        # Event that closed 1 hour ago
        self.closed_event = Event.objects.create(
            slug='closed-event', name='Closed Event',
            submissions_close_at=timezone.now() - timedelta(hours=1),
        )
        # Event that's still open
        self.open_event = Event.objects.create(
            slug='open-event', name='Open Event',
            submissions_close_at=timezone.now() + timedelta(days=7),
        )
        self.track = Track.objects.create(
            event=self.closed_event, name='Track', external_id='trk_dl_01',
        )
        self.open_track = Track.objects.create(
            event=self.open_event, name='Track', external_id='trk_dl_02',
        )

        # Teams
        self.closed_team = Team.objects.create(
            event=self.closed_event, name='Team Closed',
            invite_code='dl-closed', created_by=self.user,
        )
        TeamMembership.objects.create(team=self.closed_team, user=self.user)

        self.open_team = Team.objects.create(
            event=self.open_event, name='Team Open',
            invite_code='dl-open', created_by=self.user,
        )
        TeamMembership.objects.create(team=self.open_team, user=self.user)

        # Memberships
        EventMembership.objects.create(
            event=self.closed_event, user=self.user,
            role=EventRole.PARTICIPANT,
        )
        EventMembership.objects.create(
            event=self.open_event, user=self.user,
            role=EventRole.PARTICIPANT,
        )

        # Projects
        self.closed_project = Project.objects.create(
            event=self.closed_event, team=self.closed_team,
            track=self.track, title='Closed Project', summary='Test',
            status=ProjectStatus.DRAFT,
        )
        self.open_project = Project.objects.create(
            event=self.open_event, team=self.open_team,
            track=self.open_track, title='Open Project', summary='Test',
            status=ProjectStatus.DRAFT,
        )

    def test_update_rejected_after_deadline(self):
        """
        Updating a project in a closed event raises PermissionDenied.
        This exercises services.submissions.update() directly.
        """
        actor = Actor(user=self.user, event=self.closed_event)
        with self.assertRaises(PermissionDenied):
            update_submission(actor, self.closed_project.id, title='New Title')

    def test_update_succeeds_before_deadline(self):
        """Updating a project in an open event succeeds."""
        actor = Actor(user=self.user, event=self.open_event)
        updated = update_submission(
            actor, self.open_project.id, title='Updated Title',
        )
        self.assertEqual(updated.title, 'Updated Title')

    def test_submit_rejected_after_deadline(self):
        """Submitting a project in a closed event raises PermissionDenied."""
        actor = Actor(user=self.user, event=self.closed_event)
        with self.assertRaises(PermissionDenied):
            submit_submission(actor, self.closed_project.id)

    def test_submit_succeeds_before_deadline(self):
        """Submitting a project in an open event succeeds."""
        actor = Actor(user=self.user, event=self.open_event)
        submitted = submit_submission(actor, self.open_project.id)
        self.assertEqual(submitted.status, ProjectStatus.SUBMITTED)
        self.assertIsNotNone(submitted.submitted_at)


# -----------------------------------------------------------------------
# 3. CSRF split — header-auth vs. cookie-auth
# -----------------------------------------------------------------------

@override_settings(
    ROOT_URLCONF='rubric.urls',
    MIDDLEWARE=[
        'django.middleware.security.SecurityMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.middleware.common.CommonMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
        'django.contrib.messages.middleware.MessageMiddleware',
        'django.middleware.clickjacking.XFrameOptionsMiddleware',
        'accounts.middleware.AuthMiddleware',
    ],
)
class CsrfSplitTest(TestCase):
    """
    When authenticated via Authorization header, CSRF is bypassed.
    When authenticated via session cookie, CSRF is enforced.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='csrf@example.org', display_name='CSRF User',
        )
        self.event = Event.objects.create(
            slug='csrf-test', name='CSRF Test',
            submissions_close_at=timezone.now() + timedelta(days=7),
        )
        EventMembership.objects.create(
            event=self.event, user=self.user,
            role=EventRole.PARTICIPANT,
        )
        _, self.raw_token = AuthToken.create_token(
            self.user, label='csrf-test',
        )
        self.client = Client(enforce_csrf_checks=True)

    def test_header_auth_post_bypasses_csrf(self):
        """
        A POST with Authorization header and no CSRF token should succeed
        (not get 403'd by CSRF middleware).
        """
        response = self.client.post(
            '/projects/new',
            content_type='application/json',
            data=json.dumps({'title': 'test'}),
            HTTP_AUTHORIZATION=f'Bearer {self.raw_token}',
        )
        # Should NOT be 403 from CSRF — the placeholder view returns 200
        self.assertEqual(response.status_code, 200)

    def test_cookie_auth_post_rejected_without_csrf(self):
        """
        A POST with session cookie but no CSRF token should be rejected
        with 403 by Django's CsrfViewMiddleware.
        """
        response = self.client.post(
            '/projects/new',
            content_type='application/json',
            data=json.dumps({'title': 'test'}),
            **{'HTTP_COOKIE': f'session={self.raw_token}'},
        )
        # CsrfViewMiddleware should reject this with 403
        self.assertEqual(response.status_code, 403)


# -----------------------------------------------------------------------
# 4. Teams service layer
# -----------------------------------------------------------------------

class TeamsServiceTest(TestCase):
    """Test create_team and join_team service functions."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='teamlead@example.org', display_name='Team Lead',
        )
        self.joiner = User.objects.create_user(
            email='joiner@example.org', display_name='Joiner',
        )
        self.event = Event.objects.create(
            slug='team-test', name='Team Test',
            submissions_close_at=timezone.now() + timedelta(days=7),
        )
        EventMembership.objects.create(
            event=self.event, user=self.user,
            role=EventRole.PARTICIPANT,
        )
        EventMembership.objects.create(
            event=self.event, user=self.joiner,
            role=EventRole.PARTICIPANT,
        )

    def test_create_team(self):
        """Any registered user can create a team."""
        actor = Actor(user=self.user, event=self.event)
        team = create_team(actor, self.event, 'My Team')
        self.assertEqual(team.name, 'My Team')
        self.assertEqual(team.event, self.event)
        self.assertIsNotNone(team.invite_code)
        # Creator is automatically a member
        self.assertTrue(
            TeamMembership.objects.filter(
                team=team, user=self.user,
            ).exists()
        )

    def test_create_team_anonymous_rejected(self):
        """Anonymous actors cannot create teams."""
        with self.assertRaises(PermissionDenied):
            create_team(AnonymousActor(), self.event, 'Bad Team')

    def test_join_team_with_correct_code(self):
        """Joining with the correct invite code succeeds."""
        actor = Actor(user=self.user, event=self.event)
        team = create_team(actor, self.event, 'Joinable Team')

        joiner_actor = Actor(user=self.joiner, event=self.event)
        membership = join_team(joiner_actor, team.id, team.invite_code)
        self.assertEqual(membership.team, team)
        self.assertEqual(membership.user, self.joiner)

    def test_join_team_with_wrong_code(self):
        """Joining with the wrong invite code is rejected."""
        actor = Actor(user=self.user, event=self.event)
        team = create_team(actor, self.event, 'Secret Team')

        joiner_actor = Actor(user=self.joiner, event=self.event)
        with self.assertRaises(ValueError):
            join_team(joiner_actor, team.id, 'wrong-code')


# -----------------------------------------------------------------------
# 5. Submissions service layer
# -----------------------------------------------------------------------

class SubmissionsServiceTest(TestCase):
    """Test create, update, submit, get, gallery service functions."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='submitter@example.org', display_name='Submitter',
        )
        self.other_user = User.objects.create_user(
            email='other@example.org', display_name='Other User',
        )
        self.event = Event.objects.create(
            slug='sub-test', name='Sub Test',
            submissions_close_at=timezone.now() + timedelta(days=7),
        )
        self.track = Track.objects.create(
            event=self.event, name='AI Track',
        )
        self.team = Team.objects.create(
            event=self.event, name='Sub Team',
            invite_code='sub-test', created_by=self.user,
        )
        TeamMembership.objects.create(team=self.team, user=self.user)
        EventMembership.objects.create(
            event=self.event, user=self.user,
            role=EventRole.PARTICIPANT,
        )
        EventMembership.objects.create(
            event=self.event, user=self.other_user,
            role=EventRole.PARTICIPANT,
        )
        self.actor = Actor(user=self.user, event=self.event)
        self.other_actor = Actor(user=self.other_user, event=self.event)

    def test_create_submission_as_team_member(self):
        """Team member can create a submission."""
        project = create_submission(
            self.actor, self.team, self.track,
            title='My Project', summary='A great project',
        )
        self.assertEqual(project.title, 'My Project')
        self.assertEqual(project.status, ProjectStatus.DRAFT)
        self.assertEqual(project.team, self.team)

    def test_create_submission_as_non_member_rejected(self):
        """Non-team-member cannot create a submission for that team."""
        with self.assertRaises(PermissionDenied):
            create_submission(
                self.other_actor, self.team, self.track,
                title='Sneaky', summary='Trying to submit for another team',
            )

    def test_get_submitted_project_is_public(self):
        """A SUBMITTED project is visible to anyone."""
        project = create_submission(
            self.actor, self.team, self.track,
            title='Public Project', summary='Visible to all',
        )
        submit_submission(self.actor, project.id)
        # Even anonymous can see it
        result = get_submission(AnonymousActor(), project.id)
        self.assertEqual(result.title, 'Public Project')

    def test_get_draft_project_rejected_for_non_owner(self):
        """A DRAFT project is not visible to non-owners."""
        project = create_submission(
            self.actor, self.team, self.track,
            title='Secret Draft', summary='Hidden',
        )
        with self.assertRaises(PermissionDenied):
            get_submission(self.other_actor, project.id)

    def test_gallery_returns_only_submitted(self):
        """Gallery returns only SUBMITTED projects."""
        draft = create_submission(
            self.actor, self.team, self.track,
            title='Draft', summary='Not visible',
        )
        submitted = create_submission(
            self.actor, self.team, self.track,
            title='Submitted', summary='Visible',
        )
        submit_submission(self.actor, submitted.id)

        results = list(gallery(AnonymousActor()))
        titles = [p.title for p in results]
        self.assertIn('Submitted', titles)
        self.assertNotIn('Draft', titles)


# -----------------------------------------------------------------------
# 6. Fixture import idempotency (runs against SQLite in-memory)
# -----------------------------------------------------------------------

class FixtureImportIdempotencyTest(TestCase):
    """
    Test that seed_fixtures imports all data correctly and idempotently.
    Uses the real fixtures.json from the repo root.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Locate fixtures.json
        cls.fixtures_path = Path(__file__).resolve().parent.parent / 'fixtures.json'
        if not cls.fixtures_path.exists():
            raise FileNotFoundError(
                f"fixtures.json not found at {cls.fixtures_path}"
            )

    def _run_import(self):
        """Run the seed_fixtures management command."""
        from django.core.management import call_command
        from io import StringIO
        out = StringIO()
        call_command(
            'seed_fixtures',
            fixtures=str(self.fixtures_path),
            stdout=out,
        )
        return out.getvalue()

    def test_import_counts(self):
        """All 30 judges, 40 teams, 41 projects import correctly."""
        self._run_import()

        self.assertEqual(
            EventMembership.objects.filter(role=EventRole.JUDGE).count(), 30,
        )
        self.assertEqual(Team.objects.count(), 40)
        self.assertEqual(Project.objects.count(), 41)
        self.assertGreater(JudgeTrackEligibility.objects.count(), 0)

    def test_idempotent_rerun(self):
        """Running import twice produces the same counts (no duplicates)."""
        self._run_import()
        first_judges = EventMembership.objects.filter(role=EventRole.JUDGE).count()
        first_teams = Team.objects.count()
        first_projects = Project.objects.count()

        self._run_import()
        self.assertEqual(
            EventMembership.objects.filter(role=EventRole.JUDGE).count(),
            first_judges,
        )
        self.assertEqual(Team.objects.count(), first_teams)
        self.assertEqual(Project.objects.count(), first_projects)

    def test_duplicate_direction_from_import(self):
        """
        After import, prj_07.is_duplicate_of → prj_41 (not the reverse).
        This is the single most important assertion in the test suite for
        this milestone.
        """
        self._run_import()

        prj_07 = Project.objects.get(external_id='prj_07')
        prj_41 = Project.objects.get(external_id='prj_41')

        # The EARLIER (prj_07) flags itself against the LATER (prj_41)
        self.assertEqual(
            prj_07.is_duplicate_of_id, prj_41.id,
            "prj_07 must flag itself against prj_41 (later = canonical)",
        )
        self.assertIsNotNone(prj_07.duplicate_flag_reason)

        # The LATER (prj_41) must NOT be flagged
        self.assertIsNone(
            prj_41.is_duplicate_of_id,
            "prj_41 (the canonical, later submission) must not be flagged",
        )

    def test_persona_tokens_exist(self):
        """All four persona tokens exist after import."""
        self._run_import()

        from importer.management.commands.seed_fixtures import SEED_TOKENS
        for persona, raw_token in SEED_TOKENS.items():
            token_hash = AuthToken.hash_token(raw_token)
            self.assertTrue(
                AuthToken.objects.filter(token_hash=token_hash).exists(),
                f"Token for {persona} not found after import",
            )
