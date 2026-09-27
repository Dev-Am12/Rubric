import io
from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounts.actors import Actor, PermissionDenied
from accounts.models import EventMembership, EventRole, JudgeTrackEligibility, User
from events.models import Event, Track
from judging.models import AssignmentStatus, Ballot, JudgeAssignment, Rubric, RubricCriterion
from services.assignment import compute_graph_health, get_run, run
from submissions.models import Project, ProjectStatus
from teams.models import Team, TeamMembership


class AssignmentFixture:
    def make_event(self, suffix):
        organizer = User.objects.create_user(email=f'{suffix}-org@example.org', display_name='Organizer')
        event = Event.objects.create(
            slug=f'assignment-{suffix}', name=f'Assignment {suffix}',
            submissions_close_at=timezone.now() + timedelta(days=1),
        )
        EventMembership.objects.create(event=event, user=organizer, role=EventRole.ORGANIZER)
        return event, organizer, Actor(organizer, event)

    def make_track(self, event, suffix):
        return Track.objects.create(event=event, name=f'Track {suffix}', external_id=f'{event.slug}-{suffix}')

    def make_judge(self, event, suffix, tracks):
        user = User.objects.create_user(
            email=f'{event.slug}-{suffix}@example.org', display_name=suffix,
            external_id=f'{event.slug}-{suffix}',
        )
        membership = EventMembership.objects.create(event=event, user=user, role=EventRole.JUDGE)
        for track in tracks:
            JudgeTrackEligibility.objects.create(event_membership=membership, track=track)
        return user

    def make_project(self, event, track, suffix, members=()):
        team = Team.objects.create(
            event=event, name=f'Team {suffix}', invite_code=f'{event.slug}-invite-{suffix}',
        )
        for member in members:
            TeamMembership.objects.create(team=team, user=member)
        return Project.objects.create(
            event=event, team=team, track=track, title=f'Project {suffix}',
            summary='Synthetic assignment project', status=ProjectStatus.SUBMITTED,
            external_id=f'{event.slug}-{suffix}',
        )


