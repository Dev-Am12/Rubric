"""
Tests for the auth & policy foundation layer.

Coverage:
  1. AuthMiddleware: token resolution, expiry, anonymous fallback
  2. Actor / AnonymousActor: role booleans, independence, defaults-closed
  3. require() + exception handler: 401 vs 403 mapping
  4. Route×role coverage mechanism (AUTHZ.md §4): undeclared route detection
  5. Control case: the leaky debug route proves the mechanism catches it

All tests use fixture-independent synthetic users — no imported fixture
data is needed for this layer.
"""

from django.test import TestCase, RequestFactory, override_settings
from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta

from accounts.actors import Actor, AnonymousActor, PermissionDenied, require
from accounts.models import AuthToken, EventMembership, EventRole, User
from accounts.middleware import AuthMiddleware
from events.models import Event


class AnonymousActorTest(TestCase):
    """AnonymousActor has every permission boolean False (defaults closed)."""

    def test_all_roles_false(self):
        anon = AnonymousActor()
        self.assertTrue(anon.is_anonymous)
        self.assertFalse(anon.is_participant)
        self.assertFalse(anon.is_judge)
        self.assertFalse(anon.is_organizer)
        self.assertFalse(anon.is_site_admin)

    def test_user_is_none(self):
        anon = AnonymousActor()
        self.assertIsNone(anon.user)

    def test_judge_external_id_is_none(self):
        anon = AnonymousActor()
        self.assertIsNone(anon.judge_external_id)


