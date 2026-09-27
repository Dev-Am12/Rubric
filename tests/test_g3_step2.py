"""
Tests for G3 Step 2 — Judge-facing UI.

Coverage:
  1. /judge/queue — a judge's own assignments (pending/completed) via services.judging.
  2. /judge/ballots/{assignment_id} — two-pane layout: submission material on left (fixed),
     rubric criteria + comment on right (scrolls independently).
  3. Autosave — hx-trigger="change, keyup delay:1s" posting partial save keeps draft intact
     without completing the ballot or assignment status.
  4. Submit-and-advance — submit_ballot() marks ballot complete, transitions assignment to
     COMPLETED, and redirects to the next pending assignment (or queue when finished).
  5. Zero-leak principle — zero code path or data leak of another judge's scores.
  6. /organizer/progress — minimal view returning raw progress numbers, organizer-only.
  7. Authz & unassigned judge — judge_unassigned gets 403 on an assignment not theirs.
"""

from io import StringIO
from django.core.management import call_command
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from accounts.actors import Actor, PermissionDenied
from accounts.models import AuthToken, EventMembership, EventRole, User
from events.models import Event, Track
from judging.models import AssignmentStatus, Ballot, BallotScore, JudgeAssignment, Rubric, RubricCriterion
from services import judging as judging_services
from submissions.models import Project, ProjectStatus
from teams.models import Team


