"""
Tests for Phase 3 Step 3.3:
1. Demo-login switch: env RUBRIC_SEED_DEMO_LOGINS (true vs false).
2. Auth rate limiting: login and register limited per IP (10 attempts / 5 minutes)
   returning 429, DB-backed sliding window with keyed IP hash.
3. Synthetic validation sweep: services.normalization.synthetic_validation_sweep(seeds=range(100)).
"""

import hashlib
import hmac
import io
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import AuthAttempt, AuthToken, EventMembership, User
from events.models import Event
from services import accounts as accounts_service
from services import normalization as norm_services


class DemoLoginSwitchTests(TestCase):
    """
    Test the demo-login switch controlled by RUBRIC_SEED_DEMO_LOGINS.
    When true (default): seed_fixtures creates persona accounts and public demo tokens.
    When false: seed_fixtures still imports core data but creates no public demo
    tokens or persona accounts, and prints how to run create_organizer instead.
    """

    def test_demo_logins_enabled_by_default(self):
        """When RUBRIC_SEED_DEMO_LOGINS is unset or true, demo tokens are generated."""
        out = io.StringIO()
        with patch.dict('os.environ', {}, clear=True):
            call_command('seed_fixtures', stdout=out)

        output = out.getvalue()
        self.assertIn("seeded. test logins:", output)
        self.assertIn("organizer:", output)
        self.assertIn("judge_a:", output)

        # Confirm tokens and personas exist in database
        self.assertTrue(AuthToken.objects.filter(label__startswith="seed:").exists())
        self.assertTrue(User.objects.filter(email='organizer@rubric.local').exists())
        self.assertTrue(Event.objects.filter(external_id='evt_01').exists())

    def test_demo_logins_disabled_via_env(self):
        """When RUBRIC_SEED_DEMO_LOGINS is false, no public demo tokens or persona accounts are created."""
        out = io.StringIO()
        with patch.dict('os.environ', {'RUBRIC_SEED_DEMO_LOGINS': 'false'}):
            call_command('seed_fixtures', stdout=out)

        output = out.getvalue()
        # Verify instructions for creating an organizer are printed
        self.assertIn("without demo logins (RUBRIC_SEED_DEMO_LOGINS=false)", output)
        self.assertIn("create_organizer", output)
        self.assertNotIn("test logins:", output)

        # Core fixture data MUST still be imported
        self.assertTrue(Event.objects.filter(external_id='evt_01').exists())
        self.assertEqual(Event.objects.count(), 1)

        # But NO demo tokens or persona accounts are created
        self.assertFalse(AuthToken.objects.filter(label__startswith="seed:").exists())
        self.assertFalse(User.objects.filter(email='organizer@rubric.local').exists())
        self.assertFalse(User.objects.filter(email='participant@example.org').exists())


