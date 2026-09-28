"""
Tests for G5 Step 3:
1. Real user accounts: registration, login, logout, session cookie flags,
   timing/enumeration protection, CSRF enforcement on cookie auth.
2. Organizer-configurable weighted rubric:
   - Organizer-only authorization.
   - Validation: at least one criterion, finite positive weights, positive max_score.
   - Post-scoring edit policy: scored criteria cannot be deleted.
   - Weight adjustments are permitted and audit-logged with before/after values.
   - Re-running normalization measurably and deterministically updates scores on the real fixture.
   - /organizer/rubric UI view with normalization notice.
3. Definition of done:
   - A brand-new registered user can register, log in, and reach a page requiring a session.
"""

import io
import re
from decimal import Decimal

from django.conf import settings
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from accounts.actors import Actor, AnonymousActor, PermissionDenied
from accounts.models import AuthToken, EventMembership, EventRole, User
from audit.models import AuditLogEntry
from events.models import Event
from importer.management.commands.seed_fixtures import SEED_TOKENS
from judging.models import BallotScore, Rubric, RubricCriterion
from services import accounts as accounts_service
from services import judging as judging_services
from services.normalization import run as normalization_run


class G5Step3RubricConfigurationTests(TestCase):
    """
    Tests for services.judging.configure_rubric, rubric editing policy after scoring,
    and deterministic impact on normalization output.
    """

    @classmethod
    def setUpTestData(cls):
        call_command('seed_fixtures', stdout=io.StringIO())
        cls.event = Event.objects.get(external_id='evt_01')
        cls.organizer = User.objects.get(email='organizer@rubric.local')
        # Participant user from seeded persona token
        cls.participant = AuthToken.objects.get(
            token_hash=AuthToken.hash_token(SEED_TOKENS['participant'])
        ).user
        cls.judge = User.objects.get(external_id='jdg_07')

        cls.organizer_actor = Actor(cls.organizer, cls.event)
        cls.participant_actor = Actor(cls.participant, cls.event)
        cls.judge_actor = Actor(cls.judge, cls.event)
        cls.anon_actor = AnonymousActor()

    def test_configure_rubric_organizer_only(self):
        """Only organizers can configure rubric; others get PermissionDenied."""
        criteria = [{'name': 'criterion_a', 'weight': 1.0, 'max_score': 5.0}]

        with self.assertRaises(PermissionDenied):
            judging_services.configure_rubric(self.anon_actor, criteria)

        with self.assertRaises(PermissionDenied):
            judging_services.configure_rubric(self.participant_actor, criteria)

        with self.assertRaises(PermissionDenied):
            judging_services.configure_rubric(self.judge_actor, criteria)

    def test_configure_rubric_validations(self):
        """Validates: at least one criterion, finite positive weights, positive max_score."""
        # Empty criteria
        with self.assertRaises(ValueError) as ctx:
            judging_services.configure_rubric(self.organizer_actor, [])
        self.assertIn("At least one criterion is required", str(ctx.exception))

        # Empty criterion name
        with self.assertRaises(ValueError) as ctx:
            judging_services.configure_rubric(self.organizer_actor, [{'name': '', 'weight': 1.0, 'max_score': 5.0}])
        self.assertIn("name cannot be empty", str(ctx.exception))

        # Duplicate criterion names
        with self.assertRaises(ValueError) as ctx:
            judging_services.configure_rubric(self.organizer_actor, [
                {'name': 'design', 'weight': 1.0, 'max_score': 5.0},
                {'name': 'design', 'weight': 2.0, 'max_score': 5.0},
            ])
        self.assertIn("Duplicate criterion name", str(ctx.exception))

        # Zero or negative weight
        for bad_weight in [0, -1, -0.5, '0', '-2.5']:
            with self.assertRaises(ValueError) as ctx:
                judging_services.configure_rubric(self.organizer_actor, [
                    {'name': 'innovation', 'weight': bad_weight, 'max_score': 5.0},
                ])
            self.assertIn("must be a finite positive number", str(ctx.exception))

        # Non-finite weight
        for bad_weight in ['nan', 'inf', '-inf', 'abc']:
            with self.assertRaises(ValueError) as ctx:
                judging_services.configure_rubric(self.organizer_actor, [
                    {'name': 'innovation', 'weight': bad_weight, 'max_score': 5.0},
                ])
            self.assertIn("must be a finite positive number", str(ctx.exception))

        # Zero or negative max score
        for bad_max in [0, -5, '0', '-1.0', 'nan', 'inf']:
            with self.assertRaises(ValueError) as ctx:
                judging_services.configure_rubric(self.organizer_actor, [
                    {'name': 'innovation', 'weight': 1.0, 'max_score': bad_max},
                ])
            self.assertIn("must be a positive number", str(ctx.exception))

    def test_deleting_scored_criterion_is_rejected(self):
        """Criteria with existing BallotScore rows cannot be deleted."""
        rubric = judging_services.get_rubric(self.organizer_actor)
        existing_criteria = list(rubric.criteria.all())
        self.assertGreater(len(existing_criteria), 0)

        # Confirm that at least one criterion has existing BallotScore rows
        scored_criterion = None
        for c in existing_criteria:
            if BallotScore.objects.filter(criterion=c).exists():
                scored_criterion = c
                break
        self.assertIsNotNone(scored_criterion, "Expected at least one scored criterion in seeded fixture")

        # Attempt to configure rubric omitting the scored criterion
        surviving_criteria = [
            {'name': c.name, 'weight': float(c.weight), 'max_score': float(c.max_score)}
            for c in existing_criteria if c.name != scored_criterion.name
        ]

        with self.assertRaises(ValueError) as ctx:
            judging_services.configure_rubric(self.organizer_actor, surviving_criteria)
        self.assertIn(f"Cannot delete criterion '{scored_criterion.name}'", str(ctx.exception))
        self.assertIn("ballots have already been scored against it", str(ctx.exception))

        # Verify criterion still exists in DB
        self.assertTrue(RubricCriterion.objects.filter(pk=scored_criterion.pk).exists())

    def test_weight_changes_audit_logged_with_before_after(self):
        """Weight changes are permitted and audit-logged with before/after values."""
        rubric = judging_services.get_rubric(self.organizer_actor)
        existing_criteria = list(rubric.criteria.order_by('order', 'id'))

        modified_criteria = []
        target_criterion = existing_criteria[0]
        old_weight = float(target_criterion.weight)
        new_weight = old_weight + 2.5

        for c in existing_criteria:
            w = new_weight if c.name == target_criterion.name else float(c.weight)
            modified_criteria.append({
                'name': c.name,
                'weight': w,
                'max_score': float(c.max_score),
                'order': c.order,
            })

        initial_audit_count = AuditLogEntry.objects.count()

        judging_services.configure_rubric(self.organizer_actor, modified_criteria)

        self.assertEqual(AuditLogEntry.objects.count(), initial_audit_count + 1)
        entry = AuditLogEntry.objects.order_by('-seq').first()
        self.assertEqual(entry.action, 'rubric.configure')
        self.assertEqual(entry.actor_user_id, self.organizer.pk)

        # Verify payload contains before and after values
        payload = entry.payload
        self.assertIn('weight_changes', payload)
        target_changes = [ch for ch in payload['weight_changes'] if ch['name'] == target_criterion.name]
        self.assertEqual(len(target_changes), 1)
        self.assertEqual(target_changes[0]['before'], old_weight)
        self.assertEqual(target_changes[0]['after'], new_weight)

    def test_weight_changes_measurably_and_deterministically_change_normalized_output(self):
        """
        Changing weights measurably and deterministically changes normalized output
        on the real fixture.
        """
        # 1. Run baseline normalization
        run_baseline = normalization_run(self.organizer_actor)
        baseline_scores = {
            s.project.external_id or str(s.project.pk): float(s.normalized_mean)
            for s in run_baseline.scores.filter(normalized_mean__isnull=False)
        }
        self.assertGreater(len(baseline_scores), 0)

        # 2. Change weights heavily skewing one criterion
        rubric = judging_services.get_rubric(self.organizer_actor)
        criteria = list(rubric.criteria.all())
        # Set first criterion to weight 100.0, others to 0.01
        heavily_weighted = []
        for idx, c in enumerate(criteria):
            w = 100.0 if idx == 0 else 0.01
            heavily_weighted.append({
                'name': c.name,
                'weight': w,
                'max_score': float(c.max_score),
            })

        judging_services.configure_rubric(self.organizer_actor, heavily_weighted)

        # 3. Re-run normalization with new weights
        run_modified = normalization_run(self.organizer_actor)
        modified_scores = {
            s.project.external_id or str(s.project.pk): float(s.normalized_mean)
            for s in run_modified.scores.filter(normalized_mean__isnull=False)
        }

        # Measurable difference: at least one project's normalized score has changed
        differences = [
            abs(modified_scores[k] - baseline_scores[k])
            for k in baseline_scores if k in modified_scores
        ]
        max_diff = max(differences) if differences else 0.0
        self.assertGreater(max_diff, 1e-4, "Expected measurable change in normalized score after weight change")

        # 4. Re-run normalization again with same weights: must be deterministically identical
        run_modified_2 = normalization_run(self.organizer_actor)
        modified_2_scores = {
            s.project.external_id or str(s.project.pk): float(s.normalized_mean)
            for s in run_modified_2.scores.filter(normalized_mean__isnull=False)
        }
        for k in modified_scores:
            self.assertEqual(
                modified_scores[k],
                modified_2_scores[k],
                f"Normalization run with identical weights must be byte-identical deterministic for {k}",
            )

    def test_organizer_rubric_view_authz_and_rendering(self):
        """GET and POST /organizer/rubric enforces organizer-only and renders notice."""
        org_token = SEED_TOKENS['organizer']
        part_token = SEED_TOKENS['participant']
        judge_token = SEED_TOKENS['judge_a']

        url = '/organizer/rubric'

        # Anon -> 401
        self.assertEqual(self.client.get(url).status_code, 401)

        # Participant -> 403
        self.assertEqual(self.client.get(url, HTTP_AUTHORIZATION=f'Bearer {part_token}').status_code, 403)

        # Judge -> 403
        self.assertEqual(self.client.get(url, HTTP_AUTHORIZATION=f'Bearer {judge_token}').status_code, 403)

        # Organizer -> 200
        res = self.client.get(url, HTTP_AUTHORIZATION=f'Bearer {org_token}')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Weighted Scoring Rubric')
        self.assertContains(res, 'Normalization Notice')
        self.assertContains(res, 're-run Normalization')


