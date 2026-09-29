"""
Tests for G4 Step 3:
- /organizer (dashboard): Live progress, track under-coverage, graph health, flags.
- /organizer/assignments: Trigger run, AssignmentRun history, connectivity report.
- /organizer/normalization: Trigger run, raw/normalized/rank-change table (Normalization Proof artifact).
- Real /api/export.csv: Organizer-only auth (401/403 for anon/participant), real per-project CSV data with flags.
"""

import csv
import io

from django.core.management import call_command
from django.test import TestCase

from accounts.actors import Actor
from accounts.models import User
from events.models import Event
from judging.models import AssignmentRun, NormalizationRun
from submissions.models import Project


class OrganizerDashboardAndExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_fixtures', stdout=io.StringIO())
        cls.event = Event.objects.get(external_id='evt_01')

        cls.organizer_user = User.objects.get(email='organizer@rubric.local')
        cls.judge_user = User.objects.get(external_id='jdg_07')
        cls.judge_b_user = User.objects.get(external_id='jdg_29')

        cls.organizer_token = 'rubric_seed_organizer_tok_9f8e7d6c5b4a'
        cls.judge_token = 'rubric_seed_judge_a_tok_1a2b3c4d5e6f'
        cls.participant_token = 'rubric_seed_participant_tok_3f4e5d6c7b8a'

    def _auth_header(self, token):
        return {'HTTP_AUTHORIZATION': f'Bearer {token}'}

    # -------------------------------------------------------------------------
    # Route Authorization Tests
    # -------------------------------------------------------------------------

    def test_organizer_dashboard_authz(self):
        # Anonymous -> 401
        res_anon = self.client.get('/organizer')
        self.assertEqual(res_anon.status_code, 401)

        # Participant -> 403
        res_part = self.client.get('/organizer', **self._auth_header(self.participant_token))
        self.assertEqual(res_part.status_code, 403)

        # Judge -> 403
        res_judge = self.client.get('/organizer', **self._auth_header(self.judge_token))
        self.assertEqual(res_judge.status_code, 403)

        # Organizer -> 200
        res_org = self.client.get('/organizer', **self._auth_header(self.organizer_token))
        self.assertEqual(res_org.status_code, 200)

    def test_organizer_assignments_authz(self):
        # Anonymous -> 401
        res_anon = self.client.get('/organizer/assignments')
        self.assertEqual(res_anon.status_code, 401)

        # Participant -> 403
        res_part = self.client.get('/organizer/assignments', **self._auth_header(self.participant_token))
        self.assertEqual(res_part.status_code, 403)

        # Judge -> 403
        res_judge = self.client.get('/organizer/assignments', **self._auth_header(self.judge_token))
        self.assertEqual(res_judge.status_code, 403)

        # Organizer -> 200
        res_org = self.client.get('/organizer/assignments', **self._auth_header(self.organizer_token))
        self.assertEqual(res_org.status_code, 200)

    def test_organizer_normalization_authz(self):
        # Anonymous -> 401
        res_anon = self.client.get('/organizer/normalization')
        self.assertEqual(res_anon.status_code, 401)

        # Participant -> 403
        res_part = self.client.get('/organizer/normalization', **self._auth_header(self.participant_token))
        self.assertEqual(res_part.status_code, 403)

        # Judge -> 403
        res_judge = self.client.get('/organizer/normalization', **self._auth_header(self.judge_token))
        self.assertEqual(res_judge.status_code, 403)

        # Organizer -> 200
        res_org = self.client.get('/organizer/normalization', **self._auth_header(self.organizer_token))
        self.assertEqual(res_org.status_code, 200)

    # -------------------------------------------------------------------------
    # Dashboard Contents and Fixture Facts Matching
    # -------------------------------------------------------------------------

    def test_dashboard_fixture_facts_exact_match(self):
        """
        Dashboard numbers match the fixture's known facts exactly:
        - jdg_07 flagged for constant score
        - prj_19 double-flagged (thin batch and constant judge)
        - prj_07 shown as duplicate and excluded
        - graph health shows 1 component of 30 judges
        - 32/41 projects meeting target reviews
        """
        response = self.client.get('/organizer', **self._auth_header(self.organizer_token))
        self.assertEqual(response.status_code, 200)

        # 1. Graph Health: 1 connected component of 30 judges
        self.assertEqual(response.context['n_components'], 1)
        self.assertEqual(response.context['total_judges'], 30)
        self.assertAlmostEqual(response.context['fiedler_value'], 0.0875, delta=0.005)
        self.assertContains(response, '1 connected component · 30/30 judges')

        # 2. Constant Judge Flag: jdg_07
        constant_judge_ids = [j['judge_external_id'] for j in response.context['constant_judges']]
        self.assertIn('jdg_07', constant_judge_ids)
        self.assertContains(response, 'jdg_07')
        self.assertContains(response, 'scored 3/3 assignments identically')

        # 3. Thin projects & prj_19 compound flag
        self.assertEqual(response.context['thin_count'], 8)
        self.assertIn('prj_19', response.context['compound_flagged_projects'])
        self.assertContains(response, '8 projects')
        self.assertContains(response, 'prj_19')

        # 4. Duplicate submission: prj_07 superseded by prj_41
        duplicate_keys = [d['project_key'] for d in response.context['duplicates']]
        self.assertIn('prj_07', duplicate_keys)
        self.assertContains(response, 'prj_07')
        self.assertContains(response, 'prj_41')
        self.assertContains(response, 'tm_07')
        self.assertContains(response, '[restore]')

        # 5. Live progress numbers: 33/41 projects have >= 3 reviews
        self.assertEqual(response.context['total_projects'], 41)
        self.assertEqual(response.context['target_met_count'], 33)
        self.assertEqual(response.context['target_k'], 3)
        self.assertContains(response, '33/41 projects have ≥3 reviews')

        # 6. Under-coverage by track (e.g. Health short by 1)
        under_covered_track_names = [t['track'].name for t in response.context['under_covered_tracks']]
        self.assertIn('Health', under_covered_track_names)
        self.assertContains(response, 'Under-coverage:')

    def test_dashboard_duplicate_restore_action(self):
        """Clicking restore on duplicate submission clears is_duplicate_of."""
        prj_07 = Project.objects.get(external_id='prj_07', event=self.event)
        self.assertIsNotNone(prj_07.is_duplicate_of_id)

        response = self.client.post('/organizer', {
            'action': 'restore_duplicate',
            'project_id': prj_07.pk,
        }, **self._auth_header(self.organizer_token))

        self.assertRedirects(response, '/organizer')

        prj_07.refresh_from_db()
        self.assertIsNone(prj_07.is_duplicate_of_id)

        # After restore, prj_07 is no longer in duplicates
        res2 = self.client.get('/organizer', **self._auth_header(self.organizer_token))
        duplicate_keys = [d['project_key'] for d in res2.context['duplicates']]
        self.assertNotIn('prj_07', duplicate_keys)

    # -------------------------------------------------------------------------
    # Organizer Assignments Page Tests
    # -------------------------------------------------------------------------

    def test_organizer_assignments_page_and_trigger_run(self):
        # Initial GET shows connectivity report
        response = self.client.get('/organizer/assignments', **self._auth_header(self.organizer_token))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['n_components'], 1)
        self.assertContains(response, 'Graph Health & Connectivity Report')

        # POST triggers an AssignmentRun
        initial_run_count = AssignmentRun.objects.filter(event=self.event).count()
        post_response = self.client.post('/organizer/assignments', {
            'target_k': 3,
            'seed': 42,
        }, **self._auth_header(self.organizer_token))
        self.assertRedirects(post_response, '/organizer/assignments')

        self.assertEqual(AssignmentRun.objects.filter(event=self.event).count(), initial_run_count + 1)

        # Subsequent GET shows latest run in history
        res_after = self.client.get('/organizer/assignments', **self._auth_header(self.organizer_token))
        self.assertContains(res_after, 'AssignmentRun History')
        self.assertIsNotNone(res_after.context['latest_run'])
        self.assertEqual(res_after.context['latest_run'].target_k, 3)

    # -------------------------------------------------------------------------
    # Organizer Normalization Page Tests
    # -------------------------------------------------------------------------

    def test_organizer_normalization_page_and_proof_table(self):
        # GET shows Normalization Proof table with raw/norm ranks and rank changes
        response = self.client.get('/organizer/normalization', **self._auth_header(self.organizer_token))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'The Normalization Proof Table')
        self.assertContains(response, 'empirical_bayes_shrinkage_v1')
        self.assertContains(response, 'Norm Rank')
        self.assertContains(response, 'Δ Rank')

        # Excluded duplicate project is marked EXCLUDED
        self.assertContains(response, 'EXCLUDED')

        # POST triggers a new NormalizationRun
        initial_norm_count = NormalizationRun.objects.filter(event=self.event).count()
        post_res = self.client.post('/organizer/normalization', {}, **self._auth_header(self.organizer_token))
        self.assertRedirects(post_res, '/organizer/normalization')
        self.assertGreaterEqual(NormalizationRun.objects.filter(event=self.event).count(), initial_norm_count + 1)

        # CSV Proof download works
        csv_res = self.client.get('/organizer/normalization?format=csv', **self._auth_header(self.organizer_token))
        self.assertEqual(csv_res.status_code, 200)
        self.assertEqual(csv_res['Content-Type'], 'text/csv; charset=utf-8')
        first_line = csv_res.content.decode('utf-8').splitlines()[0]
        self.assertIn('project_id', first_line)
        self.assertIn('normalized_rank', first_line)
        self.assertIn('rank_change', first_line)

    # -------------------------------------------------------------------------
    # Real /api/export.csv Tests
    # -------------------------------------------------------------------------

    def test_real_csv_export_denies_anonymous_and_participant(self):
        """Participant and anonymous both get denied on /api/export.csv (401/403)."""
        # Anonymous -> 401
        res_anon = self.client.get('/api/export.csv')
        self.assertEqual(res_anon.status_code, 401)

        # Participant -> 403
        res_part = self.client.get('/api/export.csv', **self._auth_header(self.participant_token))
        self.assertEqual(res_part.status_code, 403)

        # Judge -> 403
        res_judge = self.client.get('/api/export.csv', **self._auth_header(self.judge_token))
        self.assertEqual(res_judge.status_code, 403)

    def test_real_csv_export_returns_valid_per_project_data_with_flags(self):
        """Organizer export returns real CSV with raw_mean, normalized_mean, rank, review_count, flags."""
        response = self.client.get('/api/export.csv', **self._auth_header(self.organizer_token))
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])

        content = response.content.decode('utf-8')
        reader = csv.DictReader(io.StringIO(content))
        self.assertEqual(
            reader.fieldnames,
            ['project_id', 'raw_mean', 'normalized_mean', 'rank', 'review_count', 'flags'],
        )

        rows_by_id = {row['project_id']: row for row in reader}

        # 41 total projects exported
        self.assertEqual(len(rows_by_id), 41)

        # Compound case prj_19: reviewed by constant judge jdg_07 and thin review count
        row_19 = rows_by_id['prj_19']
        self.assertEqual(int(row_19['review_count']), 2)
        self.assertIn('thin_batch', row_19['flags'].split(';'))
        self.assertIn('constant_judge', row_19['flags'].split(';'))
        self.assertTrue(float(row_19['raw_mean']) > 0)
        self.assertTrue(float(row_19['normalized_mean']) > 0)
        self.assertTrue(int(row_19['rank']) > 0)

        # Duplicate prj_07: flagged duplicate, excluded from ranking (empty rank and norm mean)
        row_07 = rows_by_id['prj_07']
        self.assertIn('duplicate', row_07['flags'].split(';'))
        self.assertEqual(row_07['rank'], '')
        self.assertEqual(row_07['normalized_mean'], '')

        # Thin batch project prj_10
        row_10 = rows_by_id['prj_10']
        self.assertEqual(int(row_10['review_count']), 2)
        self.assertIn('thin_batch', row_10['flags'].split(';'))

        # CSV exports contain only canonical machine-readable flag values.
        allowed_flags = {'thin_batch', 'constant_judge', 'duplicate'}
        for row in rows_by_id.values():
            flags = set(row['flags'].split(';')) - {''}
            self.assertTrue(flags <= allowed_flags, f"Unexpected CSV flags for {row['project_id']}: {flags}")
            self.assertNotIn('thin', flags)
            self.assertNotIn('constant-judge', flags)
