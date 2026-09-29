import io
import math
import re
from pathlib import Path

from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from accounts.actors import Actor
from accounts.models import EventMembership, EventRole, User
from events.models import Event
from judging.models import Ballot, JudgeAssignment, NormalizationRun, Rubric, RubricCriterion
from services import normalization
from submissions.models import Project


class DocsConsistencyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_fixtures', stdout=io.StringIO())
        cls.event = Event.objects.get(external_id='evt_01')
        cls.organizer = User.objects.get(email='organizer@rubric.local')
        cls.organizer_actor = Actor(cls.organizer, cls.event)
        cls.repo_root = Path(__file__).resolve().parents[1]

    def test_judging_md_normalization_values_match_real_run(self):
        """Assert recomputed statistical parameters from a real run appear in JUDGING.md."""
        run = normalization.run(self.organizer_actor)
        judging_md_path = self.repo_root / 'JUDGING.md'
        self.assertTrue(judging_md_path.exists(), 'JUDGING.md must exist in repo root')
        content = judging_md_path.read_text(encoding='utf-8')

        pooled_mean = run.parameters['pooled_mean']
        pooled_variance = run.parameters['pooled_variance']
        pooled_stdev = math.sqrt(pooled_variance)

        pooled_mean_str = f"{pooled_mean:.4f}"
        pooled_var_str = f"{pooled_variance:.4f}"
        pooled_std_str = f"{pooled_stdev:.4f}"

        self.assertEqual(pooled_mean_str, '3.5758')
        self.assertEqual(pooled_var_str, '0.3930')
        self.assertEqual(pooled_std_str, '0.6269')

        self.assertIn(pooled_mean_str, content, f"Expected pooled mean {pooled_mean_str} in JUDGING.md")
        self.assertIn(pooled_var_str, content, f"Expected pooled variance {pooled_var_str} in JUDGING.md")
        self.assertIn(pooled_std_str, content, f"Expected pooled stdev {pooled_std_str} in JUDGING.md")

        # Constant judge jdg_07: s~^2 = 4 * 0.3930 / 7 = 0.2246
        jdg_07_stats = next(
            j for j in run.parameters['judge_statistics'] if j['judge_external_id'] == 'jdg_07'
        )
        constant_shrunk_var_str = f"{jdg_07_stats['shrunk_variance']:.4f}"
        self.assertEqual(constant_shrunk_var_str, '0.2246')
        self.assertIn(constant_shrunk_var_str, content, f"Expected constant judge variance {constant_shrunk_var_str} in JUDGING.md")

        # Constant judge jdg_07 z-score contribution is 0.5115
        jdg_07_contribs = [
            c['z_score']
            for contribs in run.parameters['contributions'].values()
            for c in contribs
            if c['judge_external_id'] == 'jdg_07'
        ]
        self.assertTrue(len(jdg_07_contribs) > 0)
        constant_z_str = f"{jdg_07_contribs[0]:.4f}"
        self.assertEqual(constant_z_str, '0.5115')
        self.assertIn(constant_z_str, content, f"Expected constant judge z-score {constant_z_str} in JUDGING.md")

        # Real fixture evidence: stdev of raw judge means (0.3235) and norm ballot means (0.2023)
        evidence = normalization.compute_judge_calibration_evidence(run)
        raw_stdev_str = f"{evidence['raw_mean_stdev']:.4f}"
        norm_stdev_str = f"{evidence['norm_mean_stdev']:.4f}"
        self.assertEqual(raw_stdev_str, '0.3235')
        self.assertEqual(norm_stdev_str, '0.2023')
        self.assertIn(raw_stdev_str, content, f"Expected raw judge means stdev {raw_stdev_str} in JUDGING.md")
        self.assertIn(norm_stdev_str, content, f"Expected normalized ballot means stdev {norm_stdev_str} in JUDGING.md")

        # Synthetic ground truth evidence (seed 2026: 0.7308 and 0.8917)
        syn = normalization.synthetic_validation(2026)
        syn_raw_str = f"{syn.raw_spearman:.4f}"
        syn_norm_str = f"{syn.normalized_spearman:.4f}"
        self.assertEqual(syn_raw_str, '0.7308')
        self.assertEqual(syn_norm_str, '0.8917')
        self.assertIn(syn_raw_str, content, f"Expected synthetic raw spearman {syn_raw_str} in JUDGING.md")
        self.assertIn(syn_norm_str, content, f"Expected synthetic norm spearman {syn_norm_str} in JUDGING.md")

    def test_decisions_md_table_of_contents_completeness(self):
        """Assert every '## N.' heading in DECISIONS.md has a table-of-contents entry."""
        decisions_md_path = self.repo_root / 'DECISIONS.md'
        self.assertTrue(decisions_md_path.exists(), 'DECISIONS.md must exist in repo root')
        content = decisions_md_path.read_text(encoding='utf-8')

        # Find Table of Contents block
        toc_match = re.search(r'## Table of Contents\s*\n(.*?)(?=\n---\s*\n|\n## \d+\.)', content, re.DOTALL)
        self.assertIsNotNone(toc_match, 'DECISIONS.md must have a Table of Contents section')
        toc_text = toc_match.group(1)

        # Extract all numbered headings in the body
        headings = re.findall(r'^## (\d+)\.\s*(.+)$', content, re.MULTILINE)
        self.assertTrue(len(headings) > 0, 'DECISIONS.md must have numbered decision headings')

        for num_str, title in headings:
            num = int(num_str)
            # TOC line should contain "[N. "
            expected_toc_prefix = f'[{num}.'
            self.assertIn(
                expected_toc_prefix,
                toc_text,
                f"DECISIONS.md TOC is missing an entry for '## {num}. {title}'"
            )