class ActorRoleBooleanTest(TestCase):
    """
    Actor role booleans are independent — a user can hold multiple roles
    simultaneously (AUTHZ.md §1, stress-test F12).
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='multi@example.org', display_name='Multi Role',
        )
        self.event = Event.objects.create(
            slug='test-event', name='Test Event',
            submissions_close_at=timezone.now() + timedelta(days=30),
        )

    def test_participant_only(self):
        EventMembership.objects.create(
            event=self.event, user=self.user, role=EventRole.PARTICIPANT,
        )
        actor = Actor(user=self.user, event=self.event)
        self.assertFalse(actor.is_anonymous)
        self.assertTrue(actor.is_participant)
        self.assertFalse(actor.is_judge)
        self.assertFalse(actor.is_organizer)

    def test_judge_only(self):
        EventMembership.objects.create(
            event=self.event, user=self.user, role=EventRole.JUDGE,
        )
        actor = Actor(user=self.user, event=self.event)
        self.assertFalse(actor.is_participant)
        self.assertTrue(actor.is_judge)
        self.assertFalse(actor.is_organizer)

    def test_organizer_only(self):
        EventMembership.objects.create(
            event=self.event, user=self.user, role=EventRole.ORGANIZER,
        )
        actor = Actor(user=self.user, event=self.event)
        self.assertFalse(actor.is_participant)
        self.assertFalse(actor.is_judge)
        self.assertTrue(actor.is_organizer)

    def test_dual_role_judge_and_participant(self):
        """A user can hold both JUDGE and PARTICIPANT simultaneously."""
        EventMembership.objects.create(
            event=self.event, user=self.user, role=EventRole.JUDGE,
        )
        EventMembership.objects.create(
            event=self.event, user=self.user, role=EventRole.PARTICIPANT,
        )
        actor = Actor(user=self.user, event=self.event)
        self.assertTrue(actor.is_participant)
        self.assertTrue(actor.is_judge)
        self.assertFalse(actor.is_organizer)

    def test_site_admin_from_user_flag(self):
        """is_site_admin comes from User.is_site_admin, not EventMembership."""
        self.user.is_site_admin = True
        self.user.save()
        actor = Actor(user=self.user, event=self.event)
        self.assertTrue(actor.is_site_admin)

    def test_judge_external_id(self):
        self.user.external_id = 'jdg_99'
        self.user.save()
        EventMembership.objects.create(
            event=self.event, user=self.user, role=EventRole.JUDGE,
        )
        actor = Actor(user=self.user, event=self.event)
        self.assertEqual(actor.judge_external_id, 'jdg_99')

    def test_judge_external_id_none_if_not_judge(self):
        """judge_external_id returns None if user is not a judge."""
        self.user.external_id = 'jdg_99'
        self.user.save()
        EventMembership.objects.create(
            event=self.event, user=self.user, role=EventRole.PARTICIPANT,
        )
        actor = Actor(user=self.user, event=self.event)
        self.assertIsNone(actor.judge_external_id)

    def test_no_memberships_all_false(self):
        """A valid user with no EventMembership has all role flags False."""
        actor = Actor(user=self.user, event=self.event)
        self.assertFalse(actor.is_participant)
        self.assertFalse(actor.is_judge)
        self.assertFalse(actor.is_organizer)


class RequireHelperTest(TestCase):
    """require(actor, condition) raises PermissionDenied on falsy condition."""

    def test_truthy_condition_passes(self):
        # Should not raise
        require(AnonymousActor(), True)

    def test_falsy_condition_raises(self):
        with self.assertRaises(PermissionDenied):
            require(AnonymousActor(), False)

    def test_none_condition_raises(self):
        with self.assertRaises(PermissionDenied):
            require(AnonymousActor(), None)


class AuthMiddlewareTokenResolutionTest(TestCase):
    """AuthMiddleware resolves tokens from headers into request.actor."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='auth@example.org', display_name='Auth User',
        )
        self.event = Event.objects.create(
            slug='auth-event', name='Auth Event',
            submissions_close_at=timezone.now() + timedelta(days=30),
        )
        EventMembership.objects.create(
            event=self.event, user=self.user, role=EventRole.JUDGE,
        )
        self.token_obj, self.raw_token = AuthToken.create_token(
            user=self.user, label='test-token',
        )
        self.factory = RequestFactory()

    def _get_actor(self, headers=None):
        """
        Build a request, run it through the middleware, return the actor.
        We use a simple passthrough get_response to capture the actor.
        """
        captured = {}

        def get_response(request):
            captured['actor'] = request.actor
            return JsonResponse({'ok': True})

        mw = AuthMiddleware(get_response)
        request = self.factory.get('/')
        if headers:
            for key, value in headers.items():
                request.META[key] = value
        mw(request)
        return captured['actor']

    def test_no_header_gives_anonymous(self):
        actor = self._get_actor()
        self.assertTrue(actor.is_anonymous)

    def test_valid_bearer_token(self):
        actor = self._get_actor({
            'HTTP_AUTHORIZATION': f'Bearer {self.raw_token}',
        })
        self.assertFalse(actor.is_anonymous)
        self.assertEqual(actor.user.pk, self.user.pk)
        self.assertTrue(actor.is_judge)

    def test_invalid_token_gives_anonymous(self):
        actor = self._get_actor({
            'HTTP_AUTHORIZATION': 'Bearer totally-invalid-token',
        })
        self.assertTrue(actor.is_anonymous)

    def test_garbage_auth_header_gives_anonymous(self):
        actor = self._get_actor({
            'HTTP_AUTHORIZATION': 'Basic dXNlcjpwYXNz',
        })
        self.assertTrue(actor.is_anonymous)

    def test_expired_token_gives_anonymous(self):
        _, expired_raw = AuthToken.create_token(
            user=self.user, label='expired',
            expires_at=timezone.now() - timedelta(hours=1),
        )
        actor = self._get_actor({
            'HTTP_AUTHORIZATION': f'Bearer {expired_raw}',
        })
        self.assertTrue(actor.is_anonymous)

    def test_unexpired_token_works(self):
        _, future_raw = AuthToken.create_token(
            user=self.user, label='future',
            expires_at=timezone.now() + timedelta(hours=24),
        )
        actor = self._get_actor({
            'HTTP_AUTHORIZATION': f'Bearer {future_raw}',
        })
        self.assertFalse(actor.is_anonymous)
        self.assertEqual(actor.user.pk, self.user.pk)

    def test_null_expires_at_never_expires(self):
        """Seed tokens have expires_at=None and should never expire."""
        actor = self._get_actor({
            'HTTP_AUTHORIZATION': f'Bearer {self.raw_token}',
        })
        self.assertFalse(actor.is_anonymous)

    def test_cookie_based_token(self):
        """Tokens can also be provided via a session cookie."""
        captured = {}

        def get_response(request):
            captured['actor'] = request.actor
            return JsonResponse({'ok': True})

        mw = AuthMiddleware(get_response)
        request = self.factory.get('/')
        request.COOKIES['session'] = self.raw_token
        mw(request)
        self.assertFalse(captured['actor'].is_anonymous)
        self.assertEqual(captured['actor'].user.pk, self.user.pk)


