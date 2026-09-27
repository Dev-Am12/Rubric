import csv
import io
import json
import math
import random
from datetime import timedelta
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounts.actors import Actor, PermissionDenied
from accounts.models import EventMembership, EventRole, User
from events.models import Event, Track
from judging.models import Ballot, BallotScore, JudgeAssignment, NormalizationRun, NormalizedScore, Rubric, RubricCriterion
from services.normalization import build_proof_artifact, get_run, normalized_output_bytes, normalized_score_payload, run
from submissions.models import Project, ProjectStatus
from teams.models import Team


class FixtureNormalizationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_fixtures', stdout=io.StringIO())
        cls.event = Event.objects.get(external_id='evt_01')
        cls.organizer = User.objects.get(email='organizer@rubric.local')
        cls.organizer_actor = Actor(cls.organizer, cls.event)

    def _leave_one_judge_out(self, external_id):
        assignments = list(
            JudgeAssignment.objects.filter(event=self.event, judge__external_id=external_id)
            .select_related('judge', 'project').order_by('pk')
        )
        saved_ballots = []
        for assignment in assignments:
            ballot = Ballot.objects.filter(assignment=assignment).first()
            if ballot is None:
                continue
            saved_ballots.append((
                ballot.pk, assignment.pk, ballot.comment, ballot.submitted_at,
                ballot.is_complete,
                [(score.pk, score.criterion_id, score.value) for score in ballot.scores.order_by('pk')],
            ))
        try:
            Ballot.objects.filter(assignment__in=assignments).delete()
            return run(self.organizer_actor)
        finally:
            for ballot_id, assignment_id, comment, submitted_at, is_complete, scores in saved_ballots:
                ballot = Ballot.objects.create(
                    pk=ballot_id, assignment_id=assignment_id, comment=comment,
                    submitted_at=submitted_at, is_complete=is_complete,
                )
                BallotScore.objects.bulk_create([
                    BallotScore(pk=score_id, ballot=ballot, criterion_id=criterion_id, value=value)
                    for score_id, criterion_id, value in scores
                ])

    def test_jdg07_constant_offset_and_leave_one_out_effect(self):
        baseline = run(self.organizer_actor)
        targets = ('prj_09', 'prj_17', 'prj_19')
        z_values = []
        baseline_values = {}
        for project_id in targets:
            contribution = next(
                item for item in baseline.parameters['contributions'][project_id]
                if item['judge_external_id'] == 'jdg_07'
            )
            z_values.append(contribution['z_score'])
            baseline_values[project_id] = float(baseline.scores.get(project__external_id=project_id).normalized_mean)
        for z_value in z_values[1:]:
            self.assertAlmostEqual(z_values[0], z_value, delta=1e-12)

        control_targets = ('prj_13', 'prj_26', 'prj_35')
        control_baseline_values = {
            project_id: float(baseline.scores.get(project__external_id=project_id).normalized_mean)
            for project_id in control_targets
        }
        without_jdg07 = self._leave_one_judge_out('jdg_07')
        jdg07_changes = {
            project_id: abs(baseline_values[project_id] - float(
                without_jdg07.scores.get(project__external_id=project_id).normalized_mean
            ))
            for project_id in targets
        }
        without_control = self._leave_one_judge_out('jdg_06')
        control_changes = {
            project_id: abs(control_baseline_values[project_id] - float(
                without_control.scores.get(project__external_id=project_id).normalized_mean
            ))
            for project_id in control_targets
        }

        # A factor-of-two envelope is a deliberately conservative same-order bound;
        # the observed non-thin jdg_07 shifts are about 0.15–0.17 vs. a control max ~0.17.
        control_bound = 2 * max(control_changes.values())
        self.assertLessEqual(jdg07_changes['prj_09'], control_bound)
        self.assertLessEqual(jdg07_changes['prj_17'], control_bound)
        # prj_19 is excluded from that comparison: jdg_07 removal leaves one reviewer,
        # independently explaining greater sensitivity through its review count.
        remaining_prj19_reviews = JudgeAssignment.objects.filter(
            event=self.event, project__external_id='prj_19', status='COMPLETED',
        ).exclude(judge__external_id='jdg_07').count()
        self.assertEqual(remaining_prj19_reviews, 1)
        self.assertGreater(jdg07_changes['prj_19'], 0)

    def test_constant_judge_no_div_by_zero(self):
        normalization = run(self.organizer_actor)
        statistics = next(
            row for row in normalization.parameters['judge_statistics']
            if row['judge_external_id'] == 'jdg_07'
        )
        self.assertEqual(statistics['n'], 3)
        self.assertEqual(statistics['raw_variance'], 0.0)
        self.assertGreater(statistics['shrunk_variance'], 0.0)
        self.assertTrue(math.isfinite(statistics['shrunk_variance']))
        json.dumps(normalization.parameters, allow_nan=False)
        for score in normalization.scores.all():
            for value in (score.raw_mean, score.normalized_mean, score.judge_graph_fiedler_value):
                if value is not None:
                    self.assertTrue(math.isfinite(float(value)))

    def test_thin_batches_flagged_real_fixture(self):
        normalization = run(self.organizer_actor)
        proof_rows = {
            row['project_id']: row for row in csv.DictReader(
                io.StringIO(build_proof_artifact(normalization).decode('utf-8'))
            )
        }
        for project_id in ('prj_10', 'prj_15', 'prj_18', 'prj_19', 'prj_24', 'prj_29', 'prj_39', 'prj_40'):
            self.assertEqual(normalization.parameters['project_review_counts'][project_id], 2)
            self.assertIn('thin_batch', {
                flag['type'] for flag in normalization.parameters['project_flags'][project_id]
            })
            payload = normalized_score_payload(normalization.scores.get(project__external_id=project_id))
            self.assertEqual(payload['review_count'], 2)
            self.assertIn('thin_batch', {flag['type'] for flag in payload['flags']})
            self.assertEqual(int(proof_rows[project_id]['review_count']), 2)
            self.assertIn('thin_batch', {flag['type'] for flag in json.loads(proof_rows[project_id]['flags'])})

    def test_prj19_compounding_flag(self):
        normalization = run(self.organizer_actor)
        payload = normalized_score_payload(normalization.scores.get(project__external_id='prj_19'))
        flags = payload['flags']
        self.assertIn('thin_batch', {flag['type'] for flag in flags})
        constant_flags = [flag for flag in flags if flag['type'] == 'constant_judge']
        self.assertEqual([flag['judge_external_id'] for flag in constant_flags], ['jdg_07'])
        self.assertIn('jdg_07', {
            flag['judge_external_id'] for flag in normalization.parameters['judge_flags']
        })

    def test_duplicate_never_lost_default_canonical(self):
        normalization = run(self.organizer_actor)
        earlier = Project.objects.get(event=self.event, external_id='prj_07')
        later = Project.objects.get(event=self.event, external_id='prj_41')
        self.assertIsNone(later.is_duplicate_of_id)
        self.assertEqual(earlier.is_duplicate_of_id, later.pk)
        earlier_score = normalization.scores.get(project=earlier)
        later_score = normalization.scores.get(project=later)
        self.assertIsNone(earlier_score.rank)
        self.assertIsNone(earlier_score.normalized_mean)
        self.assertIsNotNone(earlier_score.raw_mean)
        self.assertIsNotNone(later_score.rank)
        self.assertIn('duplicate', {
            flag['type'] for flag in normalization.parameters['project_flags']['prj_07']
        })
        self.assertEqual(normalization.scores.count(), Project.objects.filter(event=self.event).count())
        gallery_response = self.client.get('/projects')
        gallery_project_ids = {project.pk for project in gallery_response.context['projects']}
        self.assertNotIn(earlier.pk, gallery_project_ids)
        self.assertIn(later.pk, gallery_project_ids)

    def test_deterministic_output(self):
        first = run(self.organizer_actor)
        second = run(self.organizer_actor)
        self.assertEqual(normalized_output_bytes(first), normalized_output_bytes(second))

    def test_normalization_proof_artifact(self):
        normalization = run(self.organizer_actor)
        payload = build_proof_artifact(normalization)
        rows = list(csv.DictReader(io.StringIO(payload.decode('utf-8'))))
        self.assertEqual(len(rows), Project.objects.filter(event=self.event).count())
        self.assertIn('rank_change', rows[0])
        self.assertIn('review_count', rows[0])
        output = Path(__file__).resolve().parents[1] / f'.normalization-proof-test-{normalization.pk}.csv'
        try:
            call_command('export_normalization_proof', normalization.pk,
                         output=str(output), stdout=io.StringIO())
            self.assertEqual(output.read_bytes(), payload)
        finally:
            output.unlink(missing_ok=True)

    def test_get_run_is_organizer_scoped(self):
        normalization = run(self.organizer_actor)
        self.assertEqual(get_run(self.organizer_actor, normalization.pk), normalization)
        judge = User.objects.get(external_id='jdg_07')
        with self.assertRaises(PermissionDenied):
            get_run(Actor(judge, self.event), normalization.pk)