class BallotAnchorsAndValidationTests(TestCase):
    SEED_JUDGE_A = 'rubric_seed_judge_a_tok_1a2b3c4d5e6f'
    SEED_ORGANIZER = 'rubric_seed_organizer_tok_9f8e7d6c5b4a'

    @classmethod
    def setUpTestData(cls):
        call_command('seed_fixtures', stdout=io.StringIO())
        cls.event = Event.objects.get(external_id='evt_01')
        cls.judge_user = User.objects.get(external_id='jdg_07')

    def test_custom_or_renamed_criterion_ballot_anchors_degrade_gracefully(self):
        """Confirm organizer-added or renamed criteria degrade gracefully (no anchor text, no crash)."""
        rubric = self.event.rubrics.first()
        self.assertIsNotNone(rubric)

        # Add a custom criterion with an unmapped name
        custom_crit = RubricCriterion.objects.create(
            rubric=rubric,
            name='Sustainability Impact',
            weight=2,
            max_score=5,
            order=99,
        )

        # Find an assignment for judge_a
        assignment = JudgeAssignment.objects.filter(event=self.event, judge=self.judge_user).first()
        self.assertIsNotNone(assignment)

        client = Client()
        client.cookies['session'] = self.SEED_JUDGE_A

        url = reverse('judge_ballot', kwargs={'assignment_id': assignment.pk})
        response = client.get(url)
        self.assertEqual(response.status_code, 200, 'Ballot page must not crash on custom criterion')

        # Check context criteria_data
        criteria_data = response.context['criteria_data']
        custom_item = next(
            (item for item in criteria_data if item['criterion'].id == custom_crit.id),
            None
        )
        self.assertIsNotNone(custom_item, 'Custom criterion must be present in criteria_data')

        # Assert no anchor text for custom criterion options
        for opt in custom_item['options']:
            self.assertEqual(opt['anchor'], '', 'Custom criterion options must have empty anchor text')

        # Assert standard criterion still has anchor text
        func_item = next(
            (item for item in criteria_data if item['criterion'].name.lower() == 'functionality'),
            None
        )
        if func_item:
            first_opt = func_item['options'][0]
            self.assertNotEqual(first_opt['anchor'], '', 'Standard criterion must retain anchor text')

        # Assert rendered HTML contains custom criterion name without error
        html = response.content.decode('utf-8')
        self.assertIn('Sustainability Impact', html)
        self.assertIn(f'score_{custom_crit.id}', html)

    def test_synthetic_validation_api_and_reproducibility(self):
        """Test services.normalization.synthetic_validation(seed)."""
        res = normalization.synthetic_validation(2026)
        self.assertGreater(res.normalized_spearman, res.raw_spearman)
        self.assertAlmostEqual(res.raw_spearman, 0.7308, places=3)
        self.assertAlmostEqual(res.normalized_spearman, 0.8917, places=3)

        # Verify tuple unpacking
        raw_corr, norm_corr = res
        self.assertEqual(raw_corr, res.raw_spearman)
        self.assertEqual(norm_corr, res.normalized_spearman)

        # Verify dict access
        self.assertEqual(res['raw_spearman'], res.raw_spearman)
        self.assertEqual(res['normalized_spearman'], res.normalized_spearman)
        self.assertEqual(res['seed'], 2026)

        # Verify different seeds run deterministically
        res_other = normalization.synthetic_validation(42)
        self.assertIsInstance(res_other.raw_spearman, float)
        self.assertIsInstance(res_other.normalized_spearman, float)

    def test_real_fixture_calibration_evidence_and_organizer_page(self):
        """Test calibration evidence computation and display on /organizer/normalization."""
        client = Client()
        client.cookies['session'] = self.SEED_ORGANIZER

        response = client.get('/organizer/normalization')
        self.assertEqual(response.status_code, 200)

        # Context has evidence
        self.assertIn('calibration_evidence', response.context)
        self.assertIn('synthetic_evidence', response.context)

        evidence = response.context['calibration_evidence']
        self.assertEqual(evidence['judge_count'], 29)
        self.assertEqual(evidence['ballot_count'], 121)
        self.assertAlmostEqual(evidence['raw_mean_stdev'], 0.3235, places=3)
        self.assertAlmostEqual(evidence['norm_mean_stdev'], 0.2023, places=3)
        self.assertGreater(evidence['stdev_reduction'], 0.1)

        # HTML contains both evidence sections, real first and synthetic clearly labeled
        html = response.content.decode('utf-8')
        real_idx = html.find('real-fixture-evidence')
        syn_idx = html.find('synthetic-validation-evidence')
        self.assertNotEqual(real_idx, -1, 'Page must contain real fixture evidence')
        self.assertNotEqual(syn_idx, -1, 'Page must contain synthetic validation evidence')
        self.assertLess(real_idx, syn_idx, 'Real fixture evidence must appear before synthetic evidence')
        self.assertIn('SYNTHETIC', html, 'Synthetic validation must be clearly labelled SYNTHETIC')
        self.assertIn('0.3235', html)
        self.assertIn('0.2023', html)
        self.assertIn('0.7308', html)
        self.assertIn('0.8917', html)