class G3Step2JudgeUITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_fixtures', stdout=StringIO())

        cls.event = Event.objects.get(external_id='evt_01')
        cls.organizer_user = User.objects.get(email='organizer@rubric.local')
        cls.judge_a_user = User.objects.get(external_id='jdg_07')
        cls.judge_b_user = User.objects.get(external_id='jdg_29')
        part_tok_hash = AuthToken.hash_token('rubric_seed_participant_tok_3f4e5d6c7b8a')
        cls.participant_user = AuthToken.objects.get(token_hash=part_tok_hash).user

        # Create judge_unassigned: a judge on evt_01 with zero assignments
        cls.judge_unassigned_user = User.objects.create_user(
            email='judge_unassigned@rubric.local',
            display_name='Judge Unassigned',
            external_id='jdg_unassigned',
        )
        EventMembership.objects.create(
            event=cls.event,
            user=cls.judge_unassigned_user,
            role=EventRole.JUDGE,
        )
        _, cls.unassigned_token = AuthToken.create_token(
            cls.judge_unassigned_user, label='unassigned-judge-token',
        )

        cls.tokens = {
            'organizer': 'rubric_seed_organizer_tok_9f8e7d6c5b4a',
            'judge_a': 'rubric_seed_judge_a_tok_1a2b3c4d5e6f',
            'judge_b': 'rubric_seed_judge_b_tok_7a8b9c0d1e2f',
            'participant': 'rubric_seed_participant_tok_3f4e5d6c7b8a',
            'judge_unassigned': cls.unassigned_token,
        }

    def _headers(self, persona):
        return {'HTTP_AUTHORIZATION': f"Bearer {self.tokens[persona]}"}

    # -----------------------------------------------------------------------
    # 1. /judge/queue
    # -----------------------------------------------------------------------

    def test_judge_queue_shows_own_assignments(self):
        """Assigned judge sees their own assignments on /judge/queue."""
        response = self.client.get(reverse('judge_queue'), **self._headers('judge_a'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Judge Assignment Queue')
        self.assertContains(response, 'prj_09')
        self.assertContains(response, 'prj_17')
        self.assertContains(response, 'prj_19')

    def test_judge_unassigned_sees_empty_queue(self):
        """judge_unassigned accesses /judge/queue with 200, seeing zero assignments."""
        response = self.client.get(reverse('judge_queue'), **self._headers('judge_unassigned'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '0</strong> of <strong>0</strong> completed')

    def test_non_judges_blocked_from_queue(self):
        """Anonymous gets 401 and participant gets 403 on /judge/queue."""
        anon_resp = self.client.get(reverse('judge_queue'))
        self.assertEqual(anon_resp.status_code, 401)

        part_resp = self.client.get(reverse('judge_queue'), **self._headers('participant'))
        self.assertEqual(part_resp.status_code, 403)

    # -----------------------------------------------------------------------
    # 2. /judge/ballots/{assignment_id} & Isolation Checks
    # -----------------------------------------------------------------------

    def test_judge_can_open_own_ballot(self):
        """Assigned judge opens their own ballot and sees two-pane layout with criteria."""
        assignment = JudgeAssignment.objects.filter(judge=self.judge_a_user).first()
        response = self.client.get(
            reverse('judge_ballot', kwargs={'assignment_id': assignment.pk}),
            **self._headers('judge_a'),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'left-pane')
        self.assertContains(response, 'right-pane')
        self.assertContains(response, assignment.project.title)
        self.assertContains(response, 'functionality')
        self.assertContains(response, 'quality')
        self.assertContains(response, 'innovation')
        self.assertContains(response, 'Submit &amp; Next')

    def test_judge_unassigned_gets_403_on_assignment_not_theirs(self):
        """judge_unassigned gets 403 accessing an assignment belonging to another judge."""
        assignment = JudgeAssignment.objects.filter(judge=self.judge_a_user).first()
        response = self.client.get(
            reverse('judge_ballot', kwargs={'assignment_id': assignment.pk}),
            **self._headers('judge_unassigned'),
        )
        self.assertEqual(response.status_code, 403)

    def test_peer_judge_gets_403_on_assignment_not_theirs(self):
        """judge_b gets 403 accessing judge_a's assignment for prj_09."""
        assignment = JudgeAssignment.objects.get(
            judge=self.judge_a_user, project__external_id='prj_09',
        )
        response = self.client.get(
            reverse('judge_ballot', kwargs={'assignment_id': assignment.pk}),
            **self._headers('judge_b'),
        )
        self.assertEqual(response.status_code, 403)

    def test_participant_and_anon_get_403_or_401_on_ballot(self):
        """Participant gets 403, anon gets 401 on ballot screen."""
        assignment = JudgeAssignment.objects.first()
        anon_resp = self.client.get(
            reverse('judge_ballot', kwargs={'assignment_id': assignment.pk}),
        )
        self.assertEqual(anon_resp.status_code, 401)

        part_resp = self.client.get(
            reverse('judge_ballot', kwargs={'assignment_id': assignment.pk}),
            **self._headers('participant'),
        )
        self.assertEqual(part_resp.status_code, 403)

    # -----------------------------------------------------------------------
    # 3. Autosave (Partial save via HTMX)
    # -----------------------------------------------------------------------

    def test_autosave_preserves_partial_scores_and_leaves_ballot_incomplete(self):
        """
        Autosave posts partial score; saves BallotScore and comment,
        leaves is_complete=False and status=PENDING.
        """
        # Create a fresh pending assignment for judge_a
        project = Project.objects.filter(event=self.event).exclude(
            judge_assignments__judge=self.judge_a_user,
        ).first()
        assignment = JudgeAssignment.objects.create(
            event=self.event,
            judge=self.judge_a_user,
            project=project,
            status=AssignmentStatus.PENDING,
        )

        rubric = self.event.rubrics.first()
        func_crit = rubric.criteria.get(name='functionality')

        # Trigger autosave with partial score (1 criterion only) and comment
        autosave_url = reverse('judge_ballot_autosave', kwargs={'assignment_id': assignment.pk})
        response = self.client.post(
            autosave_url,
            {f'score_{func_crit.pk}': '4', 'comment': 'Work in progress review'},
            **self._headers('judge_a'),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Draft autosaved at')

        # Verify ballot state in database
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, AssignmentStatus.PENDING)
        ballot = assignment.ballot
        self.assertFalse(ballot.is_complete)
        self.assertEqual(ballot.comment, 'Work in progress review')
        self.assertEqual(ballot.scores.count(), 1)
        self.assertEqual(ballot.scores.first().value, 4)

        # GET request to ballot screen displays saved draft values
        get_response = self.client.get(
            reverse('judge_ballot', kwargs={'assignment_id': assignment.pk}),
            **self._headers('judge_a'),
        )
        self.assertEqual(get_response.status_code, 200)
        self.assertContains(get_response, 'Work in progress review')
        self.assertContains(get_response, 'Draft saved')

    def test_autosave_forbidden_for_unassigned_judge(self):
        """judge_unassigned gets 403 when attempting to autosave someone else's assignment."""
        assignment = JudgeAssignment.objects.filter(judge=self.judge_a_user).first()
        autosave_url = reverse('judge_ballot_autosave', kwargs={'assignment_id': assignment.pk})
        response = self.client.post(
            autosave_url,
            {'comment': 'Hacked comment'},
            **self._headers('judge_unassigned'),
        )
        self.assertEqual(response.status_code, 403)

    # -----------------------------------------------------------------------
    # 4. Submit-and-Advance Lifecycle
    # -----------------------------------------------------------------------

    def test_submit_ballot_marks_complete_and_advances_to_next_pending(self):
        """
        Submitting ballot completes assignment and redirects to next pending assignment,
        or to queue if no more pending assignments exist.
        """
        # Create two pending assignments for judge_a
        available_projects = list(Project.objects.filter(event=self.event).exclude(
            judge_assignments__judge=self.judge_a_user,
        )[:2])

        assign_1 = JudgeAssignment.objects.create(
            event=self.event, judge=self.judge_a_user, project=available_projects[0],
            status=AssignmentStatus.PENDING,
        )
        assign_2 = JudgeAssignment.objects.create(
            event=self.event, judge=self.judge_a_user, project=available_projects[1],
            status=AssignmentStatus.PENDING,
        )

        rubric = self.event.rubrics.first()
        criteria = list(rubric.criteria.all())

        # Submit first assignment
        post_data = {
            f'score_{criteria[0].pk}': '5',
            f'score_{criteria[1].pk}': '4',
            f'score_{criteria[2].pk}': '5',
            'comment': 'Exceptional submission',
        }
        submit_url_1 = reverse('judge_ballot', kwargs={'assignment_id': assign_1.pk})
        response_1 = self.client.post(submit_url_1, post_data, **self._headers('judge_a'))

        # Should redirect to next pending assignment (assign_2)
        expected_next_url = reverse('judge_ballot', kwargs={'assignment_id': assign_2.pk})
        self.assertRedirects(response_1, expected_next_url)

        assign_1.refresh_from_db()
        self.assertEqual(assign_1.status, AssignmentStatus.COMPLETED)
        self.assertTrue(assign_1.ballot.is_complete)
        self.assertEqual(assign_1.ballot.scores.count(), 3)

        # Now submit second assignment
        submit_url_2 = reverse('judge_ballot', kwargs={'assignment_id': assign_2.pk})
        response_2 = self.client.post(submit_url_2, post_data, **self._headers('judge_a'))

        # No more pending assignments for judge_a; redirects to queue
        self.assertRedirects(response_2, reverse('judge_queue'))

        assign_2.refresh_from_db()
        self.assertEqual(assign_2.status, AssignmentStatus.COMPLETED)
        self.assertTrue(assign_2.ballot.is_complete)

    # -----------------------------------------------------------------------
    # 5. Strict Zero-Leak Verification
    # -----------------------------------------------------------------------

    def test_ballot_screen_never_contains_peer_judge_scores(self):
        """
        Verify that no other judge's scores or feedback ever appear on the ballot
        or queue screens.
        """
        # prj_19 is judged by both jdg_07 (judge_a) and jdg_29 (judge_b)
        assign_a = JudgeAssignment.objects.get(
            judge=self.judge_a_user, project__external_id='prj_19',
        )
        assign_b = JudgeAssignment.objects.get(
            judge=self.judge_b_user, project__external_id='prj_19',
        )
        # Give judge_b a distinct unique comment
        assign_b.ballot.comment = "CONFIDENTIAL_JUDGE_B_PRIVATE_FEEDBACK_XYZ123"
        assign_b.ballot.save()

        # Judge A views their ballot for prj_19
        resp = self.client.get(
            reverse('judge_ballot', kwargs={'assignment_id': assign_a.pk}),
            **self._headers('judge_a'),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "CONFIDENTIAL_JUDGE_B_PRIVATE_FEEDBACK_XYZ123")
        self.assertNotContains(resp, "jdg_29")

        # Judge A views their queue
        queue_resp = self.client.get(reverse('judge_queue'), **self._headers('judge_a'))
        self.assertEqual(queue_resp.status_code, 200)
        self.assertNotContains(queue_resp, "CONFIDENTIAL_JUDGE_B_PRIVATE_FEEDBACK_XYZ123")
        self.assertNotContains(queue_resp, "jdg_29")

    # -----------------------------------------------------------------------
    # 6. Minimal Organizer Progress View
    # -----------------------------------------------------------------------

    def test_organizer_progress_accessible_only_to_organizer(self):
        """Organizer accesses /organizer/progress with 200; judges and participants get 403."""
        # Organizer gets 200 HTML
        org_resp = self.client.get(reverse('organizer_progress_page'), **self._headers('organizer'))
        self.assertEqual(org_resp.status_code, 200)
        self.assertContains(org_resp, 'Event Judging Progress')
        self.assertContains(org_resp, 'Completed Projects')
        self.assertContains(org_resp, 'Total Projects')

        # Organizer gets JSON with Accept header
        org_json_resp = self.client.get(
            reverse('organizer_progress_page'),
            HTTP_ACCEPT='application/json',
            **self._headers('organizer'),
        )
        self.assertEqual(org_json_resp.status_code, 200)
        data = org_json_resp.json()
        self.assertIn('completed_projects', data)
        self.assertIn('total_projects', data)

        # Judge gets 403
        judge_resp = self.client.get(reverse('organizer_progress_page'), **self._headers('judge_a'))
        self.assertEqual(judge_resp.status_code, 403)

        # Participant gets 403
        part_resp = self.client.get(reverse('organizer_progress_page'), **self._headers('participant'))
        self.assertEqual(part_resp.status_code, 403)

        # Anonymous gets 401
        anon_resp = self.client.get(reverse('organizer_progress_page'))
        self.assertEqual(anon_resp.status_code, 401)
