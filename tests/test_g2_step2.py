"""
Tests for G2 Step 2:
  1. Gallery is genuinely public and anonymous-readable
  2. Fixture project title (from real fixtures.json) appears in the gallery response body
  3. Draft is never visible to a non-owner (anonymous -> 401, non-owner -> 403, owner -> 200)
  4. Project detail view shows metadata, status, links, and duplicate flag when set
  5. Closed event shows honest "submissions are closed" state on /projects/new and /projects/{id}/edit
  6. /my/submissions shows participant's own team projects and duplicate-flag banner for tm_07
  7. Gallery HTMX/search filtering by q and track
"""

import json
from datetime import timedelta
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase, Client
from django.utils import timezone

from accounts.actors import Actor, AnonymousActor
from accounts.models import AuthToken, EventMembership, EventRole, User
from events.models import Event, Track
from submissions.models import Project, ProjectStatus
from submissions.services import create as create_submission, submit as submit_submission
from teams.models import Team, TeamMembership


class GalleryPublicTest(TestCase):
    """
    Test 1: Gallery is genuinely public and anonymous-readable,
    and all submitted projects appear without pagination.
    """

    def setUp(self):
        self.client = Client()
        self.event = Event.objects.create(
            slug='gallery-test',
            name='Gallery Test Event',
            submissions_close_at=timezone.now() + timedelta(days=7),
        )
        self.track = Track.objects.create(
            event=self.event,
            name='Developer Tools',
            external_id='trk_dev',
        )
        self.user = User.objects.create_user(
            email='alice@example.org',
            display_name='Alice Submitter',
        )
        self.team = Team.objects.create(
            event=self.event,
            name='Alpha Team',
            invite_code='alpha-team',
            created_by=self.user,
        )
        TeamMembership.objects.create(team=self.team, user=self.user)
        self.actor = Actor(user=self.user, event=self.event)

    def test_gallery_is_public_and_anonymous_readable(self):
        """Gallery (/projects) responds with 200 OK for anonymous requests."""
        response = self.client.get('/projects')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Project Gallery')

    def test_gallery_displays_submitted_projects(self):
        """Submitted projects display title, summary, track, and team on one page."""
        p1 = create_submission(
            self.actor, self.team, self.track,
            title='Project Alpha One',
            summary='First test summary for Alpha Team',
        )
        submit_submission(self.actor, p1.id)

        response = self.client.get('/projects')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Project Alpha One')
        self.assertContains(response, 'First test summary for Alpha Team')
        self.assertContains(response, 'Developer Tools')
        self.assertContains(response, 'Alpha Team')

    def test_gallery_filters_by_query_and_track(self):
        """Gallery can filter projects by keyword and track."""
        p1 = create_submission(
            self.actor, self.team, self.track,
            title='Quantum Compiler',
            summary='Fast quantum tools',
        )
        submit_submission(self.actor, p1.id)

        track2 = Track.objects.create(
            event=self.event,
            name='Security Track',
            external_id='trk_sec',
        )
        p2 = create_submission(
            self.actor, self.team, track2,
            title='Cipher Shield',
            summary='Advanced encryption tool',
        )
        submit_submission(self.actor, p2.id)

        # Search by query
        resp_q = self.client.get('/projects?q=Quantum')
        self.assertContains(resp_q, 'Quantum Compiler')
        self.assertNotContains(resp_q, 'Cipher Shield')

        # Filter by track
        resp_track = self.client.get('/projects?track=trk_sec')
        self.assertContains(resp_track, 'Cipher Shield')
        self.assertNotContains(resp_track, 'Quantum Compiler')


