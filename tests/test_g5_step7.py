"""
Tests for G5.7: Event management, current-event model, landing page, and organizer bootstrap.

Covers:
1. Current event isolation & zero cross-event leakage:
   - Creating a second event leaves fixture event gallery, judge queue, dashboard, and CSV export unchanged.
   - Switching scopes all of them to the new event with zero cross-event leakage.
   - Switching back restores fixture scope.
2. Partial unique constraint on Event.is_current:
   - At most one event can have is_current=True.
   - Multiple events can have is_current=False.
3. Deadline enforcement:
   - Moving submissions_close_at into past makes the real submit path refuse with 403.
4. Organizer bootstrap management command:
   - `manage.py create_organizer` creates user, sets password, marks site admin and organizer,
     records audit log entry, and allows successful login.
5. Date validation:
   - close > open validated for both submission and voting dates.
   - Naive datetimes rejected with ValueError.
6. Authz coverage:
   - All new routes tested across all six personas (anon, participant, judge_a, judge_b,
     judge_unassigned, organizer).
"""

from datetime import datetime, timedelta, timezone as dt_timezone
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.utils import timezone

from accounts.actors import Actor
from accounts.models import AuthToken, EventMembership, EventRole, User
from audit.models import AuditLogEntry
from events.models import Event, Track, Prize
from events import services as events_services
from importer.management.commands.seed_fixtures import SEED_TOKENS
from submissions.models import Project, ProjectStatus
from teams.models import Team, TeamMembership


class EventIsolationAndSwitchingTests(TestCase):
    """
    Test that creating a second event without switching leaves all fixture
    surfaces unchanged, and switching cleanly scopes all surfaces to the new event.
    """

    def setUp(self):
        call_command('seed_fixtures')
        self.fixture_event = Event.objects.get(external_id='evt_01')
        self.assertTrue(self.fixture_event.is_current)

        self.org_token = SEED_TOKENS['organizer']
        self.judge_token = SEED_TOKENS['judge_a']
        self.client = Client()

    def test_create_second_event_leaves_existing_surfaces_unchanged(self):
        # 1. Baseline counts for fixture event
        resp_gallery = self.client.get('/projects')
        self.assertEqual(resp_gallery.status_code, 200)
        # 40 projects visible in public gallery (41 total minus 1 duplicate)
        self.assertEqual(len(resp_gallery.context['projects']), 40)

        resp_queue = self.client.get('/judge/queue', HTTP_AUTHORIZATION=f'Bearer {self.judge_token}')
        self.assertEqual(resp_queue.status_code, 200)
        initial_queue_count = len(resp_queue.context['assignments'])
        self.assertGreater(initial_queue_count, 0)

        resp_dash = self.client.get('/organizer', HTTP_AUTHORIZATION=f'Bearer {self.org_token}')
        self.assertEqual(resp_dash.status_code, 200)
        self.assertEqual(resp_dash.context['total_projects'], 41)

        resp_csv = self.client.get('/api/export.csv', HTTP_AUTHORIZATION=f'Bearer {self.org_token}')
        self.assertEqual(resp_csv.status_code, 200)
        csv_lines = resp_csv.content.decode('utf-8').strip().split('\n')
        self.assertEqual(len(csv_lines), 42)  # 1 header + 41 rows

        # 2. Organizer creates second event without switching
        org_user = User.objects.get(email='organizer@rubric.local')
        org_actor = Actor(org_user, self.fixture_event)

        now = timezone.now()
        new_event = events_services.create_event(
            org_actor,
            name="Winter Hackathon 2027",
            slug="winter-2027",
            submissions_open_at=now,
            submissions_close_at=now + timedelta(days=7),
            voting_opens_at=now + timedelta(days=7),
            voting_closes_at=now + timedelta(days=10),
        )

        self.assertFalse(new_event.is_current)
        self.fixture_event.refresh_from_db()
        self.assertTrue(self.fixture_event.is_current)

        # 3. Verify all surfaces remain identical
        resp_gallery2 = self.client.get('/projects')
        self.assertEqual(len(resp_gallery2.context['projects']), 40)

        resp_queue2 = self.client.get('/judge/queue', HTTP_AUTHORIZATION=f'Bearer {self.judge_token}')
        self.assertEqual(len(resp_queue2.context['assignments']), initial_queue_count)

        resp_dash2 = self.client.get('/organizer', HTTP_AUTHORIZATION=f'Bearer {self.org_token}')
        self.assertEqual(resp_dash2.context['total_projects'], 41)

        resp_csv2 = self.client.get('/api/export.csv', HTTP_AUTHORIZATION=f'Bearer {self.org_token}')
        self.assertEqual(resp_csv2.content, resp_csv.content)

        # 4. Now explicitly switch to the new event
        events_services.set_current_event(org_actor, new_event)
        new_event.refresh_from_db()
        self.fixture_event.refresh_from_db()
        self.assertTrue(new_event.is_current)
        self.assertFalse(self.fixture_event.is_current)

        # 5. Surfaces are now scoped to new event: 0 projects, 0 queue items, empty CSV
        resp_gallery_new = self.client.get('/projects')
        self.assertEqual(len(resp_gallery_new.context['projects']), 0)

        # judge_a is not enrolled in the new event -> 403 forbidden
        resp_queue_no_role = self.client.get('/judge/queue', HTTP_AUTHORIZATION=f'Bearer {self.judge_token}')
        self.assertEqual(resp_queue_no_role.status_code, 403)

        # Enrolling judge_a in new event gives 200 with 0 assignments
        judge_user = User.objects.get(external_id='jdg_07')
        EventMembership.objects.create(event=new_event, user=judge_user, role=EventRole.JUDGE)
        resp_queue_new = self.client.get('/judge/queue', HTTP_AUTHORIZATION=f'Bearer {self.judge_token}')
        self.assertEqual(resp_queue_new.status_code, 200)
        self.assertEqual(len(resp_queue_new.context['assignments']), 0)

        resp_dash_new = self.client.get('/organizer', HTTP_AUTHORIZATION=f'Bearer {self.org_token}')
        self.assertEqual(resp_dash_new.context['total_projects'], 0)

        resp_csv_new = self.client.get('/api/export.csv', HTTP_AUTHORIZATION=f'Bearer {self.org_token}')
        csv_new_lines = resp_csv_new.content.decode('utf-8').strip().split('\n')
        self.assertEqual(len(csv_new_lines), 1)  # header only, zero projects leaked

        # 6. Switch back to fixture event
        events_services.set_current_event(org_actor, self.fixture_event)
        self.fixture_event.refresh_from_db()
        self.assertTrue(self.fixture_event.is_current)

        resp_gallery_back = self.client.get('/projects')
        self.assertEqual(len(resp_gallery_back.context['projects']), 40)