class G5Step3UserAccountsTests(TestCase):
    """
    Tests for real user accounts:
    - Register/login/logout round-trip.
    - Password hashing via Django's hasher.
    - Session cookie flags (HttpOnly, SameSite=Lax, Secure when DEBUG is off).
    - Indistinguishable failure responses for unknown email vs wrong password.
    - CSRF enforcement on cookie authentication.
    - Definition of done: new user registers, logs in, reaches protected session page.
    """

    @classmethod
    def setUpTestData(cls):
        call_command('seed_fixtures', stdout=io.StringIO())
        cls.event = Event.objects.get(external_id='evt_01')

    def test_register_login_logout_roundtrip_service(self):
        """Services roundtrip: register -> login -> logout with audit logs."""
        email = "cadet@example.com"
        password = "ValidPassword123!"

        # 1. Register
        initial_audit_count = AuditLogEntry.objects.count()
        user, raw_token = accounts_service.register(
            email=email,
            password=password,
            display_name="Space Cadet",
        )
        self.assertEqual(user.email, email)
        self.assertTrue(user.check_password(password))
        self.assertEqual(user.display_name, "Space Cadet")

        # Verify audit log for register (must not log raw password or token)
        self.assertEqual(AuditLogEntry.objects.count(), initial_audit_count + 1)
        reg_entry = AuditLogEntry.objects.order_by('-seq').first()
        self.assertEqual(reg_entry.action, 'user.register')
        self.assertNotIn(password, str(reg_entry.payload))
        self.assertNotIn(raw_token, str(reg_entry.payload))

        # 2. Login
        logged_user, new_raw_token = accounts_service.login(email=email, password=password)
        self.assertEqual(logged_user.pk, user.pk)
        token_hash = AuthToken.hash_token(new_raw_token)
        self.assertTrue(AuthToken.objects.filter(token_hash=token_hash).exists())

        # Verify audit log for login
        self.assertEqual(AuditLogEntry.objects.count(), initial_audit_count + 2)
        login_entry = AuditLogEntry.objects.order_by('-seq').first()
        self.assertEqual(login_entry.action, 'user.login')
        self.assertNotIn(password, str(login_entry.payload))
        self.assertNotIn(new_raw_token, str(login_entry.payload))

        # 3. Logout invalidates token server-side
        success = accounts_service.logout(new_raw_token)
        self.assertTrue(success)
        self.assertFalse(AuthToken.objects.filter(token_hash=token_hash).exists())

    def test_unknown_email_and_wrong_password_indistinguishable(self):
        """
        Login failure must not reveal whether an email exists.
        Both unknown-email and wrong-password return 401 with generic error message.
        """
        test_email = "known_user@example.org"
        password = "SuperSecretPassword123!"
        accounts_service.register(email=test_email, password=password, display_name="Known")

        # 1. Wrong password on known email
        res_wrong_pw = self.client.post('/login', {
            'email': test_email,
            'password': 'completely_wrong_password',
        })

        # 2. Unknown email
        res_unknown_email = self.client.post('/login', {
            'email': 'ghost_user_does_not_exist@example.org',
            'password': 'any_password',
        })

        self.assertEqual(res_wrong_pw.status_code, 401)
        self.assertEqual(res_unknown_email.status_code, 401)
        self.assertContains(res_wrong_pw, accounts_service.GENERIC_LOGIN_ERROR, status_code=401)
        self.assertContains(res_unknown_email, accounts_service.GENERIC_LOGIN_ERROR, status_code=401)

        # Neither response leaks user existence info
        self.assertNotIn("user not found", res_unknown_email.content.decode().lower())
        self.assertNotIn("no such user", res_unknown_email.content.decode().lower())
        self.assertNotIn("incorrect password", res_wrong_pw.content.decode().lower())

        # When evaluated for the same email address, the rendered templates are identical (modulo masked CSRF token)
        res_same_email = self.client.post('/login', {
            'email': test_email,
            'password': 'different_wrong_password',
        })
        def normalize_csrf(raw_html):
            return re.sub(rb'name="csrfmiddlewaretoken" value="[^"]+"', rb'name="csrfmiddlewaretoken" value="CSRF_MASKED"', raw_html)

        self.assertEqual(normalize_csrf(res_wrong_pw.content), normalize_csrf(res_same_email.content))

    @override_settings(DEBUG=False)
    def test_session_cookie_flags_debug_false(self):
        """When DEBUG=False, session cookie has HttpOnly, SameSite=Lax, and Secure=True."""
        email = "securecookie@example.org"
        password = "Password123!"

        res = self.client.post('/accounts/register', {
            'email': email,
            'password': password,
            'display_name': 'Secure User',
        })
        self.assertEqual(res.status_code, 302)
        self.assertIn('session', res.cookies)
        cookie = res.cookies['session']
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['samesite'].lower(), 'lax')
        self.assertTrue(cookie['secure'])

        # Same for login
        res_login = self.client.post('/login', {
            'email': email,
            'password': password,
        })
        self.assertEqual(res_login.status_code, 302)
        login_cookie = res_login.cookies['session']
        self.assertTrue(login_cookie['httponly'])
        self.assertEqual(login_cookie['samesite'].lower(), 'lax')
        self.assertTrue(login_cookie['secure'])

    @override_settings(DEBUG=True)
    def test_session_cookie_flags_debug_true(self):
        """When DEBUG=True, Secure flag is False to facilitate local development."""
        res = self.client.post('/accounts/register', {
            'email': 'debugcookie@example.org',
            'password': 'Password123!',
        })
        self.assertEqual(res.status_code, 302)
        cookie = res.cookies['session']
        self.assertTrue(cookie['httponly'])
        self.assertEqual(cookie['samesite'].lower(), 'lax')
        self.assertFalse(cookie['secure'])

    def test_cookie_authenticated_post_without_csrf_is_rejected(self):
        """
        CSRF stays fully enforced on cookie-authenticated requests.
        A cookie-authenticated POST without a CSRF token must be rejected (403).
        """
        # Create user and get a session token
        user, raw_token = accounts_service.register(
            email="csrftester@example.org",
            password="Password123!",
            display_name="CSRF Tester",
        )

        csrf_client = Client(enforce_csrf_checks=True)
        # Authenticate via cookie
        csrf_client.cookies['session'] = raw_token

        # POST without CSRF token must return 403 Forbidden
        response = csrf_client.post('/logout')
        self.assertEqual(
            response.status_code,
            403,
            "Cookie-authenticated POST without CSRF token must be rejected with 403",
        )

        # GET to acquire valid CSRF token in the client
        get_res = csrf_client.get('/login')
        csrf_token = csrf_client.cookies['csrftoken'].value

        # POST with CSRF token is processed and succeeds with redirect
        post_res = csrf_client.post('/logout', {
            'csrfmiddlewaretoken': csrf_token,
        })
        self.assertEqual(post_res.status_code, 302)

    def test_definition_of_done_new_user_reaches_protected_page(self):
        """
        Definition of Done:
        A brand-new registered user can register, log in, and reach a page requiring a session.
        """
        email = "brandnew@example.com"
        password = "VerySecretPassword123!"
        display_name = "Brand New Explorer"

        client = Client()

        # Step 0: Anonymous user cannot access /my/submissions
        anon_res = client.get('/my/submissions')
        self.assertEqual(anon_res.status_code, 401)

        # Step 1: Register through HTTP form
        reg_res = client.post('/accounts/register', {
            'email': email,
            'password': password,
            'display_name': display_name,
        })
        self.assertEqual(reg_res.status_code, 302)
        self.assertIn('session', client.cookies)

        # Step 2: Log out
        logout_res = client.post('/logout')
        self.assertEqual(logout_res.status_code, 302)

        # Confirm session is terminated
        after_logout_res = client.get('/my/submissions')
        self.assertEqual(after_logout_res.status_code, 401)

        # Step 3: Log back in through /login
        login_res = client.post('/login', {
            'email': email,
            'password': password,
            'next': '/my/submissions',
        })
        self.assertEqual(login_res.status_code, 302)
        self.assertIn('session', client.cookies)

        # Step 4: Reach protected page requiring session
        protected_res = client.get('/my/submissions')
        self.assertEqual(protected_res.status_code, 200)
        self.assertContains(protected_res, 'My Submissions')
        self.assertContains(protected_res, display_name)