class AssignmentAlgorithmTests(AssignmentFixture, TestCase):
    def test_track_eligibility_never_violated(self):
        event, _, actor = self.make_event('eligibility')
        left, right = self.make_track(event, 'left'), self.make_track(event, 'right')
        self.make_judge(event, 'left-judge', [left])
        self.make_judge(event, 'right-judge', [right])
        self.make_judge(event, 'both-judge', [left, right])
        self.make_project(event, left, 'left-project')
        self.make_project(event, right, 'right-project')
        run(actor, k=2, seed=91)
        for assignment in JudgeAssignment.objects.filter(event=event).select_related('judge', 'project__track'):
            self.assertTrue(JudgeTrackEligibility.objects.filter(
                event_membership__event=event,
                event_membership__user=assignment.judge,
                event_membership__role=EventRole.JUDGE,
                track=assignment.project.track,
            ).exists())

    def test_conflict_of_interest_never_assigned(self):
        event, _, actor = self.make_event('conflict')
        track = self.make_track(event, 'track')
        conflicted = self.make_judge(event, 'conflicted', [track])
        project = self.make_project(event, track, 'project', members=[conflicted])
        assignment_run = run(actor, k=1, seed=3)
        self.assertFalse(JudgeAssignment.objects.filter(event=event, judge=conflicted, project=project).exists())
        self.assertEqual(assignment_run.under_coverage, [{
            'project_id': project.external_id, 'got': 0, 'wanted': 1,
        }])

    def test_load_balanced_within_bound(self):
        event, _, actor = self.make_event('balanced')
        track = self.make_track(event, 'track')
        judges = [self.make_judge(event, f'judge-{index:02d}', [track]) for index in range(10)]
        for index in range(30):
            self.make_project(event, track, f'project-{index:02d}')
        run(actor, k=3, seed=11)
        loads = [JudgeAssignment.objects.filter(event=event, judge=judge).count() for judge in judges]
        self.assertLessEqual(max(loads) - min(loads), 1)

    def test_under_coverage_reported_not_hidden(self):
        event, _, actor = self.make_event('undercoverage')
        track = self.make_track(event, 'track')
        self.make_judge(event, 'judge-one', [track])
        self.make_judge(event, 'judge-two', [track])
        projects = [self.make_project(event, track, f'project-{index}') for index in range(2)]
        assignment_run = run(actor, k=3, seed=17)
        expected = sorted([
            {'project_id': project.external_id, 'got': 2, 'wanted': 3} for project in projects
        ], key=lambda row: row['project_id'])
        self.assertEqual(sorted(assignment_run.under_coverage, key=lambda row: row['project_id']), expected)
        self.assertTrue(all(JudgeAssignment.objects.filter(event=event, project=project).count() == 2 for project in projects))

    def test_assignment_additive_never_reshuffles_submitted_ballot(self):
        event, _, actor = self.make_event('additive')
        track = self.make_track(event, 'track')
        judge_one = self.make_judge(event, 'judge-one', [track])
        project = self.make_project(event, track, 'project')
        run(actor, k=1, seed=1)
        original = JudgeAssignment.objects.get(event=event, judge=judge_one, project=project)
        original.status = AssignmentStatus.COMPLETED
        original.save(update_fields=['status'])
        Ballot.objects.create(assignment=original, is_complete=True, submitted_at=timezone.now())
        original_snapshot = (original.pk, original.judge_id, original.project_id, original.status, original.assigned_at)
        self.make_judge(event, 'judge-two', [track])
        run(actor, k=2, seed=1)
        original.refresh_from_db()
        self.assertEqual(
            (original.pk, original.judge_id, original.project_id, original.status, original.assigned_at),
            original_snapshot,
        )
        self.assertTrue(Ballot.objects.filter(assignment=original, is_complete=True).exists())
        self.assertEqual(JudgeAssignment.objects.filter(event=event, project=project).count(), 2)

    def test_anchor_injection_only_via_real_multitrack_judge(self):
        event, _, actor = self.make_event('anchor')
        first, second = self.make_track(event, 'first'), self.make_track(event, 'second')
        first_judge = self.make_judge(event, 'first-judge', [first])
        second_judge = self.make_judge(event, 'second-judge', [second])
        anchor = self.make_judge(event, 'anchor', [first, second])
        first_project = self.make_project(event, first, 'first-project')
        second_project = self.make_project(event, second, 'second-project')
        JudgeAssignment.objects.create(event=event, judge=first_judge, project=first_project)
        JudgeAssignment.objects.create(event=event, judge=anchor, project=first_project)
        JudgeAssignment.objects.create(event=event, judge=second_judge, project=second_project)
        assignment_run = run(actor, k=1, seed=23)
        self.assertEqual(assignment_run.connectivity_report['n_components'], 1)
        self.assertEqual(len(assignment_run.anchor_injections), 1)
        injection = assignment_run.anchor_injections[0]
        self.assertEqual(injection['judge_external_id'], anchor.external_id)
        self.assertEqual(injection['project_id'], second_project.external_id)
        self.assertTrue(JudgeAssignment.objects.filter(event=event, judge=anchor, project=second_project).exists())

    def test_deterministic_given_seed(self):
        def assignment_pairs(suffix):
            event, _, actor = self.make_event(suffix)
            track = self.make_track(event, 'track')
            for index in range(4):
                self.make_judge(event, f'judge-{index}', [track])
            for index in range(6):
                self.make_project(event, track, f'project-{index}')
            run(actor, k=2, seed=808)
            return sorted((assignment.judge.display_name, assignment.project.title) for assignment in JudgeAssignment.objects.filter(event=event).select_related('judge', 'project'))
        self.assertEqual(assignment_pairs('deterministic-one'), assignment_pairs('deterministic-two'))

    def test_get_run_organizer_only(self):
        event, _, actor = self.make_event('get-run')
        track = self.make_track(event, 'track')
        judge = self.make_judge(event, 'judge', [track])
        self.make_project(event, track, 'project')
        assignment_run = run(actor, k=1, seed=1)
        self.assertEqual(get_run(actor, assignment_run.pk), assignment_run)
        with self.assertRaises(PermissionDenied):
            get_run(Actor(judge, event), assignment_run.pk)

    def test_singleton_component_fiedler_is_null(self):
        event, _, _ = self.make_event('singleton')
        track = self.make_track(event, 'track')
        self.make_judge(event, 'judge', [track])
        health = compute_graph_health(event)
        self.assertEqual(health['n_components'], 1)
        self.assertEqual(health['component_sizes'], [1])
        self.assertIsNone(health['fiedler_value_global'])
        self.assertEqual(health['fiedler_value_per_component'], [None])


class FixtureGraphHealthTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_fixtures', stdout=io.StringIO())

    def test_graph_health_matches_manual_bfs_on_real_fixture(self):
        event = Event.objects.get(external_id='evt_01')
        health = compute_graph_health(event)
        self.assertEqual(health['n_components'], 1)
        self.assertEqual(health['component_sizes'], [30])

    def test_fixture_completed_assignments_unchanged_after_live_run(self):
        event = Event.objects.get(external_id='evt_01')
        organizer = User.objects.get(email='organizer@rubric.local')
        before = list(JudgeAssignment.objects.filter(
            event=event, status=AssignmentStatus.COMPLETED,
        ).order_by('pk').values_list('pk', 'judge_id', 'project_id', 'status', 'assigned_at'))
        # The imported historical fixture has at least two completed reviews per
        # project, so its minimum established coverage target adds no new rows.
        assignment_run = run(Actor(organizer, event), k=2, seed=101)
        after = list(JudgeAssignment.objects.filter(
            event=event, status=AssignmentStatus.COMPLETED,
        ).order_by('pk').values_list('pk', 'judge_id', 'project_id', 'status', 'assigned_at'))
        self.assertEqual(before, after)
        self.assertEqual(JudgeAssignment.objects.filter(event=event).count(), 126)
        self.assertEqual(assignment_run.under_coverage, [])
