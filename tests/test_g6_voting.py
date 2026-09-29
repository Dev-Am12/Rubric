import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
import uuid

from django.core.management import call_command
from django.db import IntegrityError, close_old_connections, transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.actors import Actor, AnonymousActor, PermissionDenied
from accounts.models import EventMembership, EventRole, User
from audit.models import AuditLogEntry
from events.models import Event, Track
from submissions.models import Project, ProjectStatus
from teams.models import Team
from voting.models import Comment, Vote, VoteAttempt, VoteAttemptOutcome, VoteMode
from services import voting
from tests.test_g5_audit import AuditTransactionTestCase


TOKENS = {
    'organizer': 'rubric_seed_organizer_tok_9f8e7d6c5b4a',
    'judge': 'rubric_seed_judge_a_tok_1a2b3c4d5e6f',
    'participant': 'rubric_seed_participant_tok_3f4e5d6c7b8a',
}


class VotingFixtureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_fixtures', stdout=StringIO())
        cls.event = Event.objects.get(external_id='evt_01')
        cls.project = Project.objects.get(external_id='prj_41')
        cls.organizer = Actor(User.objects.get(email='organizer@rubric.local'), cls.event)
        participant_user = Team.objects.get(external_id='tm_07').memberships.select_related('user').first().user
        cls.participant = Actor(participant_user, cls.event)
        cls.judge = Actor(User.objects.get(external_id='jdg_07'), cls.event)

    def setUp(self):
        self.event.voting_opens_at = timezone.now() - timedelta(minutes=1)
        self.event.voting_closes_at = timezone.now() + timedelta(hours=1)
        self.event.voting_access = 'OPEN'
        self.event.votes_per_voter = None
        self.event.save(update_fields=['voting_opens_at', 'voting_closes_at', 'voting_access', 'votes_per_voter'])
        self.event.refresh_from_db()
        self.anon = AnonymousActor()
        self.identity = {'fingerprint': 'test-voter-fingerprint'}

    def headers(self, persona):
        return {'HTTP_AUTHORIZATION': f'Bearer {TOKENS[persona]}'}

    def test_v_t1_duplicate_attempt_is_logged_and_only_one_vote_exists(self):
        first = voting.cast(self.anon, self.event, self.project, **self.identity)
        second = voting.cast(self.anon, self.event, self.project, **self.identity)
        self.assertEqual(first.outcome, VoteAttemptOutcome.ACCEPTED)
        self.assertEqual(second.outcome, VoteAttemptOutcome.REJECTED_DUPLICATE)
        self.assertEqual(Vote.objects.filter(event=self.event, project=self.project).count(), 1)
        self.assertEqual(VoteAttempt.objects.filter(event=self.event, project=self.project).count(), 2)

    def test_v_t2_sliding_window_blocks_sixth_attempt(self):
        projects = list(voting.eligible_projects(self.event).exclude(pk=self.project.pk)[:6])
        attempts = [
            voting.cast(self.anon, self.event, project, fingerprint='rate-limit-voter')
            for project in projects
        ]
        self.assertEqual(
            [attempt.outcome for attempt in attempts],
            [VoteAttemptOutcome.ACCEPTED] * 5 + [VoteAttemptOutcome.REJECTED_RATE_LIMIT],
        )

    def test_v_t3_results_are_hidden_until_close_for_non_organizers(self):
        self.assertEqual(voting.get_results(self.organizer, self.event)['event'], self.event)
        for actor in (self.anon, self.participant, self.judge):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionDenied):
                    voting.get_results(actor, self.event)

        results_url = reverse('voting_results', args=[self.event.slug])
        self.assertEqual(self.client.get(results_url).status_code, 401)
        self.assertEqual(self.client.get(results_url, **self.headers('participant')).status_code, 403)
        self.assertEqual(self.client.get(results_url, **self.headers('judge')).status_code, 403)
        self.assertEqual(self.client.get(results_url, **self.headers('organizer')).status_code, 200)

        self.event.voting_closes_at = timezone.now() - timedelta(seconds=1)
        self.event.save(update_fields=['voting_closes_at'])
        self.assertEqual(self.client.get(results_url).status_code, 200)
        self.assertEqual(self.client.get(results_url + '?format=json').status_code, 200)

    def test_v_t4_ballot_order_is_stable_per_voter_and_differs_between_voters(self):
        first = voting.get_ballot(self.anon, self.event, fingerprint='voter-alpha')['projects']
        again = voting.get_ballot(self.anon, self.event, fingerprint='voter-alpha')['projects']
        other = voting.get_ballot(self.anon, self.event, fingerprint='voter-beta')['projects']
        first_ids = [project.pk for project in first]
        self.assertEqual(first_ids, [project.pk for project in again])
        self.assertNotEqual(first_ids, [project.pk for project in other])

    def test_v_t5_flag_hides_comment_without_deleting_and_html_is_escaped(self):
        body = '<script>alert("x")</script>'
        comment = voting.comment(self.anon, self.project, body, **self.identity)
        public_url = reverse('project_detail', args=[self.project.pk])
        response = self.client.get(public_url)
        self.assertContains(response, '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;', html=False)
        self.assertNotContains(response, body, html=False)

        voting.flag_comment(self.organizer, comment.pk)
        self.assertFalse(voting.public_comments(self.anon, self.project).filter(pk=comment.pk).exists())
        self.assertTrue(voting.organizer_comments(self.organizer, self.project).filter(pk=comment.pk).exists())
        self.assertTrue(Comment.objects.filter(pk=comment.pk, is_flagged=True).exists())
        self.assertNotContains(self.client.get(public_url), 'alert', html=False)
        organizer_page = self.client.get(public_url, **self.headers('organizer'))
        self.assertContains(organizer_page, 'Hidden from public')
        self.assertContains(organizer_page, '&lt;script&gt;', html=False)

    def test_v_t6_fixture_duplicate_is_never_votable_but_canonical_is(self):
        duplicate = Project.objects.get(external_id='prj_07')
        canonical = Project.objects.get(external_id='prj_41')
        ballot = voting.get_ballot(self.anon, self.event, **self.identity)
        eligible_ids = {project.external_id for project in ballot['projects']}
        self.assertNotIn('prj_07', eligible_ids)
        self.assertIn('prj_41', eligible_ids)
        with self.assertRaises(PermissionDenied):
            voting.cast(self.anon, self.event, duplicate, **self.identity)
        attempt = voting.cast(self.anon, self.event, canonical, **self.identity)
        self.assertEqual(attempt.outcome, VoteAttemptOutcome.ACCEPTED)

    def test_v_t7_integrity_summary_counts_outcomes_and_project_activity(self):
        voting.cast(self.anon, self.event, self.project, fingerprint='summary-voter')
        voting.cast(self.anon, self.event, self.project, fingerprint='summary-voter')
        summary = voting.integrity_summary(self.organizer, self.event)
        self.assertEqual(summary['outcomes'][VoteAttemptOutcome.ACCEPTED], 1)
        self.assertEqual(summary['outcomes'][VoteAttemptOutcome.REJECTED_DUPLICATE], 1)
        row = next(item for item in summary['projects'] if item['project_id'] == self.project.pk)
        self.assertEqual((row['attempts'], row['blocked_attempts'], row['active_votes']), (2, 1, 1))

    def test_vote_budget_is_enforced_and_withdrawal_frees_it(self):
        self.event.votes_per_voter = 1
        self.event.save(update_fields=['votes_per_voter'])
        other_project = voting.eligible_projects(self.event).exclude(pk=self.project.pk).first()
        accepted = voting.cast(self.anon, self.event, self.project, fingerprint='budget-voter')
        rejected = voting.cast(self.anon, self.event, other_project, fingerprint='budget-voter')
        self.assertEqual(accepted.outcome, VoteAttemptOutcome.ACCEPTED)
        self.assertEqual(rejected.outcome, VoteAttemptOutcome.REJECTED_BUDGET)
        ballot = voting.get_ballot(self.anon, self.event, fingerprint='budget-voter')
        self.assertEqual(ballot['remaining_budget'], 0)
        withdrawn = voting.withdraw(self.anon, self.event, self.project, fingerprint='budget-voter')
        self.assertEqual(withdrawn.outcome, VoteAttemptOutcome.WITHDRAWN)
        self.assertFalse(Vote.objects.filter(event=self.event, voter_fingerprint='budget-voter').exists())
        self.assertEqual(voting.get_ballot(self.anon, self.event, fingerprint='budget-voter')['remaining_budget'], 1)
        self.assertEqual(
            voting.cast(self.anon, self.event, other_project, fingerprint='budget-voter').outcome,
            VoteAttemptOutcome.ACCEPTED,
        )

    def test_auth_mode_rejects_anonymous_and_uses_user_id_fingerprint(self):
        self.event.voting_access = 'AUTH'
        self.event.save(update_fields=['voting_access'])
        with self.assertRaises(PermissionDenied):
            voting.cast(self.anon, self.event, self.project, fingerprint='arbitrary')
        url = reverse('voting_cast', args=[self.event.slug, self.project.pk])
        self.assertEqual(self.client.post(url).status_code, 401)
        result = voting.cast(self.participant, self.event, self.project)
        self.assertEqual(result.voter_fingerprint, str(self.participant.user.pk))

    def test_unopened_and_closed_windows_record_rejected_closed(self):
        self.event.voting_opens_at = None
        self.event.save(update_fields=['voting_opens_at'])
        unopened = voting.cast(self.anon, self.event, self.project, fingerprint='closed-voter')
        self.assertEqual(unopened.outcome, VoteAttemptOutcome.REJECTED_CLOSED)
        self.event.voting_opens_at = timezone.now() - timedelta(hours=2)
        self.event.voting_closes_at = timezone.now() - timedelta(hours=1)
        self.event.save(update_fields=['voting_opens_at', 'voting_closes_at'])
        closed = voting.cast(self.anon, self.event, self.project, fingerprint='closed-voter')
        self.assertEqual(closed.outcome, VoteAttemptOutcome.REJECTED_CLOSED)

    def test_database_unique_constraint_is_the_final_duplicate_guard(self):
        attempt = voting.cast(self.anon, self.event, self.project, fingerprint='db-unique-voter')
        vote = Vote.objects.get(attempt=attempt)
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                Vote.objects.create(
                    event=self.event,
                    project=self.project,
                    mode=VoteMode.OPEN,
                    voter_fingerprint='db-unique-voter',
                )
        self.assertEqual(Vote.objects.filter(event=self.event, project=self.project).count(), 1)
        self.assertEqual(vote.weight, 1)

    def test_raw_ip_and_user_agent_are_never_persisted(self):
        raw_ip = '203.0.113.91'
        raw_ua = 'private-test-agent/99.7'
        voting.cast(self.anon, self.event, self.project, ip=raw_ip, user_agent=raw_ua)
        voting.comment(self.anon, self.project, 'safe comment', ip=raw_ip, user_agent=raw_ua)
        persisted = '\n'.join([
            str(list(VoteAttempt.objects.values())),
            str(list(Vote.objects.values())),
            str(list(Comment.objects.values())),
            json.dumps(list(AuditLogEntry.objects.values('payload')), default=str),
        ])
        self.assertNotIn(raw_ip, persisted)
        self.assertNotIn(raw_ua, persisted)

    def test_event_voting_settings_are_validated_and_before_after_audited(self):
        from events.services import update_event
        update_event(
            self.organizer, self.event,
            voting_access='AUTH', votes_per_voter=4,
        )
        self.event.refresh_from_db()
        self.assertEqual((self.event.voting_access, self.event.votes_per_voter), ('AUTH', 4))
        entry = AuditLogEntry.objects.filter(action='event.update').latest('seq')
        self.assertEqual(entry.payload['before']['voting_access'], 'OPEN')
        self.assertEqual(entry.payload['after']['voting_access'], 'AUTH')
        self.assertEqual(entry.payload['after']['votes_per_voter'], 4)
        with self.assertRaisesRegex(ValueError, 'votes_per_voter'):
            update_event(self.organizer, self.event, votes_per_voter=-1)

    def test_organizer_summary_is_protected_and_other_reads_do_not_expose_tallies(self):
        voting.cast(self.anon, self.event, self.project, fingerprint='private-tally-voter')
        summary_url = reverse('organizer_voting_summary')
        self.assertEqual(self.client.get(summary_url).status_code, 401)
        self.assertEqual(self.client.get(summary_url, **self.headers('participant')).status_code, 403)
        self.assertEqual(self.client.get(summary_url, **self.headers('judge')).status_code, 403)
        summary = self.client.get(summary_url, **self.headers('organizer'))
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json()['outcomes']['ACCEPTED'], 1)

        detail = self.client.get(reverse('project_detail', args=[self.project.pk]))
        self.assertNotContains(detail, 'vote_count', html=False)
        self.assertNotContains(detail, 'private-tally-voter', html=False)
        csv_response = self.client.get('/api/export.csv', **self.headers('organizer'))
        self.assertEqual(csv_response.status_code, 200)
        self.assertNotIn('vote_count', csv_response.content.decode('utf-8'))
        dashboard = self.client.get('/organizer', **self.headers('organizer'))
        self.assertEqual(dashboard.status_code, 200)
        self.assertNotContains(dashboard, 'private-tally-voter', html=False)

    def test_bare_anonymous_post_is_rejected_by_csrf_before_voting_service(self):
        client = Client(enforce_csrf_checks=True)
        url = reverse('voting_cast', args=[self.event.slug, self.project.pk])
        response = client.post(url)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(VoteAttempt.objects.count(), 0)

    def test_header_authenticated_post_keeps_the_existing_csrf_split(self):
        client = Client(enforce_csrf_checks=True)
        url = reverse('voting_cast', args=[self.event.slug, self.project.pk])
        response = client.post(url, **self.headers('participant'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Vote.objects.count(), 1)


class VotingConcurrencyTests(AuditTransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.event = Event.objects.create(
            slug=f'concurrency-{uuid.uuid4().hex[:10]}',
            name='Voting concurrency',
            submissions_close_at=timezone.now() + timedelta(days=1),
            voting_opens_at=timezone.now() - timedelta(minutes=1),
            voting_closes_at=timezone.now() + timedelta(hours=1),
            votes_per_voter=None,
        )
        track = Track.objects.create(event=self.event, name='Track')
        team = Team.objects.create(event=self.event, name='Team', invite_code=uuid.uuid4().hex)
        self.projects = [
            Project.objects.create(
                event=self.event,
                team=team,
                track=track,
                title=f'Concurrent project {index}',
                summary='Synthetic concurrency fixture',
                status=ProjectStatus.SUBMITTED,
            )
            for index in range(12)
        ]

    def _parallel_cast(self, project, voter):
        close_old_connections()
        try:
            result = voting.cast(
                AnonymousActor(), self.event.slug, project.pk,
                fingerprint=voter,
            )
            return result.outcome
        finally:
            close_old_connections()

    def test_concurrent_same_vote_has_one_winner_and_logs_all_attempts(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(lambda _: self._parallel_cast(self.projects[0], 'same-voter'), range(8)))
        self.assertEqual(outcomes.count(VoteAttemptOutcome.ACCEPTED), 1)
        self.assertEqual(
            outcomes.count(VoteAttemptOutcome.REJECTED_DUPLICATE)
            + outcomes.count(VoteAttemptOutcome.REJECTED_RATE_LIMIT),
            7,
        )
        self.assertEqual(Vote.objects.filter(event=self.event).count(), 1)
        self.assertEqual(VoteAttempt.objects.filter(event=self.event).count(), 8)

    def test_concurrent_budget_race_keeps_exactly_the_allowed_vote_count(self):
        self.event.votes_per_voter = 3
        self.event.save(update_fields=['votes_per_voter'])
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(
                lambda project: self._parallel_cast(project, 'budget-race-voter'),
                self.projects[:8],
            ))
        self.assertEqual(outcomes.count(VoteAttemptOutcome.ACCEPTED), 3)
        self.assertEqual(
            outcomes.count(VoteAttemptOutcome.REJECTED_BUDGET)
            + outcomes.count(VoteAttemptOutcome.REJECTED_RATE_LIMIT),
            5,
        )
        self.assertEqual(Vote.objects.filter(event=self.event, voter_fingerprint='budget-race-voter').count(), 3)
        self.assertEqual(VoteAttempt.objects.filter(event=self.event).count(), 8)