class DisconnectedNormalizationTests(TestCase):
    def test_shrinkage_beats_raw_on_synthetic_ground_truth(self):
        rng = random.Random(2026)
        true_quality = {f'syn_prj_{index:02d}': rng.uniform(1.5, 4.5) for index in range(20)}
        offsets = {f'syn_jdg_{index:02d}': -1.5 + index / 3 for index in range(10)}
        organizer = User.objects.create_user(email='synthetic-org@example.org', display_name='Organizer')
        event = Event.objects.create(
            slug='synthetic-normalization', name='Synthetic Normalization',
            submissions_close_at=timezone.now() + timedelta(days=1),
        )
        EventMembership.objects.create(event=event, user=organizer, role=EventRole.ORGANIZER)
        track = Track.objects.create(event=event, name='Synthetic Track')
        rubric = Rubric.objects.create(event=event, name='Synthetic Rubric')
        criterion = RubricCriterion.objects.create(
            rubric=rubric, name='functionality', weight=1, max_score=5, order=0,
        )
        judges = {}
        for external_id in sorted(offsets):
            user = User.objects.create_user(
                email=f'{external_id}@example.org', display_name=external_id,
                external_id=external_id,
            )
            EventMembership.objects.create(event=event, user=user, role=EventRole.JUDGE)
            judges[external_id] = user

        raw_by_project = {}
        for index, external_id in enumerate(sorted(true_quality)):
            team = Team.objects.create(
                event=event, name=f'Synthetic Team {index}', invite_code=f'synthetic-invite-{index}',
            )
            project = Project.objects.create(
                event=event, team=team, track=track, title=external_id,
                summary='Fixed-seed planted quality', status=ProjectStatus.SUBMITTED,
                external_id=external_id,
            )
            scores = []
            for judge_index in (index % 10, (index + 1) % 10, (index + 2) % 10):
                judge_id = f'syn_jdg_{judge_index:02d}'
                observed = max(1.0, min(5.0, true_quality[external_id] + offsets[judge_id] + rng.gauss(0, 0.2)))
                scores.append(observed)
                assignment = JudgeAssignment.objects.create(event=event, judge=judges[judge_id], project=project)
                ballot = Ballot.objects.create(assignment=assignment, is_complete=True)
                BallotScore.objects.create(
                    ballot=ballot, criterion=criterion, value=round(observed, 4),
                )
            raw_by_project[external_id] = sum(scores) / len(scores)

        normalized = run(Actor(organizer, event))
        normalized_by_project = {
            row.project.external_id: float(row.normalized_mean)
            for row in normalized.scores.select_related('project')
        }

        def descending_ranks(values):
            ordered = sorted(values, key=lambda key: (-values[key], key))
            return {key: rank for rank, key in enumerate(ordered, start=1)}

        def spearman(left, right):
            left_ranks = descending_ranks(left)
            right_ranks = descending_ranks(right)
            keys = sorted(left_ranks)
            mean_left = sum(left_ranks[key] for key in keys) / len(keys)
            mean_right = sum(right_ranks[key] for key in keys) / len(keys)
            numerator = sum((left_ranks[key] - mean_left) * (right_ranks[key] - mean_right) for key in keys)
            denominator = math.sqrt(
                sum((left_ranks[key] - mean_left) ** 2 for key in keys)
                * sum((right_ranks[key] - mean_right) ** 2 for key in keys)
            )
            return numerator / denominator

        raw_correlation = spearman(raw_by_project, true_quality)
        normalized_correlation = spearman(normalized_by_project, true_quality)
        self.assertGreater(normalized_correlation, raw_correlation)

    def test_disconnected_graph_synthetic(self):
        now = timezone.now()
        organizer = User.objects.create_user(email='norm-org@example.org', display_name='Organizer')
        event = Event.objects.create(
            slug='disconnected-normalization', name='Disconnected Normalization',
            submissions_close_at=now + timedelta(days=1),
        )
        EventMembership.objects.create(event=event, user=organizer, role=EventRole.ORGANIZER)
        track = Track.objects.create(event=event, name='Track')
        rubric = Rubric.objects.create(event=event, name='Default')
        criterion = RubricCriterion.objects.create(
            rubric=rubric, name='functionality', weight=1, max_score=5, order=0,
        )
        judge_users = []
        for index in range(4):
            judge = User.objects.create_user(
                email=f'disconnected-judge-{index}@example.org',
                display_name=f'Disconnected Judge {index}',
                external_id=f'dj_{index}',
            )
            EventMembership.objects.create(event=event, user=judge, role=EventRole.JUDGE)
            judge_users.append(judge)

        for component, judges in enumerate((judge_users[:2], judge_users[2:])):
            base = 1 + component * 2
            for project_offset, value in enumerate((base, base + 1)):
                team = Team.objects.create(
                    event=event, name=f'Team {component}-{project_offset}',
                    invite_code=f'invite-{component}-{project_offset}',
                )
                project = Project.objects.create(
                    event=event, team=team, track=track,
                    title=f'Project {component}-{project_offset}', summary='Synthetic',
                    status=ProjectStatus.SUBMITTED,
                )
                for judge in judges:
                    assignment = JudgeAssignment.objects.create(
                        event=event, judge=judge, project=project,
                    )
                    ballot = Ballot.objects.create(assignment=assignment, is_complete=True)
                    BallotScore.objects.create(ballot=ballot, criterion=criterion, value=value)

        actor = Actor(organizer, event)
        normalization = run(actor)
        self.assertEqual(normalization.parameters['component_count'], 2)
        self.assertEqual(normalization.parameters['ranking_scope'], 'component')
        scores = list(normalization.scores.order_by('project_id'))
        self.assertEqual({score.judge_graph_component_id for score in scores}, {1, 2})
        for component_id in (1, 2):
            component_scores = [score for score in scores if score.judge_graph_component_id == component_id]
            self.assertEqual(sorted(score.rank for score in component_scores), [1, 2])
            self.assertTrue(all(score.judge_graph_fiedler_value is not None for score in component_scores))
        self.assertEqual(len({score.rank for score in scores}), 2)

        acknowledged = run(actor, allow_disconnected_ranking=True)
        self.assertEqual(acknowledged.parameters['ranking_scope'], 'global')
        self.assertTrue(acknowledged.parameters['allow_disconnected_ranking'])
        self.assertEqual(sorted(score.rank for score in acknowledged.scores.all()), [1, 2, 3, 4])