class AuthRateLimitTests(TestCase):
    """
    Test IP rate limiting on login and register:
    - 10 attempts / 5 minutes per IP returning HTTP 429.
    - Sliding window backed by AuthAttempt model.
    - Stores keyed HMAC-SHA256 of IP, never raw IP.
    """

    def setUp(self):
        self.client = Client()
        self.event = Event.objects.create(
            slug='auth-rate-test-event',
            name='Auth Rate Test Event',
            submissions_close_at=timezone.now() + timedelta(days=7),
            is_current=True,
        )

    def test_login_rate_limiting_blocks_after_10_attempts(self):
        """The 11th login attempt from the same IP within 5 minutes returns 429."""
        ip = "198.51.100.42"

        # Make 10 attempts
        for i in range(10):
            resp = self.client.post(
                '/login',
                {'email': 'nobody@example.org', 'password': f'badpw{i}'},
                REMOTE_ADDR=ip,
            )
            self.assertEqual(resp.status_code, 401)

        # 11th attempt must be rejected with 429
        resp11 = self.client.post(
            '/login',
            {'email': 'nobody@example.org', 'password': 'badpw11'},
            REMOTE_ADDR=ip,
        )
        self.assertEqual(resp11.status_code, 429)
        self.assertIn(
            "Too many authentication attempts. Please try again in 5 minutes.",
            resp11.content.decode('utf-8'),
        )

    def test_register_rate_limiting_blocks_after_10_attempts(self):
        """The 11th registration attempt from the same IP within 5 minutes returns 429."""
        ip = "198.51.100.43"

        # Make 10 invalid attempts (missing password)
        for i in range(10):
            resp = self.client.post(
                '/accounts/register',
                {'email': f'user{i}@example.org', 'password': '123'},  # too short
                REMOTE_ADDR=ip,
            )
            self.assertEqual(resp.status_code, 400)

        # 11th attempt must be rejected with 429
        resp11 = self.client.post(
            '/accounts/register',
            {'email': 'user11@example.org', 'password': 'validpassword123'},
            REMOTE_ADDR=ip,
        )
        self.assertEqual(resp11.status_code, 429)
        self.assertIn(
            "Too many authentication attempts. Please try again in 5 minutes.",
            resp11.content.decode('utf-8'),
        )

    def test_sliding_window_allows_attempts_after_expiry(self):
        """Attempts older than 5 minutes age out of the sliding window."""
        ip = "198.51.100.44"
        ip_h = accounts_service.hash_ip(ip)

        # Plant 10 attempts that occurred 6 minutes ago
        past_time = timezone.now() - timedelta(minutes=6)
        for _ in range(10):
            AuthAttempt.objects.create(
                ip_hash=ip_h,
                action='login',
                created_at=past_time,
            )

        # Because all 10 are outside the 5-minute window, a new attempt should be allowed
        resp = self.client.post(
            '/login',
            {'email': 'nobody@example.org', 'password': 'test'},
            REMOTE_ADDR=ip,
        )
        # Succeeded through rate-limiter, failed credentials -> 401 (not 429)
        self.assertEqual(resp.status_code, 401)

    def test_different_ips_have_independent_budgets(self):
        """One IP exhausting its rate limit does not affect a different IP."""
        ip_a = "198.51.100.50"
        ip_b = "198.51.100.51"

        # Exhaust IP A
        for i in range(10):
            self.client.post(
                '/login',
                {'email': 'nobody@example.org', 'password': 'pw'},
                REMOTE_ADDR=ip_a,
            )

        # IP A is blocked
        resp_a = self.client.post(
            '/login',
            {'email': 'nobody@example.org', 'password': 'pw'},
            REMOTE_ADDR=ip_a,
        )
        self.assertEqual(resp_a.status_code, 429)

        # IP B is still allowed
        resp_b = self.client.post(
            '/login',
            {'email': 'nobody@example.org', 'password': 'pw'},
            REMOTE_ADDR=ip_b,
        )
        self.assertEqual(resp_b.status_code, 401)

    def test_ip_is_stored_as_keyed_hash_not_raw_ip(self):
        """Database stores keyed HMAC-SHA256 hash of IP; raw IP never appears in DB."""
        raw_ip = "203.0.113.199"
        self.client.post(
            '/login',
            {'email': 'test@example.org', 'password': 'pw'},
            REMOTE_ADDR=raw_ip,
        )

        # Verify no record contains the raw IP
        self.assertFalse(AuthAttempt.objects.filter(ip_hash=raw_ip).exists())

        # Verify record matches the keyed HMAC hash
        expected_hash = accounts_service.hash_ip(raw_ip)
        self.assertTrue(AuthAttempt.objects.filter(ip_hash=expected_hash).exists())
        self.assertEqual(len(expected_hash), 64)


class SyntheticValidationSweepTests(TestCase):
    """
    Test services.normalization.synthetic_validation_sweep(seeds=range(100)):
    mean, median, min, max of raw and normalized Spearman, and the fraction of
    seeds where normalized beats raw.
    """

    def test_synthetic_validation_sweep_computes_accurate_metrics(self):
        """Run 100-seed synthetic sweep and verify stats."""
        sweep = norm_services.synthetic_validation_sweep(seeds=range(100))

        self.assertEqual(sweep.num_seeds, 100)
        self.assertGreater(sweep.norm_mean, sweep.raw_mean)
        self.assertGreater(sweep.norm_median, sweep.raw_median)
        self.assertGreaterEqual(sweep.win_fraction, 0.95)

        # Check dictionary and attribute access
        self.assertIsNotNone(sweep['raw_mean'])
        self.assertIsNotNone(sweep.norm_mean)
        self.assertIsNotNone(sweep['win_fraction'])

    def test_synthetic_validation_sweep_rendered_on_normalization_page(self):
        """The organizer normalization page shows the synthetic sweep beside the single seed."""
        user = User.objects.create_user(email='org_sweep@example.org', display_name='Organizer')
        event = Event.objects.create(
            slug='sweep-event',
            name='Sweep Event',
            submissions_close_at=timezone.now() + timedelta(days=7),
            is_current=True,
        )
        EventMembership.objects.create(event=event, user=user, role='ORGANIZER')
        _, raw_token = AuthToken.create_token(user=user, label='sweep-test')

        client = Client()
        client.cookies['session'] = raw_token

        url = reverse('organizer_normalization')
        resp = client.get(url)
        self.assertEqual(resp.status_code, 200)

        html = resp.content.decode('utf-8')
        # Check sweep container and synthetic labeling
        self.assertIn('synthetic-validation-sweep', html)
        self.assertIn('SYNTHETIC &middot; 100 Seeds', html)
        self.assertIn('sweep-raw-mean', html)
        self.assertIn('sweep-norm-mean', html)
        self.assertIn('sweep-win-fraction', html)