class PartialUniqueConstraintTests(TestCase):
    """
    Test that at most one event can have is_current=True simultaneously.
    """

    def test_partial_unique_constraint_enforces_single_current_event(self):
        now = timezone.now()
        Event.objects.create(
            name="First Current",
            slug="first-current",
            is_current=True,
            submissions_close_at=now + timedelta(days=1),
        )

        # Creating another event with is_current=True violates the partial unique constraint
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Event.objects.create(
                    name="Second Current",
                    slug="second-current",
                    is_current=True,
                    submissions_close_at=now + timedelta(days=1),
                )

        # Multiple events with is_current=False must be permitted
        e3 = Event.objects.create(
            name="Non-current 1",
            slug="non-current-1",
            is_current=False,
            submissions_close_at=now + timedelta(days=1),
        )
        e4 = Event.objects.create(
            name="Non-current 2",
            slug="non-current-2",
            is_current=False,
            submissions_close_at=now + timedelta(days=1),
        )
        self.assertFalse(e3.is_current)
        self.assertFalse(e4.is_current)


class DeadlineEnforcementTests(TestCase):
    """
    Test that moving the submission close date into the past causes
    the real submit path to reject submissions with 403.
    """

    def setUp(self):
        call_command('seed_fixtures')
        self.event = Event.objects.get(external_id='evt_01')
        self.part_token = SEED_TOKENS['participant']
        self.client = Client()

    def test_past_close_date_refuses_submission(self):
        # Move submissions_close_at into past
        self.event.submissions_close_at = timezone.now() - timedelta(minutes=30)
        self.event.save()

        # HTML form POST
        response = self.client.post(
            '/projects/new',
            {
                'title': 'Late Hack Submission',
                'summary': 'Should be rejected',
            },
            HTTP_AUTHORIZATION=f'Bearer {self.part_token}',
        )
        self.assertEqual(response.status_code, 403)

        # JSON POST
        response_json = self.client.post(
            '/projects/new',
            data='{"title": "Late API Submission", "summary": "Rejected"}',
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {self.part_token}',
        )
        self.assertEqual(response_json.status_code, 403)


