from io import StringIO
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from judging.models import Ballot, BallotScore, JudgeAssignment, Rubric
from services.judging import get_scores, progress, save_ballot, save_ballot_draft, submit_ballot
from accounts.actors import Actor, PermissionDenied
from accounts.models import EventMembership, EventRole, User


class G3JudgingImportAndIsolationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_fixtures', stdout=StringIO())

    def _headers(self, persona):
        tokens = {
            'organizer': 'rubric_seed_organizer_tok_9f8e7d6c5b4a',
            'judge_a': 'rubric_seed_judge_a_tok_1a2b3c4d5e6f',
            'judge_b': 'rubric_seed_judge_b_tok_7a8b9c0d1e2f',
            'participant': 'rubric_seed_participant_tok_3f4e5d6c7b8a',
        }
        return {'HTTP_AUTHORIZATION': f"Bearer {tokens[persona]}"}

    def test_imports_all_fixture_ballots_and_jdg_07_constant_scores(self):
        self.assertEqual(Ballot.objects.count(), 126)
        self.assertEqual(JudgeAssignment.objects.count(), 126)
        self.assertEqual(BallotScore.objects.count(), 378)
        rubric = Rubric.objects.get(event__external_id='evt_01')
        self.assertEqual(list(rubric.criteria.values_list('name', flat=True)),
                         ['functionality', 'quality', 'innovation'])
        expected = {'prj_09': 4, 'prj_17': 4, 'prj_19': 4}
        for project, value in expected.items():
            ballot = Ballot.objects.get(assignment__judge__external_id='jdg_07',
                                        assignment__project__external_id=project)
            self.assertTrue(ballot.is_complete)
            self.assertEqual(set(ballot.scores.values_list('value', flat=True)), {value})

    def test_import_is_idempotent(self):
        call_command('seed_fixtures', stdout=StringIO())
        self.assertEqual(Rubric.objects.count(), 1)
        self.assertEqual(JudgeAssignment.objects.count(), 126)
        self.assertEqual(Ballot.objects.count(), 126)
        self.assertEqual(BallotScore.objects.count(), 378)

    def test_judge_cannot_see_peer_scores(self):
        response = self.client.get(reverse('judge_scores') + '?judge=jdg_07', **self._headers('judge_b'))
        self.assertEqual(response.status_code, 403)

    def test_participant_blocked(self):
        response = self.client.get(reverse('judge_scores'), **self._headers('participant'))
        self.assertEqual(response.status_code, 403)

    def test_organizer_scope_all_or_one_judge_and_judge_own_scope(self):
        all_response = self.client.get(reverse('judge_scores'), **self._headers('organizer'))
        one_response = self.client.get(reverse('judge_scores') + '?judge=jdg_07', **self._headers('organizer'))
        own_response = self.client.get(reverse('judge_scores'), **self._headers('judge_a'))
        self.assertEqual(all_response.status_code, 200)
        self.assertEqual(one_response.status_code, 200)
        self.assertEqual(own_response.status_code, 200)
        all_scores = all_response.json()['scores']
        one_scores = one_response.json()['scores']
        own_scores = own_response.json()['scores']
        self.assertEqual(len(all_scores), 126)
        self.assertEqual({r['judge'] for r in one_scores}, {'jdg_07'})
        self.assertEqual(one_scores, own_scores)

    def test_submit_ballot_updates_owned_assignment_and_progress_is_organizer_only(self):
        assignment = JudgeAssignment.objects.get(
            judge__external_id='jdg_07', project__external_id='prj_09',
        )
        judge = Actor(assignment.judge, assignment.event)
        ballot = submit_ballot(judge, assignment.pk,
                               {'functionality': 5, 'quality': 4, 'innovation': 3},
                               'Reviewed')
        self.assertTrue(ballot.is_complete)
        self.assertEqual(ballot.comment, 'Reviewed')
        self.assertIsNotNone(ballot.submitted_at)
        self.assertEqual(JudgeAssignment.objects.get(pk=assignment.pk).status, 'COMPLETED')
        self.assertEqual(ballot.scores.count(), 3)

        organizer = User.objects.get(email='organizer@rubric.local')
        organizer_actor = Actor(organizer, assignment.event)
        self.assertEqual(progress(organizer_actor), {'completed_projects': 41, 'total_projects': 41})
        with self.assertRaises(PermissionDenied):
            progress(judge)

        other_assignment = JudgeAssignment.objects.get(
            judge__external_id='jdg_29', project__external_id='prj_19',
        )
        with self.assertRaises(PermissionDenied):
            submit_ballot(judge, other_assignment.pk, {}, '')

    def test_judges_without_external_ids_only_see_their_own_ballots(self):
        event = Rubric.objects.get(event__external_id='evt_01').event
        project = JudgeAssignment.objects.first().project
        judges = []
        ballots = []
        for index in (1, 2):
            user = User.objects.create_user(
                email=f'null-id-judge-{index}@example.org',
                display_name=f'Null ID Judge {index}',
                external_id=None,
            )
            EventMembership.objects.create(event=event, user=user, role=EventRole.JUDGE)
            assignment = JudgeAssignment.objects.create(
                event=event, judge=user, project=project,
            )
            ballots.append(Ballot.objects.create(assignment=assignment, is_complete=True))
            judges.append(Actor(user, event))

        self.assertIsNone(judges[0].judge_external_id)
        visible_ids = set(get_scores(judges[0]).values_list('id', flat=True))
        self.assertIn(ballots[0].id, visible_ids)
        self.assertNotIn(ballots[1].id, visible_ids)

    def test_out_of_range_score_is_rejected_without_storing_it(self):
        rubric = Rubric.objects.get(event__external_id='evt_01')
        criterion = rubric.criteria.get(name='functionality')
        criterion.max_score = 3
        criterion.save(update_fields=['max_score'])
        event = rubric.event
        user = User.objects.create_user(
            email='bounds-test-judge@example.org', display_name='Bounds Test Judge',
        )
        EventMembership.objects.create(event=event, user=user, role=EventRole.JUDGE)
        assignment = JudgeAssignment.objects.create(
            event=event, judge=user, project=JudgeAssignment.objects.first().project,
        )
        judge = Actor(user, event)

        with self.assertRaisesRegex(ValueError, 'between 0 and 3'):
            save_ballot(judge, assignment.pk,
                        {'functionality': 3.01, 'quality': 4}, is_complete=True)

        self.assertFalse(Ballot.objects.filter(assignment=assignment).exists())
        self.assertFalse(BallotScore.objects.filter(ballot__assignment=assignment).exists())

    def test_trailing_draft_autosave_cannot_overwrite_completed_ballot(self):
        assignment = JudgeAssignment.objects.get(
            judge__external_id='jdg_07', project__external_id='prj_09',
        )
        judge = Actor(assignment.judge, assignment.event)
        ballot = assignment.ballot
        original_comment = ballot.comment
        original_submitted_at = ballot.submitted_at
        original_scores = dict(ballot.scores.values_list('criterion__name', 'value'))

        saved = save_ballot_draft(
            judge, assignment.pk, {'functionality': 1}, comment='late autosave',
        )

        self.assertEqual(saved.pk, ballot.pk)
        self.assertTrue(saved.is_complete)
        self.assertEqual(saved.comment, original_comment)
        self.assertEqual(saved.submitted_at, original_submitted_at)
        self.assertEqual(dict(saved.scores.values_list('criterion__name', 'value')), original_scores)
