import io
import json
from unittest.mock import patch

from django.core.management import call_command
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from accounts.actors import Actor, AnonymousActor, PermissionDenied
from accounts.models import AuthToken, EventMembership, EventRole, User
from audit.models import AuditChainHead, AuditLogEntry
from events.models import Event, Prize, Track
from events.services import create_event, create_prize, create_track
from judging.models import AssignmentStatus, Ballot, JudgeAssignment, Rubric, RubricCriterion
from services.assignment import run as assignment_run
from services.judging import save_ballot_draft, submit_ballot
from services.normalization import run as normalization_run
from services.submissions import (
    create as submission_create,
    detect_and_flag_duplicates,
    restore_duplicate,
    submit as submission_submit,
    update as submission_update,
)
from submissions.models import Project, ProjectStatus
from teams.models import Team, TeamMembership
from teams.services import create_team, join_team


class G5Step2ServiceAuditWiringTests(TestCase):
    """
    Test that every state-changing service writes exactly one audit entry
    inside the same transaction, and rolls back cleanly on exception.
    """

    def setUp(self):
        self.organizer_user = User.objects.create_user(
            email='organizer@test.local', display_name='Organizer User', is_site_admin=True,
        )
        self.participant_user = User.objects.create_user(
            email='participant@test.local', display_name='Participant User',
        )
        self.judge_user = User.objects.create_user(
            email='judge@test.local', display_name='Judge User',
        )
        self.other_user = User.objects.create_user(
            email='other@test.local', display_name='Other User',
        )

        self.event = Event.objects.create(
            name='Test Hackathon', slug='test-hackathon',
            submissions_close_at=timezone.now() + timezone.timedelta(days=7),
            created_by=self.organizer_user,
        )
        EventMembership.objects.create(
            event=self.event, user=self.organizer_user, role=EventRole.ORGANIZER,
        )
        EventMembership.objects.create(
            event=self.event, user=self.participant_user, role=EventRole.PARTICIPANT,
        )
        EventMembership.objects.create(
            event=self.event, user=self.judge_user, role=EventRole.JUDGE,
        )

        self.organizer_actor = Actor(self.organizer_user, self.event)
        self.participant_actor = Actor(self.participant_user, self.event)
        self.judge_actor = Actor(self.judge_user, self.event)
        self.anon_actor = AnonymousActor()

    def test_event_track_prize_audit_wiring(self):
        initial_count = AuditLogEntry.objects.count()

        # create_event
        evt = create_event(self.organizer_actor, name='Audit Sub-event', slug='audit-sub-event')
        self.assertEqual(AuditLogEntry.objects.count(), initial_count + 1)
        entry = AuditLogEntry.objects.order_by('-seq').first()
        self.assertEqual(entry.action, 'event.create')
        self.assertEqual(entry.target_type, 'events.event')
        self.assertEqual(entry.target_id, str(evt.pk))

        # create_track
        trk = create_track(self.organizer_actor, event=evt, name='Security Track')
        self.assertEqual(AuditLogEntry.objects.count(), initial_count + 2)
        entry = AuditLogEntry.objects.order_by('-seq').first()
        self.assertEqual(entry.action, 'track.create')
        self.assertEqual(entry.target_id, str(trk.pk))

        # create_prize
        prz = create_prize(self.organizer_actor, event=evt, rank_label='1st Place')
        self.assertEqual(AuditLogEntry.objects.count(), initial_count + 3)
        entry = AuditLogEntry.objects.order_by('-seq').first()
        self.assertEqual(entry.action, 'prize.create')
        self.assertEqual(entry.target_id, str(prz.pk))

    def test_team_create_and_join_audit_wiring(self):
        initial_count = AuditLogEntry.objects.count()

        # create_team
        team = create_team(self.participant_actor, self.event, name='Cyber Team', invite_code='secret123')
        self.assertEqual(AuditLogEntry.objects.count(), initial_count + 1)
        entry = AuditLogEntry.objects.order_by('-seq').first()
        self.assertEqual(entry.action, 'team.create')
        # Payload must never contain passwords or tokens
        self.assertNotIn('secret123', json.dumps(entry.payload))
        self.assertNotIn('invite_code', entry.payload)

        # join_team
        joiner_actor = Actor(self.other_user, self.event)
        membership = join_team(joiner_actor, team.id, 'secret123')
        self.assertEqual(AuditLogEntry.objects.count(), initial_count + 2)
        entry = AuditLogEntry.objects.order_by('-seq').first()
        self.assertEqual(entry.action, 'team.join')
        self.assertNotIn('secret123', json.dumps(entry.payload))

    def test_submission_create_update_submit_audit_wiring(self):
        team = create_team(self.participant_actor, self.event, name='Submissions Team', invite_code='subcode')
        track = create_track(self.organizer_actor, event=self.event, name='AI Track')
        initial_count = AuditLogEntry.objects.count()

        # submission.create
        project = submission_create(
            self.participant_actor, team=team, track=track,
            title='AI Sentinel', summary='Autonomous AI safety guard',
        )
        self.assertEqual(AuditLogEntry.objects.count(), initial_count + 1)
        entry = AuditLogEntry.objects.order_by('-seq').first()
        self.assertEqual(entry.action, 'submission.create')
        self.assertEqual(entry.target_id, str(project.pk))

        # submission.update
        submission_update(self.participant_actor, project.id, summary='Updated summary')
        self.assertEqual(AuditLogEntry.objects.count(), initial_count + 2)
        entry = AuditLogEntry.objects.order_by('-seq').first()
        self.assertEqual(entry.action, 'submission.update')

        # submission.submit
        submission_submit(self.participant_actor, project.id)
        self.assertEqual(AuditLogEntry.objects.count(), initial_count + 3)
        entry = AuditLogEntry.objects.order_by('-seq').first()
        self.assertEqual(entry.action, 'submission.submit')

    def test_ballot_draft_autosave_skips_audit_but_submit_records(self):
        team = create_team(self.participant_actor, self.event, name='Ballot Team', invite_code='ballot')
        track = create_track(self.organizer_actor, event=self.event, name='Ballot Track')
        project = submission_create(self.participant_actor, team=team, track=track, title='P1', summary='S1')
        submission_submit(self.participant_actor, project.id)

        rubric = Rubric.objects.create(event=self.event, name='Default Rubric')
        c1 = RubricCriterion.objects.create(rubric=rubric, name='quality', max_score=5, weight=1, order=0)

        assignment = JudgeAssignment.objects.create(
            event=self.event, judge=self.judge_user, project=project, status=AssignmentStatus.PENDING,
        )

        initial_count = AuditLogEntry.objects.count()

        # Autosave draft: must NOT record audit entry
        draft = save_ballot_draft(self.judge_actor, assignment.pk, scores={c1.name: 4}, comment='Draft comment')
        self.assertFalse(draft.is_complete)
        self.assertEqual(AuditLogEntry.objects.count(), initial_count)

        # Ballot submit: MUST record audit entry
        submitted = submit_ballot(self.judge_actor, assignment.pk, scores={c1.name: 5}, comment='Final comment')
        self.assertTrue(submitted.is_complete)
        self.assertEqual(AuditLogEntry.objects.count(), initial_count + 1)
        entry = AuditLogEntry.objects.order_by('-seq').first()
        self.assertEqual(entry.action, 'ballot.submit')
        self.assertEqual(entry.target_id, str(submitted.pk))

    def test_assignment_and_normalization_run_audit_wiring(self):
        team = create_team(self.participant_actor, self.event, name='Run Team', invite_code='run')
        track = create_track(self.organizer_actor, event=self.event, name='Run Track')
        project = submission_create(self.participant_actor, team=team, track=track, title='Run Project', summary='S')
        submission_submit(self.participant_actor, project.id)

        initial_count = AuditLogEntry.objects.count()

        # assignment.run
        arun = assignment_run(self.organizer_actor, k=1, seed=42)
        self.assertEqual(AuditLogEntry.objects.count(), initial_count + 1)
        entry = AuditLogEntry.objects.order_by('-seq').first()
        self.assertEqual(entry.action, 'assignment.run')
        self.assertEqual(entry.target_id, str(arun.pk))

        # normalization.run
        nrun = normalization_run(self.organizer_actor)
        self.assertEqual(AuditLogEntry.objects.count(), initial_count + 2)
        entry = AuditLogEntry.objects.order_by('-seq').first()
        self.assertEqual(entry.action, 'normalization.run')
        self.assertEqual(entry.target_id, str(nrun.pk))

    def test_transactional_rollback_leaves_no_change_and_no_audit_entry(self):
        """A service that raises after mutating leaves no entry and no change."""
        initial_entries = AuditLogEntry.objects.count()
        initial_tracks = Track.objects.count()

        class SimulatedServiceFailure(Exception):
            pass

        # Simulate exception raised right after Track.objects.create
        with self.assertRaises(SimulatedServiceFailure):
            with patch('services.audit.record', side_effect=SimulatedServiceFailure("Boom after create")):
                create_track(self.organizer_actor, event=self.event, name='Failed Track')

        self.assertEqual(Track.objects.count(), initial_tracks)
        self.assertEqual(AuditLogEntry.objects.count(), initial_entries)