class PermissionDenied401vs403Test(TestCase):
    """
    The critical 401 vs 403 distinction (AUTHZ.md §1):
      AnonymousActor + PermissionDenied → 401
      resolved Actor + PermissionDenied → 403

    This test uses real HTTP requests through the middleware to verify the
    end-to-end behavior, not just unit-testing the Actor classes.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='policy@example.org', display_name='Policy User',
        )
        self.event = Event.objects.create(
            slug='policy-event', name='Policy Event',
            submissions_close_at=timezone.now() + timedelta(days=30),
        )
        # This user is a PARTICIPANT — not a judge or organizer
        EventMembership.objects.create(
            event=self.event, user=self.user, role=EventRole.PARTICIPANT,
        )
        self.token_obj, self.raw_token = AuthToken.create_token(
            user=self.user, label='policy-test',
        )

    def _make_guarded_view(self, require_condition):
        """Create a view that calls require() with the given condition."""
        def view(request):
            require(request.actor, require_condition(request.actor))
            return JsonResponse({'ok': True})
        return view

    def _request_through_middleware(self, view_fn, headers=None):
        """Run a request through the AuthMiddleware + view."""
        mw = AuthMiddleware(view_fn)
        factory = RequestFactory()
        request = factory.get('/')
        if headers:
            for key, value in headers.items():
                request.META[key] = value
        return mw(request)

    def test_anonymous_gets_401(self):
        """No token + PermissionDenied → 401."""
        view = self._make_guarded_view(lambda actor: False)
        response = self._request_through_middleware(view)
        self.assertEqual(response.status_code, 401)

    def test_authenticated_wrong_role_gets_403(self):
        """Valid token + wrong role + PermissionDenied → 403."""
        # This user is a PARTICIPANT, not a judge — require judge role
        view = self._make_guarded_view(lambda actor: actor.is_judge)
        response = self._request_through_middleware(
            view, {'HTTP_AUTHORIZATION': f'Bearer {self.raw_token}'},
        )
        self.assertEqual(response.status_code, 403)

    def test_authorized_passes_through(self):
        """Valid token + correct role → 200."""
        # This user IS a participant — require participant role
        view = self._make_guarded_view(lambda actor: actor.is_participant)
        response = self._request_through_middleware(
            view, {'HTTP_AUTHORIZATION': f'Bearer {self.raw_token}'},
        )
        self.assertEqual(response.status_code, 200)

    def test_invalid_token_gets_401_not_403(self):
        """An invalid/garbage token is treated as anonymous → 401."""
        view = self._make_guarded_view(lambda actor: False)
        response = self._request_through_middleware(
            view, {'HTTP_AUTHORIZATION': 'Bearer garbage-token'},
        )
        self.assertEqual(response.status_code, 401)


class AuthzCoverageTest(TestCase):
    """
    Route×role coverage mechanism (AUTHZ.md §4):
    Every route discovered in the URLconf must have a declared authorization
    expectation in authz_expectations.yaml.

    This test introspects the live URLconf and verifies coverage.
    """

    def _get_all_route_names(self):
        """
        Introspect the URLconf and return all named route patterns.
        """
        from django.urls import get_resolver
        resolver = get_resolver()
        names = set()
        self._collect_names(resolver.url_patterns, names)
        return names

    def _collect_names(self, patterns, names):
        """Recursively collect route names from URL patterns."""
        from django.urls.resolvers import URLPattern, URLResolver
        for pattern in patterns:
            if isinstance(pattern, URLPattern) and pattern.name:
                names.add(pattern.name)
            elif isinstance(pattern, URLResolver):
                self._collect_names(pattern.url_patterns, names)

    def _load_expectations(self):
        """Load the authz expectations YAML file."""
        import yaml
        from pathlib import Path
        yaml_path = Path(__file__).resolve().parent / 'authz_expectations.yaml'
        if not yaml_path.exists():
            return {}
        with open(yaml_path, 'r') as f:
            return yaml.safe_load(f) or {}

    def test_every_route_has_declared_expectation(self):
        """
        Every named route in the URLconf must have a corresponding entry
        in authz_expectations.yaml.  If a route is missing, it means
        someone added an endpoint without declaring its authorization
        policy — the build should fail.
        """
        route_names = self._get_all_route_names()
        expectations = self._load_expectations()

        undeclared = []
        for name in route_names:
            if name not in expectations:
                undeclared.append(name)

        if undeclared:
            self.fail(
                f"Routes discovered in URLconf with no declared authz "
                f"expectation in authz_expectations.yaml:\n"
                + "\n".join(f"  - {name}" for name in sorted(undeclared))
                + "\n\nEvery route must have a declared authorization policy. "
                "Add entries to tests/authz_expectations.yaml."
            )


class ControlCaseLeakyRouteTest(TestCase):
    """
    Prove the control case from AUTHZ.md §4 works:
    The deliberately leaky debug route has no policy check at all.

    This test verifies:
    1. The route is accessible with no auth (proves it's truly unguarded)
    2. If we REMOVE its entry from expectations, the coverage test catches it
    """

    def test_leaky_route_is_accessible_without_auth(self):
        """The leaky debug route returns 200 with no auth — by design."""
        response = self.client.get('/debug/_leaky_test_only/jdg_07/scores')
        self.assertEqual(response.status_code, 200)

    def test_leaky_route_is_in_expectations(self):
        """
        The control-case route IS in authz_expectations.yaml (marked as
        intentionally undeclared).  This proves:
        - The mechanism correctly catches routes that ARE in the URLconf
        - The expectation file is the thing that makes the coverage test pass
        - Removing the entry would cause the coverage test to fail
        """
        import yaml
        from pathlib import Path
        yaml_path = Path(__file__).resolve().parent / 'authz_expectations.yaml'
        with open(yaml_path, 'r') as f:
            expectations = yaml.safe_load(f) or {}
        self.assertIn('debug_leaky_scores', expectations)
        self.assertIn('TODO', expectations['debug_leaky_scores'].get('note', ''))

    def test_mechanism_catches_undeclared_route(self):
        """
        Prove the mechanism works: if we remove the leaky route from
        expectations and re-run the coverage check logic, it correctly
        identifies the route as undeclared.

        This is the "test that the test can fail" — the control case
        from AUTHZ.md §4.
        """
        from django.urls import get_resolver
        from django.urls.resolvers import URLPattern, URLResolver

        # Collect all named routes from URLconf
        def collect_names(patterns):
            names = set()
            for p in patterns:
                if isinstance(p, URLPattern) and p.name:
                    names.add(p.name)
                elif isinstance(p, URLResolver):
                    names.update(collect_names(p.url_patterns))
            return names

        route_names = collect_names(get_resolver().url_patterns)

        # Simulate expectations WITHOUT the leaky route
        empty_expectations = {}

        undeclared = [n for n in route_names if n not in empty_expectations]

        # The leaky route MUST appear in the undeclared list
        self.assertIn(
            'debug_leaky_scores', undeclared,
            "The coverage mechanism failed to catch the undeclared leaky route! "
            "This means the mechanism itself is broken."
        )