class OrganizerBootstrapCommandTests(TestCase):
    """
    Test `manage.py create_organizer` command.
    """

    def setUp(self):
        call_command('seed_fixtures')
        self.event = Event.objects.get(external_id='evt_01')

    def test_bootstrap_organizer_success(self):
        email = 'superorganizer@example.com'
        password = 'BootstrapPassword2026!'
        name = 'Super Organizer'

        call_command('create_organizer', email=email, password=password, name=name)

        user = User.objects.get(email=email)
        self.assertEqual(user.display_name, name)
        self.assertTrue(user.check_password(password))
        self.assertTrue(user.is_site_admin)

        membership = EventMembership.objects.get(user=user, event=self.event)
        self.assertEqual(membership.role, EventRole.ORGANIZER)

        # Check audit entry was created
        audit_entry = AuditLogEntry.objects.filter(action='organizer.bootstrap', target_id=str(user.pk)).first()
        self.assertIsNotNone(audit_entry)
        self.assertEqual(audit_entry.payload['email'], email)

        # Verify new organizer can log in via credentials
        client = Client()
        login_resp = client.post('/login', {'email': email, 'password': password})
        self.assertEqual(login_resp.status_code, 302)
        self.assertIn('session', client.cookies)


class DateValidationTests(TestCase):
    """
    Test validation on create_event and update_event:
    reject naive datetimes and validate close > open.
    """

    def setUp(self):
        self.user = User.objects.create_user(email='org_val@test.org', is_site_admin=True)
        self.actor = Actor(self.user)

    def test_reject_naive_datetime(self):
        naive_dt = datetime(2027, 5, 1, 10, 0, 0)  # No tzinfo
        with self.assertRaises(ValueError) as cm:
            events_services.create_event(
                self.actor,
                name="Naive Event",
                submissions_open_at=naive_dt,
            )
        self.assertIn("Naive datetimes are not allowed", str(cm.exception))

    def test_reject_submissions_close_before_open(self):
        now = timezone.now()
        with self.assertRaises(ValueError) as cm:
            events_services.create_event(
                self.actor,
                name="Backwards Submissions Event",
                submissions_open_at=now + timedelta(days=2),
                submissions_close_at=now + timedelta(days=1),
            )
        self.assertIn("Submissions close date must be after submissions open date", str(cm.exception))

    def test_reject_voting_close_before_open(self):
        now = timezone.now()
        with self.assertRaises(ValueError) as cm:
            events_services.create_event(
                self.actor,
                name="Backwards Voting Event",
                voting_opens_at=now + timedelta(days=5),
                voting_closes_at=now + timedelta(days=3),
            )
        self.assertIn("Voting close date must be after voting open date", str(cm.exception))