class G5Step2DuplicateDetectorAndStickyRestoreTests(TestCase):
    """
    Test duplicate detector attribution, sticky restore override,
    and idempotency against seed_fixtures.
    """

    @classmethod
    def setUpTestData(cls):
        call_command('seed_fixtures', stdout=io.StringIO())
        cls.event = Event.objects.get(external_id='evt_01')
        cls.organizer = User.objects.get(email='organizer@rubric.local')
        cls.organizer_actor = Actor(cls.organizer, cls.event)

    def test_duplicate_flag_attributed_to_policy_v1_and_restore_is_sticky(self):
        earlier = Project.objects.get(event=self.event, external_id='prj_07')
        later = Project.objects.get(event=self.event, external_id='prj_41')

        # 1. prj_07 was auto-flagged during import and attributed to 'duplicate-detection policy v1'
        self.assertEqual(earlier.is_duplicate_of_id, later.pk)
        flag_entry = AuditLogEntry.objects.filter(
            action='duplicate.flag',
            actor_label='duplicate-detection policy v1',
            target_id=str(earlier.pk),
        ).first()
        self.assertIsNotNone(flag_entry)
        self.assertEqual(flag_entry.actor_label, 'duplicate-detection policy v1')
        self.assertIsNone(flag_entry.actor_user_id)

        # 2. Organizer restores prj_07
        restored = restore_duplicate(self.organizer_actor, earlier.pk)
        self.assertIsNone(restored.is_duplicate_of)
        self.assertTrue(restored.duplicate_override)

        # Verify restore audit entry
        restore_entry = AuditLogEntry.objects.filter(
            action='duplicate.restore',
            target_id=str(earlier.pk),
        ).first()
        self.assertIsNotNone(restore_entry)
        self.assertEqual(restore_entry.actor_user_id, self.organizer.pk)

        # 3. Detector re-run never re-flags restored project
        flagged_again = detect_and_flag_duplicates(restored)
        self.assertIsNone(flagged_again)
        restored.refresh_from_db()
        self.assertIsNone(restored.is_duplicate_of)
        self.assertTrue(restored.duplicate_override)

        # 4. seed_fixtures re-run preserves the restored state
        call_command('seed_fixtures', stdout=io.StringIO())
        earlier.refresh_from_db()
        self.assertIsNone(earlier.is_duplicate_of)
        self.assertTrue(earlier.duplicate_override)


