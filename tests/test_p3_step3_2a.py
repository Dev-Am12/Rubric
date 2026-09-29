import json
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import Client, TestCase
from django.utils import timezone

from accounts.actors import Actor, PermissionDenied
from accounts.models import AuthToken, EventMembership, EventRole, User
from events import services as event_services
from events.models import Event, Prize, Track
from judging.models import JudgeAssignment, JudgeInvite
from services import judging as judging_services
from submissions import services as submission_services
from submissions.models import Project
from submissions.url_validation import validate_external_url
from teams.models import Team


class SafeProjectURLTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_fixtures', stdout=StringIO())
        cls.event = Event.objects.get(external_id='evt_01')
        cls.project = Project.objects.get(external_id='prj_09')
        cls.team = cls.project.team
        cls.user = cls.team.memberships.select_related('user').first().user
        cls.actor = Actor(cls.user, cls.event)
        cls.judge = User.objects.get(external_id='jdg_07')
        cls.assignment = JudgeAssignment.objects.get(event=cls.event, project=cls.project, judge=cls.judge)

    def setUp(self):
        self.event.submissions_close_at = timezone.now() + timedelta(days=5)
        self.event.save(update_fields=['submissions_close_at'])

    def test_service_rejects_unsafe_url_schemes_and_obfuscations(self):
        malicious = (
            'javascript:alert(1)',
            '  JaVaScRiPt:alert(1)',
            'java\tscript:alert(1)',
            'data:text/html,boom',
            'vbscript:msgbox(1)',
            '//example.org/path',
        )
        for field in ('repo_url', 'demo_video_url', 'live_url'):
            for value in malicious:
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(ValueError, field):
                        self._create_with_url(field, value)

    def test_service_strips_valid_urls_and_checks_length_and_whitespace(self):
        self.assertEqual(validate_external_url('repo_url', '  HTTPS://example.org/repo  '), 'HTTPS://example.org/repo')
        self.assertEqual(validate_external_url('repo_url', ''), '')
        with self.assertRaisesRegex(ValueError, 'repo_url'):
            validate_external_url('repo_url', 'https://example.org/a b')
        with self.assertRaisesRegex(ValueError, 'live_url'):
            validate_external_url('live_url', 'https://' + ('a' * 1025) + '.org')

    def test_create_and_update_surfaces_invalid_urls_without_writing_them(self):
        with self.assertRaisesRegex(ValueError, 'live_url'):
            self._create_with_url('live_url', 'javascript:alert(1)')

        admin = User.objects.create_user('url-admin@example.org', is_site_admin=True)
        admin_actor = Actor(admin, self.event)
        with self.assertRaisesRegex(ValueError, 'repo_url'):
            submission_services.update(admin_actor, self.project.pk, repo_url='data:text/html,x')
        self.project.refresh_from_db()
        self.assertNotEqual(self.project.repo_url, 'data:text/html,x')

    def _create_with_url(self, field, value):
        return submission_services.create(
            self.actor,
            self.team,
            self.event.tracks.first(),
            'URL validation test',
            'Test summary',
            **{field: value},
        )

    def test_json_path_returns_400_and_form_path_shows_field_error(self):
        _, token = AuthToken.create_token(self.user)
        client = Client()
        response = client.post(
            '/projects/new',
            data=json.dumps({'title': 'Unsafe', 'repo_url': 'javascript:alert(1)'}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('repo_url', response.json()['detail'])

        form = client.post(
            '/projects/new',
            {'title': 'Unsafe', 'repo_url': 'javascript:alert(1)'},
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        self.assertEqual(form.status_code, 400)
        self.assertContains(form, 'repo_url: must be an absolute HTTP or HTTPS URL', status_code=400)

    def test_fixture_urls_still_import_and_direct_orm_payload_renders_no_link(self):
        call_command('seed_fixtures', stdout=StringIO())
        self.project.refresh_from_db()
        self.assertTrue(self.project.repo_url.startswith('https://'))
        self.project.repo_url = 'javascript:alert(1)'
        self.project.demo_video_url = 'data:text/html,boom'
        self.project.live_url = 'vbscript:msgbox(1)'
        self.project.save(update_fields=['repo_url', 'demo_video_url', 'live_url'])

        _, token = AuthToken.create_token(self.judge)
        client = Client()
        detail = client.get(f'/projects/{self.project.pk}')
        ballot = client.get(
            f'/judge/ballots/{self.assignment.pk}',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        for response in (detail, ballot):
            self.assertEqual(response.status_code, 200)
            body = response.content.decode()
            self.assertNotIn('href="javascript:', body)
            self.assertNotIn('href="data:', body)
            self.assertNotIn('href="vbscript:', body)

    def test_judge_ballot_renders_live_url_from_the_model_field(self):
        self.project.live_url = 'https://demo.example.org/app'
        self.project.save(update_fields=['live_url'])
        _, token = AuthToken.create_token(self.judge)
        response = Client().get(
            f'/judge/ballots/{self.assignment.pk}',
            HTTP_AUTHORIZATION=f'Bearer {token}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'https://demo.example.org/app')
        self.assertContains(response, 'Live Site')


class EventRoleIsolationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_fixtures', stdout=StringIO())
        cls.event_a = Event.objects.get(external_id='evt_01')
        cls.organizer_a = User.objects.create_user('ordinary-organizer-a@example.org')
        EventMembership.objects.create(
            event=cls.event_a,
            user=cls.organizer_a,
            role=EventRole.ORGANIZER,
        )
        cls.judge_a = User.objects.get(external_id='jdg_07')
        cls.assignment_a = JudgeAssignment.objects.filter(event=cls.event_a, judge=cls.judge_a).order_by('pk').first()

    def setUp(self):
        Event.objects.filter(is_current=True).update(is_current=False)
        self.event_a.is_current = True
        self.event_a.save(update_fields=['is_current'])
        self.event_b = Event.objects.create(
            name='Event B', slug='event-b',
            submissions_close_at=timezone.now() + timedelta(days=10),
            is_current=False,
        )
        self.track_b = Track.objects.create(event=self.event_b, name='Track B')
        self.prize_b = Prize.objects.create(event=self.event_b, rank_label='First')
        self.organizer_b = User.objects.create_user('organizer-b@example.org')
        EventMembership.objects.create(event=self.event_b, user=self.organizer_b, role=EventRole.ORGANIZER)
        self.site_admin = User.objects.create_user('site-admin@example.org', is_site_admin=True)
        self.token_a = self._token(self.organizer_a)
        self.token_b = self._token(self.organizer_b)
        self.token_admin = self._token(self.site_admin)
        self.token_judge_a = self._token(self.judge_a)

    @staticmethod
    def _token(user):
        return AuthToken.create_token(user)[1]

    def test_event_a_organizer_cannot_mutate_event_b_or_switch_to_it(self):
        actor_a = Actor(self.organizer_a, self.event_a)
        self.assertFalse(EventMembership.objects.filter(
            event=self.event_b, user=self.organizer_a, role=EventRole.ORGANIZER,
        ).exists())
        with self.assertRaises(PermissionDenied):
            event_services.update_event(actor_a, self.event_b, name='forbidden')
        with self.assertRaises(PermissionDenied):
            event_services.create_track(actor_a, event=self.event_b, name='forbidden')
        with self.assertRaises(PermissionDenied):
            event_services.create_prize(actor_a, event=self.event_b, rank_label='forbidden')
        with self.assertRaises(PermissionDenied):
            event_services.update_track(actor_a, self.track_b, name='forbidden')
        with self.assertRaises(PermissionDenied):
            event_services.update_prize(actor_a, self.prize_b, description='forbidden')
        with self.assertRaises(PermissionDenied):
            event_services.set_current_event(actor_a, self.event_b)
        denied_http = Client().post(
            f'/organizer/events/{self.event_b.pk}/tracks',
            {'name': 'route forbidden'},
            HTTP_AUTHORIZATION=f'Bearer {self.token_a}',
        )
        self.assertEqual(denied_http.status_code, 403)
        self.event_b.refresh_from_db()
        self.assertEqual(self.event_b.name, 'Event B')
        self.assertFalse(self.event_b.is_current)
        self.assertFalse(self.event_b.tracks.filter(name='forbidden').exists())

    def test_event_b_organizer_can_edit_b_while_a_is_current_and_admin_can_too(self):
        actor_b = Actor(self.organizer_b, self.event_b)
        event_services.update_event(actor_b, self.event_b, name='B updated')
        track = event_services.create_track(actor_b, event=self.event_b, name='B second track')
        prize = event_services.create_prize(actor_b, event=self.event_b, rank_label='First')
        event_services.update_track(actor_b, track, name='B renamed')
        event_services.update_prize(actor_b, prize, description='B prize')
        self.assertEqual(Track.objects.get(pk=track.pk).name, 'B renamed')

        response = Client().post(
            f'/organizer/events/{self.event_b.pk}/dates',
            {
                'name': 'B changed over HTTP',
                'slug': self.event_b.slug,
                'submissions_open_at': '',
                'submissions_close_at': self.event_b.submissions_close_at.isoformat(),
                'voting_opens_at': '',
                'voting_closes_at': '',
                'voting_access': 'OPEN',
                'votes_per_voter': '',
            },
            HTTP_AUTHORIZATION=f'Bearer {self.token_b}',
        )
        self.assertEqual(response.status_code, 302)
        self.event_b.refresh_from_db()
        self.assertEqual(self.event_b.name, 'B changed over HTTP')

        admin_actor = Actor(self.site_admin, self.event_a)
        event_services.update_event(admin_actor, self.event_b, name='Admin updated')
        event_services.update_track(admin_actor, track, name='Admin track')
        event_services.update_prize(admin_actor, prize, description='Admin prize')
        self.assertEqual(Event.objects.get(pk=self.event_b.pk).name, 'Admin updated')
        self.assertTrue(Event.objects.get(pk=self.event_a.pk).is_current)
        self.assertFalse(Event.objects.get(pk=self.event_b.pk).is_current)
        event_services.set_current_event(admin_actor, self.event_b)
        self.assertTrue(Event.objects.get(pk=self.event_b.pk).is_current)

    def test_event_creation_and_switching_do_not_copy_or_grant_other_memberships(self):
        actor_a = Actor(self.organizer_a, self.event_a)
        count_before = EventMembership.objects.count()
        new_event = event_services.create_event(
            actor_a,
            name='New Event',
            slug='new-event-no-copied-members',
            submissions_close_at=timezone.now() + timedelta(days=10),
        )
        new_memberships = list(EventMembership.objects.filter(event=new_event))
        self.assertEqual(len(new_memberships), 1)
        self.assertEqual(new_memberships[0].user_id, self.organizer_a.pk)
        self.assertEqual(new_memberships[0].role, EventRole.ORGANIZER)
        self.assertEqual(EventMembership.objects.filter(event=new_event, user=self.judge_a).count(), 0)
        after_create_count = EventMembership.objects.count()
        self.assertEqual(after_create_count, count_before + 1)

        admin_actor = Actor(self.site_admin, self.event_a)
        event_services.set_current_event(admin_actor, new_event)
        self.assertEqual(EventMembership.objects.count(), after_create_count)
        self.assertEqual(EventMembership.objects.filter(event=new_event, user=self.judge_a).count(), 0)

    def test_judge_a_is_isolated_while_b_is_current_and_access_returns_on_a(self):
        Event.objects.filter(is_current=True).update(is_current=False)
        Event.objects.filter(pk=self.event_b.pk).update(is_current=True)
        client = Client()
        headers = {'HTTP_AUTHORIZATION': f'Bearer {self.token_judge_a}'}
        scores_url = '/api/judge/scores'
        judge_ballot_url = f'/judge/ballots/{self.assignment_a.pk}'
        submit_url = f'/api/v1/ballots/{self.assignment_a.pk}'

        self.assertEqual(client.get('/judge/queue', **headers).status_code, 403)
        self.assertEqual(client.get(judge_ballot_url, **headers).status_code, 403)
        self.assertEqual(client.get(scores_url, **headers).status_code, 403)
        denied_submit = client.post(submit_url, data='{"scores":{}}', content_type='application/json', **headers)
        self.assertEqual(denied_submit.status_code, 403)

        Event.objects.filter(pk=self.event_b.pk).update(is_current=False)
        Event.objects.filter(pk=self.event_a.pk).update(is_current=True)
        self.assertEqual(client.get('/judge/queue', **headers).status_code, 200)
        self.assertEqual(client.get(judge_ballot_url, **headers).status_code, 200)
        self.assertEqual(client.get(scores_url, **headers).status_code, 200)
        criterion_scores = {
            str(criterion.pk): '3'
            for criterion in self.event_a.rubrics.first().criteria.all()
        }
        allowed_submit = client.post(
            submit_url,
            data=json.dumps({'scores': criterion_scores}),
            content_type='application/json',
            **headers,
        )
        self.assertEqual(allowed_submit.status_code, 200)

    def test_event_a_judge_invite_and_team_code_cannot_cross_into_current_event_b(self):
        organizer_actor = Actor(self.organizer_a, self.event_a)
        invitee = User.objects.create_user('cross-event-invitee@example.org')
        EventMembership.objects.create(event=self.event_b, user=invitee, role=EventRole.PARTICIPANT)
        invite, raw_token = judging_services.create_judge_invite(
            organizer_actor, self.event_a, invitee.email,
        )
        team = Team.objects.filter(event=self.event_a).first()
        _, invitee_token = AuthToken.create_token(invitee)
        Event.objects.filter(is_current=True).update(is_current=False)
        Event.objects.filter(pk=self.event_b.pk).update(is_current=True)
        client = Client()
        headers = {'HTTP_AUTHORIZATION': f'Bearer {invitee_token}'}

        invite_response = client.get(f'/invite/judge/{raw_token}', **headers)
        self.assertEqual(invite_response.status_code, 400)
        self.assertIn('different event', invite_response.content.decode().lower())
        self.assertIsNone(JudgeInvite.objects.get(pk=invite.pk).accepted_at)

        team_response = client.get(f'/teams/join/{team.invite_code}', **headers)
        self.assertEqual(team_response.status_code, 403)
        self.assertFalse(team.memberships.filter(user=invitee).exists())