class LandingPageViewTests(TestCase):
    """
    Test public landing page `/`.
    """

    def setUp(self):
        call_command('seed_fixtures')
        self.client = Client()

    def test_landing_page_renders_current_event_details(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('event', resp.context)
        self.assertEqual(resp.context['event'].external_id, 'evt_01')
        self.assertGreater(len(resp.context['tracks']), 0)
        self.assertIn('submissions_status', resp.context)
        self.assertIn('/projects', resp.content.decode('utf-8'))
        self.assertIn('/accounts/register', resp.content.decode('utf-8'))
        self.assertIn('/login', resp.content.decode('utf-8'))


class AuthzMatrixSixPersonasTests(TestCase):
    """
    Verify all new routes against all six personas:
    1. anon
    2. participant
    3. judge_a
    4. judge_b
    5. judge_unassigned
    6. organizer
    """

    def setUp(self):
        call_command('seed_fixtures')
        self.event = Event.objects.get(external_id='evt_01')
        self.track = self.event.tracks.first()
        self.prize = self.event.prizes.first() or Prize.objects.create(
            event=self.event,
            rank_label="1st Place",
            description="Overall Winner",
        )

        # Create unassigned judge persona
        unassigned_user = User.objects.create_user(
            email='judge_unassigned@rubric.test',
            display_name='Unassigned Judge',
        )
        EventMembership.objects.create(
            user=unassigned_user,
            event=self.event,
            role=EventRole.JUDGE,
        )
        _, self.unassigned_token = AuthToken.create_token(unassigned_user, label='unassigned_judge')

        self.tokens = {
            'anon': None,
            'participant': SEED_TOKENS['participant'],
            'judge_a': SEED_TOKENS['judge_a'],
            'judge_b': SEED_TOKENS['judge_b'],
            'judge_unassigned': self.unassigned_token,
            'organizer': SEED_TOKENS['organizer'],
        }
        self.client = Client()

    def _req(self, persona, method, path, data=None):
        headers = {}
        token = self.tokens[persona]
        if token:
            headers['HTTP_AUTHORIZATION'] = f'Bearer {token}'
        if method == 'GET':
            return self.client.get(path, **headers)
        elif method == 'POST':
            return self.client.post(path, data or {}, **headers)

    def test_landing_page_accessible_to_all_personas(self):
        for persona in self.tokens:
            resp = self._req(persona, 'GET', '/')
            self.assertEqual(resp.status_code, 200, f"Failed for {persona}")

    def test_organizer_events_list_authz(self):
        for persona, token in self.tokens.items():
            resp = self._req(persona, 'GET', '/organizer/events')
            if persona == 'organizer':
                self.assertEqual(resp.status_code, 200)
            elif persona == 'anon':
                self.assertEqual(resp.status_code, 401)
            else:
                self.assertEqual(resp.status_code, 403, f"Expected 403 for {persona}, got {resp.status_code}")

    def test_organizer_event_dates_authz(self):
        path = f'/organizer/events/{self.event.pk}/dates'
        for persona in self.tokens:
            resp = self._req(persona, 'GET', path)
            if persona == 'organizer':
                self.assertEqual(resp.status_code, 200)
            elif persona == 'anon':
                self.assertEqual(resp.status_code, 401)
            else:
                self.assertEqual(resp.status_code, 403)

    def test_organizer_event_tracks_authz(self):
        path = f'/organizer/events/{self.event.pk}/tracks'
        for persona in self.tokens:
            resp = self._req(persona, 'GET', path)
            if persona == 'organizer':
                self.assertEqual(resp.status_code, 200)
            elif persona == 'anon':
                self.assertEqual(resp.status_code, 401)
            else:
                self.assertEqual(resp.status_code, 403)

    def test_organizer_event_track_edit_authz(self):
        path = f'/organizer/events/{self.event.pk}/tracks/{self.track.pk}'
        for persona in self.tokens:
            resp = self._req(persona, 'POST', path, {'name': 'Updated Track'})
            if persona == 'organizer':
                self.assertEqual(resp.status_code, 302)
            elif persona == 'anon':
                self.assertEqual(resp.status_code, 401)
            else:
                self.assertEqual(resp.status_code, 403)

    def test_organizer_event_prizes_authz(self):
        path = f'/organizer/events/{self.event.pk}/prizes'
        for persona in self.tokens:
            resp = self._req(persona, 'GET', path)
            if persona == 'organizer':
                self.assertEqual(resp.status_code, 200)
            elif persona == 'anon':
                self.assertEqual(resp.status_code, 401)
            else:
                self.assertEqual(resp.status_code, 403)

    def test_organizer_event_prize_edit_authz(self):
        path = f'/organizer/events/{self.event.pk}/prizes/{self.prize.pk}'
        for persona in self.tokens:
            resp = self._req(persona, 'POST', path, {'rank_label': '1st Place Special'})
            if persona == 'organizer':
                self.assertEqual(resp.status_code, 302)
            elif persona == 'anon':
                self.assertEqual(resp.status_code, 401)
            else:
                self.assertEqual(resp.status_code, 403)

    def test_organizer_event_make_current_authz(self):
        path = f'/organizer/events/{self.event.pk}/make-current'
        for persona in self.tokens:
            resp = self._req(persona, 'POST', path)
            if persona == 'organizer':
                self.assertEqual(resp.status_code, 302)
            elif persona == 'anon':
                self.assertEqual(resp.status_code, 401)
            else:
                self.assertEqual(resp.status_code, 403)