class G5Step2AuditRoutesAuthzTests(TestCase):
    """
    Test organizer-only audit routes:
    - GET /api/v1/organizer/audit-log
    - GET /api/v1/organizer/audit-log/verify
    - GET /organizer/audit-log
    Denies anon (401), participant (403), judge (403), allows organizer (200).
    """

    @classmethod
    def setUpTestData(cls):
        call_command('seed_fixtures', stdout=io.StringIO())
        cls.event = Event.objects.get(external_id='evt_01')
        # Use seeded persona tokens:
        from importer.management.commands.seed_fixtures import SEED_TOKENS
        cls.organizer_raw = SEED_TOKENS['organizer']
        cls.participant_raw = SEED_TOKENS['participant']
        cls.judge_raw = SEED_TOKENS['judge_a']

    def test_api_audit_log_endpoint_authz(self):
        url = '/api/v1/organizer/audit-log'

        # Anon -> 401
        res_anon = self.client.get(url)
        self.assertEqual(res_anon.status_code, 401)

        # Participant -> 403
        res_part = self.client.get(url, HTTP_AUTHORIZATION=f'Bearer {self.participant_raw}')
        self.assertEqual(res_part.status_code, 403)

        # Judge -> 403
        res_judge = self.client.get(url, HTTP_AUTHORIZATION=f'Bearer {self.judge_raw}')
        self.assertEqual(res_judge.status_code, 403)

        # Organizer -> 200
        res_org = self.client.get(url, HTTP_AUTHORIZATION=f'Bearer {self.organizer_raw}')
        self.assertEqual(res_org.status_code, 200)
        data = res_org.json()
        self.assertIn('entries', data)
        self.assertIn('total', data)
        self.assertGreater(data['total'], 0)

    def test_api_audit_verify_endpoint_authz_and_download(self):
        url = '/api/v1/organizer/audit-log/verify'

        # Anon -> 401
        res_anon = self.client.get(url)
        self.assertEqual(res_anon.status_code, 401)

        # Participant -> 403
        res_part = self.client.get(url, HTTP_AUTHORIZATION=f'Bearer {self.participant_raw}')
        self.assertEqual(res_part.status_code, 403)

        # Judge -> 403
        res_judge = self.client.get(url, HTTP_AUTHORIZATION=f'Bearer {self.judge_raw}')
        self.assertEqual(res_judge.status_code, 403)

        # Organizer -> 200 (verify result)
        res_org = self.client.get(url, HTTP_AUTHORIZATION=f'Bearer {self.organizer_raw}')
        self.assertEqual(res_org.status_code, 200)
        data = res_org.json()
        self.assertTrue(data['valid'])
        self.assertIn('head_hash', data)

        # Organizer -> 200 (export download)
        res_dl = self.client.get(f'{url}?download=1', HTTP_AUTHORIZATION=f'Bearer {self.organizer_raw}')
        self.assertEqual(res_dl.status_code, 200)
        self.assertEqual(res_dl['Content-Type'], 'application/json; charset=utf-8')
        doc = json.loads(res_dl.content)
        self.assertIn('entries', doc)
        self.assertIn('head', doc)

    def test_html_audit_log_page_authz(self):
        url = '/organizer/audit-log'

        # Anon -> 401
        res_anon = self.client.get(url)
        self.assertEqual(res_anon.status_code, 401)

        # Participant -> 403
        res_part = self.client.get(url, HTTP_AUTHORIZATION=f'Bearer {self.participant_raw}')
        self.assertEqual(res_part.status_code, 403)

        # Judge -> 403
        res_judge = self.client.get(url, HTTP_AUTHORIZATION=f'Bearer {self.judge_raw}')
        self.assertEqual(res_judge.status_code, 403)

        # Organizer -> 200
        res_org = self.client.get(url, HTTP_AUTHORIZATION=f'Bearer {self.organizer_raw}')
        self.assertEqual(res_org.status_code, 200)
        self.assertContains(res_org, 'Organizer Audit Log')
        self.assertContains(res_org, 'Verify Chain')