class FixtureProjectShownInGalleryTest(TestCase):
    """
    Test 2: Real fixture project titles appear in the gallery response body.
    Loads fixtures.json and confirms seeded projects render in /projects.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Seed the full fixture data into test database
        call_command('seed_fixtures')

    def test_fixture_projects_appear_in_gallery(self):
        """A real fixture project title appears in the gallery response body."""
        client = Client()
        response = client.get('/projects')
        self.assertEqual(response.status_code, 200)

        # Real project titles from fixtures.json
        content = response.content.decode('utf-8')
        # Check known fixture titles
        fixture_titles = ['Glass Signal', 'Small Meadow', 'Deep Compass', 'Dry Harbour']
        found = [t for t in fixture_titles if t in content]
        self.assertTrue(
            len(found) > 0,
            f"Expected at least one of {fixture_titles} in gallery body, found none."
        )


class DraftVisibilityTest(TestCase):
    """
    Test 3: A draft is never visible to a non-owner.
    - Anonymous viewing draft -> 401
    - Non-owner participant viewing draft -> 403
    - Owner participant viewing draft -> 200
    - Organizer viewing draft -> 200
    - Draft excluded from public gallery
    """

    def setUp(self):
        self.client = Client()
        self.event = Event.objects.create(
            slug='draft-test',
            name='Draft Test Event',
            submissions_close_at=timezone.now() + timedelta(days=7),
        )
        self.track = Track.objects.create(
            event=self.event,
            name='General Track',
        )
        # Owner
        self.owner = User.objects.create_user(
            email='owner@example.org',
            display_name='Owner User',
        )
        EventMembership.objects.create(
            event=self.event, user=self.owner,
            role=EventRole.PARTICIPANT,
        )
        self.team = Team.objects.create(
            event=self.event, name='Owner Team',
            invite_code='owner-team', created_by=self.owner,
        )
        TeamMembership.objects.create(team=self.team, user=self.owner)
        _, self.owner_token = AuthToken.create_token(self.owner, label='owner-token')
        self.owner_actor = Actor(user=self.owner, event=self.event)

        # Non-owner participant
        self.other_user = User.objects.create_user(
            email='stranger@example.org',
            display_name='Stranger User',
        )
        EventMembership.objects.create(
            event=self.event, user=self.other_user,
            role=EventRole.PARTICIPANT,
        )
        _, self.other_token = AuthToken.create_token(self.other_user, label='stranger-token')

        # Organizer
        self.organizer = User.objects.create_user(
            email='organizer@example.org',
            display_name='Event Organizer',
        )
        EventMembership.objects.create(
            event=self.event, user=self.organizer,
            role=EventRole.ORGANIZER,
        )
        _, self.org_token = AuthToken.create_token(self.organizer, label='org-token')

        # Create draft project
        self.draft = create_submission(
            self.owner_actor, self.team, self.track,
            title='Top Secret Draft',
            summary='Confidential project not yet submitted',
        )

    def test_anonymous_cannot_view_draft(self):
        """Anonymous actor accessing draft gets 401."""
        response = self.client.get(f'/projects/{self.draft.id}')
        self.assertEqual(response.status_code, 401)

    def test_non_owner_participant_cannot_view_draft(self):
        """Non-owner participant accessing draft gets 403."""
        response = self.client.get(
            f'/projects/{self.draft.id}',
            HTTP_AUTHORIZATION=f'Bearer {self.other_token}',
        )
        self.assertEqual(response.status_code, 403)

    def test_owner_can_view_draft(self):
        """Owner participant can view their own draft (200 OK)."""
        response = self.client.get(
            f'/projects/{self.draft.id}',
            HTTP_AUTHORIZATION=f'Bearer {self.owner_token}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Top Secret Draft')
        self.assertContains(response, 'Draft')

    def test_organizer_can_view_draft(self):
        """Organizer can view any draft project (200 OK)."""
        response = self.client.get(
            f'/projects/{self.draft.id}',
            HTTP_AUTHORIZATION=f'Bearer {self.org_token}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Top Secret Draft')

    def test_draft_excluded_from_public_gallery(self):
        """Draft projects never appear in the public gallery."""
        response = self.client.get('/projects')
        self.assertNotContains(response, 'Top Secret Draft')

        # Once submitted, it appears in gallery
        submit_submission(self.owner_actor, self.draft.id)
        response2 = self.client.get('/projects')
        self.assertContains(response2, 'Top Secret Draft')


class ClosedEventSubmissionStateTest(TestCase):
    """
    Test 4 & 5: Submissions deadline enforcement.
    Show a plain, honest "submissions are closed" state if update() rejects
    for a closed event, rather than a generic error page.
    """

    def setUp(self):
        self.client = Client()
        # Event closed in the past
        self.event = Event.objects.create(
            slug='closed-event',
            name='Past Hackathon 2025',
            submissions_close_at=timezone.now() - timedelta(days=30),
        )
        self.track = Track.objects.create(event=self.event, name='Old Track')
        self.user = User.objects.create_user(
            email='late@example.org', display_name='Late Submitter',
        )
        EventMembership.objects.create(
            event=self.event, user=self.user,
            role=EventRole.PARTICIPANT,
        )
        self.team = Team.objects.create(
            event=self.event, name='Late Team',
            invite_code='late-code', created_by=self.user,
        )
        TeamMembership.objects.create(team=self.team, user=self.user)
        _, self.token = AuthToken.create_token(self.user, label='late-tok')
        self.actor = Actor(user=self.user, event=self.event)

        # Existing project created before close
        self.project = Project.objects.create(
            event=self.event, team=self.team, track=self.track,
            title='Existing Project', summary='Created earlier',
            status=ProjectStatus.DRAFT,
        )

    def test_new_submission_page_shows_closed_state(self):
        """GET /projects/new shows honest 'submissions are closed' message."""
        response = self.client.get(
            '/projects/new',
            HTTP_AUTHORIZATION=f'Bearer {self.token}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Submissions are closed')

    def test_post_new_submission_to_closed_event_rejected_with_403(self):
        """POST /projects/new to a closed event rejects with 403."""
        response = self.client.post(
            '/projects/new',
            content_type='application/json',
            data=json.dumps({'title': 'Too Late Project', 'summary': 'Late'}),
            HTTP_AUTHORIZATION=f'Bearer {self.token}',
        )
        self.assertEqual(response.status_code, 403)

    def test_edit_page_on_closed_event_shows_closed_state(self):
        """GET /projects/{id}/edit shows honest 'submissions are closed' state."""
        response = self.client.get(
            f'/projects/{self.project.id}/edit',
            HTTP_AUTHORIZATION=f'Bearer {self.token}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Submissions are closed')

    def test_edit_submission_on_closed_event_shows_honest_error(self):
        """POST /projects/{id}/edit rejects with 403 and renders closed banner."""
        response = self.client.post(
            f'/projects/{self.project.id}/edit',
            data={'title': 'Updated Title', 'summary': 'Updated Summary'},
            HTTP_AUTHORIZATION=f'Bearer {self.token}',
        )
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, 'Submissions are closed', status_code=403)
        self.assertContains(response, 'deadline has passed', status_code=403)


class MySubmissionsViewTest(TestCase):
    """
    Test 6: /my/submissions shows participant's own team's projects,
    and displays the duplicate-flag banner when is_duplicate_of is set.
    """

    def setUp(self):
        call_command('seed_fixtures')
        self.client = Client()
        self.token = 'rubric_seed_participant_tok_3f4e5d6c7b8a'

    def test_my_submissions_requires_auth(self):
        """Anonymous request to /my/submissions is rejected with 401."""
        response = self.client.get('/my/submissions')
        self.assertEqual(response.status_code, 401)

    def test_my_submissions_shows_team_projects_and_duplicate_banner(self):
        """Participant visiting /my/submissions sees their team projects and duplicate banner."""
        response = self.client.get(
            '/my/submissions',
            HTTP_AUTHORIZATION=f'Bearer {self.token}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'My Submissions')
        self.assertContains(response, 'Dry Harbour')

        # Check for duplicate banner on prj_07
        self.assertContains(response, 'Duplicate Submission Flagged')
        self.assertContains(response, 'flagged as a duplicate of')
        self.assertContains(response, 'prj_41')


class GeneralDuplicateDetectorTest(TestCase):
    """
    Test 7: General duplicate-submission detector.
    Tests dynamic detection during submit() without relying on the importer.
    """

    def setUp(self):
        self.event = Event.objects.create(
            slug='dup-detector-test',
            name='Duplicate Detector Event',
            submissions_close_at=timezone.now() + timedelta(days=7),
        )
        self.track = Track.objects.create(
            event=self.event,
            name='Engineering Track',
        )
        self.user = User.objects.create_user(
            email='builder@example.org',
            display_name='Builder User',
        )
        EventMembership.objects.create(
            event=self.event, user=self.user,
            role=EventRole.PARTICIPANT,
        )
        self.team = Team.objects.create(
            event=self.event,
            name='Team Gamma',
            invite_code='gamma-code',
            created_by=self.user,
        )
        TeamMembership.objects.create(team=self.team, user=self.user)
        self.actor = Actor(user=self.user, event=self.event)

    def test_synthetic_near_duplicates_detected_on_submit(self):
        """
        Two synthetic near-duplicate submissions from the same team submitted
        via submissions.services.submit() are automatically detected.
        Earlier submission flags itself against later canonical one.
        """
        # Create earlier draft
        p1 = create_submission(
            self.actor, self.team, self.track,
            title='Project Nebula',
            summary='Initial version of Nebula',
        )
        # Submit earlier project
        submit_submission(self.actor, p1.id)

        # Set submitted_at to earlier time
        p1.refresh_from_db()
        p1.submitted_at = timezone.now() - timedelta(hours=2)
        p1.save(update_fields=['submitted_at'])

        # Create later draft with near-identical title
        p2 = create_submission(
            self.actor, self.team, self.track,
            title='Project Nebula (Final Version)',
            summary='Polished version of Nebula',
        )
        # Submit later project — triggers duplicate detection
        submit_submission(self.actor, p2.id)

        p1.refresh_from_db()
        p2.refresh_from_db()

        # Earlier flags itself against later
        self.assertEqual(p1.is_duplicate_of_id, p2.id)
        self.assertIsNotNone(p1.duplicate_flag_reason)
        self.assertIn('near-identical title', p1.duplicate_flag_reason)
        self.assertIn('Earlier submission flagged against later canonical one', p1.duplicate_flag_reason)

        # Later (canonical) must NOT be flagged
        self.assertIsNone(p2.is_duplicate_of_id)
        self.assertIsNone(p2.duplicate_flag_reason)

    def test_different_projects_from_same_team_never_flagged(self):
        """
        Negative test: Two genuinely different projects from the same team
        are never flagged as duplicates.
        """
        p1 = create_submission(
            self.actor, self.team, self.track,
            title='Solar Power Grid Optimizer',
            summary='Clean energy optimization engine',
        )
        submit_submission(self.actor, p1.id)

        p2 = create_submission(
            self.actor, self.team, self.track,
            title='Genomic Variant Classifier',
            summary='Bioinformatics machine learning tool',
        )
        submit_submission(self.actor, p2.id)

        p1.refresh_from_db()
        p2.refresh_from_db()

        # Neither should be flagged
        self.assertIsNone(p1.is_duplicate_of_id)
        self.assertIsNone(p1.duplicate_flag_reason)
        self.assertIsNone(p2.is_duplicate_of_id)
        self.assertIsNone(p2.duplicate_flag_reason)

    def test_identical_titles_different_teams_never_flagged(self):
        """
        Projects with identical titles from DIFFERENT teams are never flagged.
        """
        other_user = User.objects.create_user(
            email='other_team@example.org', display_name='Other Team User',
        )
        EventMembership.objects.create(
            event=self.event, user=other_user,
            role=EventRole.PARTICIPANT,
        )
        other_team = Team.objects.create(
            event=self.event, name='Team Delta',
            invite_code='delta-code', created_by=other_user,
        )
        TeamMembership.objects.create(team=other_team, user=other_user)
        other_actor = Actor(user=other_user, event=self.event)

        p1 = create_submission(
            self.actor, self.team, self.track,
            title='Smart Traffic Control',
            summary='Team Gamma version',
        )
        submit_submission(self.actor, p1.id)

        p2 = create_submission(
            other_actor, other_team, self.track,
            title='Smart Traffic Control',
            summary='Team Delta version',
        )
        submit_submission(other_actor, p2.id)

        p1.refresh_from_db()
        p2.refresh_from_db()

        self.assertIsNone(p1.is_duplicate_of_id)
        self.assertIsNone(p2.is_duplicate_of_id)
