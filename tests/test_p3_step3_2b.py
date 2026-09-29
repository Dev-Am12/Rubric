import json
from datetime import timedelta
import importlib.util
from pathlib import Path
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounts.actors import Actor, AnonymousActor
from accounts.models import EventMembership, EventRole, User
from audit.models import AuditLogEntry
from events.models import Event
from events.services import update_event
from services import audit as audit_service
from services import voting as voting_service
from submissions.models import Project
from voting.models import Vote, VoteAttempt, VoteAttemptOutcome


class VotingPseudonymTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_fixtures', stdout=StringIO())
        cls.event = Event.objects.get(external_id='evt_01')
        cls.project_41 = Project.objects.get(external_id='prj_41')
        cls.project_40 = Project.objects.get(external_id='prj_40')
        cls.project_17 = Project.objects.get(external_id='prj_17')
        cls.judge = User.objects.get(external_id='jdg_07')
        cls.second_voter = EventMembership.objects.filter(
            event=cls.event, role=EventRole.PARTICIPANT,
        ).select_related('user').first().user
        cls.organizer = User.objects.get(email='organizer@rubric.local')
        cls.judge_actor = Actor(cls.judge, cls.event)
        cls.second_actor = Actor(cls.second_voter, cls.event)
        cls.organizer_actor = Actor(cls.organizer, cls.event)

    def setUp(self):
        self.event.voting_access = 'OPEN'
        self.event.voting_opens_at = timezone.now() - timedelta(minutes=2)
        self.event.voting_closes_at = timezone.now() + timedelta(hours=1)
        self.event.votes_per_voter = None
        self.event.save(update_fields=[
            'voting_access', 'voting_opens_at', 'voting_closes_at', 'votes_per_voter',
        ])
        self.event.refresh_from_db()
        self.judge_actor = Actor(self.judge, self.event)
        self.second_actor = Actor(self.second_voter, self.event)
        self.organizer_actor = Actor(self.organizer, self.event)

    def test_auth_votes_store_keyed_pseudonyms_and_unattributed_audit_entries(self):
        self.event.voting_access = 'AUTH'
        self.event.votes_per_voter = 2
        self.event.save(update_fields=['voting_access', 'votes_per_voter'])
        first = voting_service.cast(
            self.judge_actor, self.event, self.project_41,
            ip='192.0.2.10', user_agent='first-agent',
        )
        second = voting_service.cast(
            self.second_actor, self.event, self.project_41,
            ip='192.0.2.11', user_agent='second-agent',
        )
        self.assertEqual((first.outcome, second.outcome), ('ACCEPTED', 'ACCEPTED'))

        judge_fingerprint = voting_service._fingerprint(
            self.judge_actor, self.event, ip='192.0.2.99', user_agent='rotated-agent',
        )
        self.assertEqual(
            judge_fingerprint,
            voting_service._fingerprint(self.judge_actor, self.event, user_agent='other-agent'),
        )
        other_event = Event.objects.create(
            name='Pseudonym scope test', slug='pseudonym-scope-test',
            submissions_close_at=timezone.now() + timedelta(days=3),
            voting_access='AUTH',
        )
        self.assertNotEqual(
            judge_fingerprint,
            voting_service._fingerprint(self.judge_actor, other_event),
        )

        vote_rows = Vote.objects.filter(event=self.event)
        attempt_rows = VoteAttempt.objects.filter(event=self.event)
        for user in (self.judge, self.second_voter):
            self.assertFalse(vote_rows.filter(voter_fingerprint=str(user.pk)).exists())
            self.assertFalse(attempt_rows.filter(voter_fingerprint=str(user.pk)).exists())
        entries = AuditLogEntry.objects.filter(action='voting.vote_cast').order_by('seq')
        self.assertEqual(entries.count(), 2)
        for entry in entries:
            self.assertIsNone(entry.actor_user_id)
            self.assertEqual(entry.actor_label, 'voter-pseudonym')
            self.assertEqual(len(entry.payload['voter_fingerprint_hash']), 16)

        withdrawn = voting_service.withdraw(self.judge_actor, self.event, self.project_41)
        self.assertEqual(withdrawn.outcome, VoteAttemptOutcome.WITHDRAWN)
        withdrawal_entry = AuditLogEntry.objects.filter(action='voting.vote_withdrawn').latest('seq')
        self.assertIsNone(withdrawal_entry.actor_user_id)
        self.assertEqual(withdrawal_entry.actor_label, 'voter-pseudonym')

        self.assertTrue(audit_service.verify(self.organizer_actor)[0])
        document = json.loads(audit_service.export_chain())
        script = Path(__file__).resolve().parents[1] / 'scripts' / 'verify_audit_chain.py'
        spec = importlib.util.spec_from_file_location('audit_verifier', script)
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        ok, bad_seq, head_hash = verifier.verify(document)
        self.assertTrue(ok, f'export verifier failed at {bad_seq}')
        self.assertEqual(head_hash, document['head']['hash'])

    def test_auth_same_user_keeps_duplicate_and_budget_enforcement(self):
        self.event.voting_access = 'AUTH'
        self.event.votes_per_voter = 2
        self.event.save(update_fields=['voting_access', 'votes_per_voter'])
        one = voting_service.cast(self.judge_actor, self.event, self.project_41)
        duplicate = voting_service.cast(self.judge_actor, self.event, self.project_41)
        two = voting_service.cast(self.judge_actor, self.event, self.project_40)
        over_budget = voting_service.cast(self.judge_actor, self.event, self.project_17)
        self.assertEqual(one.outcome, VoteAttemptOutcome.ACCEPTED)
        self.assertEqual(duplicate.outcome, VoteAttemptOutcome.REJECTED_DUPLICATE)
        self.assertEqual(two.outcome, VoteAttemptOutcome.ACCEPTED)
        self.assertEqual(over_budget.outcome, VoteAttemptOutcome.REJECTED_BUDGET)
        self.assertEqual(Vote.objects.filter(event=self.event).count(), 2)

    def test_open_rotating_user_agents_share_ip_budget_and_rate_limit(self):
        self.event.votes_per_voter = 1
        self.event.save(update_fields=['votes_per_voter'])
        outcomes = [
            voting_service.cast(
                AnonymousActor(), self.event, self.project_41,
                ip='198.51.100.70', user_agent=f'rotated-agent-{index}',
            ).outcome
            for index in range(5)
        ]
        self.assertEqual(outcomes[0], VoteAttemptOutcome.ACCEPTED)
        self.assertEqual(outcomes[1:], [VoteAttemptOutcome.REJECTED_BUDGET] * 4)
        sixth = voting_service.cast(
            AnonymousActor(), self.event, self.project_41,
            ip='198.51.100.70', user_agent='sixth-agent',
        )
        self.assertEqual(sixth.outcome, VoteAttemptOutcome.REJECTED_RATE_LIMIT)
        self.assertEqual(Vote.objects.filter(event=self.event).count(), 1)

    def test_open_different_ips_have_independent_ballots_and_budget(self):
        self.event.votes_per_voter = 1
        self.event.save(update_fields=['votes_per_voter'])
        first = voting_service.cast(
            AnonymousActor(), self.event, self.project_41,
            ip='203.0.113.10', user_agent='shared-agent',
        )
        second = voting_service.cast(
            AnonymousActor(), self.event, self.project_40,
            ip='203.0.113.11', user_agent='shared-agent',
        )
        self.assertEqual(first.outcome, VoteAttemptOutcome.ACCEPTED)
        self.assertEqual(second.outcome, VoteAttemptOutcome.ACCEPTED)
        ballot_one = voting_service.get_ballot(
            AnonymousActor(), self.event, ip='203.0.113.10', user_agent='changed-agent',
        )
        ballot_two = voting_service.get_ballot(
            AnonymousActor(), self.event, ip='203.0.113.11', user_agent='changed-agent',
        )
        self.assertEqual(ballot_one['cast_project_ids'], {self.project_41.pk})
        self.assertEqual(ballot_two['cast_project_ids'], {self.project_40.pk})
        self.assertEqual(ballot_one['remaining_budget'], 0)

    def test_lower_budget_cannot_underflow_active_votes_but_raise_is_allowed(self):
        self.event.votes_per_voter = 3
        self.event.save(update_fields=['votes_per_voter'])
        voting_service.cast(AnonymousActor(), self.event, self.project_41, ip='192.0.2.44')
        voting_service.cast(AnonymousActor(), self.event, self.project_40, ip='192.0.2.44')
        with self.assertRaisesRegex(ValueError, 'highest active vote count.*2'):
            update_event(self.organizer_actor, self.event, votes_per_voter=1)
        updated = update_event(self.organizer_actor, self.event, votes_per_voter=2)
        self.assertEqual(updated.votes_per_voter, 2)
        raised = update_event(self.organizer_actor, self.event, votes_per_voter=4)
        self.assertEqual(raised.votes_per_voter, 4)

    def test_ballot_page_discloses_open_network_sharing(self):
        from django.test import Client

        response = Client().get(f'/vote/{self.event.slug}')
        self.assertContains(
            response,
            'Open voting is best-effort: people on the same network share a ballot. Use signed-in voting when the result matters.',
        )


class VotingWindowNowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_fixtures', stdout=StringIO())
        cls.event = Event.objects.get(external_id='evt_01')
        cls.organizer = User.objects.get(email='organizer@rubric.local')
        cls.actor = Actor(cls.organizer, cls.event)

    def test_open_now_clears_a_past_close_and_audits_the_change(self):
        from audit.models import AuditLogEntry

        self.event.voting_opens_at = timezone.now() - timedelta(days=2)
        self.event.voting_closes_at = timezone.now() - timedelta(days=1)
        self.event.save(update_fields=['voting_opens_at', 'voting_closes_at'])
        before_close = self.event.voting_closes_at.isoformat()
        updated = voting_service.open_voting_now(self.actor, self.event)
        self.assertIsNone(updated.voting_closes_at)
        self.assertLessEqual(updated.voting_opens_at, timezone.now())
        entry = AuditLogEntry.objects.filter(action='event.voting_opened_now').latest('seq')
        self.assertEqual(entry.payload['before']['voting_closes_at'], before_close)
        self.assertIsNone(entry.payload['after']['voting_closes_at'])

    def test_close_now_moves_null_or_future_open_to_now(self):
        self.event.voting_opens_at = None
        self.event.voting_closes_at = None
        self.event.save(update_fields=['voting_opens_at', 'voting_closes_at'])
        first = voting_service.close_voting_now(self.actor, self.event)
        self.assertIsNotNone(first.voting_opens_at)
        self.assertLessEqual(first.voting_opens_at, first.voting_closes_at)

        self.event.voting_opens_at = timezone.now() + timedelta(days=2)
        self.event.voting_closes_at = None
        self.event.save(update_fields=['voting_opens_at', 'voting_closes_at'])
        second = voting_service.close_voting_now(self.actor, self.event)
        self.assertLessEqual(second.voting_opens_at, second.voting_closes_at)
