"""
AuthMiddleware: resolves raw Authorization/Cookie headers into an Actor.

Design reference: AUTHZ.md §1 (actor resolution flow).

This middleware runs on every request and sets request.actor to either
an Actor (authenticated, event-scoped) or AnonymousActor (no valid token).
Views and service functions use request.actor exclusively for permission
checks — never request.user.

The exception-handler portion converts PermissionDenied into the correct
HTTP status:
    AnonymousActor + PermissionDenied  →  401
    resolved Actor + PermissionDenied  →  403

CSRF handling (G2):
    When a request is authenticated via the Authorization header (not the
    cookie fallback), CSRF enforcement is bypassed by setting
    request._dont_enforce_csrf_checks = True.  This matches how DRF's own
    TokenAuthentication draws the line vs. SessionAuthentication: header-
    based token auth is not vulnerable to CSRF, cookie-based auth is.
    Requests authenticated via the session cookie keep full CSRF enforcement.
"""

import json

from django.http import JsonResponse
from django.utils import timezone

from accounts.actors import Actor, AnonymousActor, PermissionDenied
from accounts.models import AuthToken, EventMembership
from events.models import Event


class AuthMiddleware:
    """
    Resolves Authorization/Cookie headers into request.actor.

    Token lookup:
    1. Check for "Authorization: Bearer <token>" header.
    2. If absent, check for "session" cookie (for browser sessions).
    3. Hash the raw token with SHA-256, look up AuthToken by token_hash.
    4. If found and not expired, resolve the user into an Actor scoped
       to the current event (or the first available event if none is
       specified in the URL).
    5. Otherwise, set request.actor = AnonymousActor().

    CSRF exemption:
    If the token was provided via the Authorization header, set
    request._dont_enforce_csrf_checks = True so Django's
    CsrfViewMiddleware skips CSRF validation for this request.
    Cookie-based auth keeps CSRF enforcement intact.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.actor, auth_source = self._resolve_actor(request)

        # CSRF bypass for header-authenticated requests only.
        # Cookie-authenticated requests must keep CSRF enforcement.
        if auth_source == 'header':
            request._dont_enforce_csrf_checks = True

        try:
            response = self.get_response(request)
        except PermissionDenied:
            return self._permission_denied_response(request)

        return response

    def process_exception(self, request, exception):
        if isinstance(exception, PermissionDenied):
            return self._permission_denied_response(request)
        return None

    def _resolve_actor(self, request):
        """
        Extract token from header/cookie, look up AuthToken, build Actor.

        Returns (actor, auth_source) where auth_source is one of:
          'header'  — token came from Authorization header
          'cookie'  — token came from session cookie
          None      — no valid token found
        """
        raw_token, auth_source = self._extract_token(request)
        if not raw_token:
            return AnonymousActor(), None

        token_hash = AuthToken.hash_token(raw_token)
        try:
            auth_token = AuthToken.objects.select_related('user').get(
                token_hash=token_hash,
            )
        except AuthToken.DoesNotExist:
            return AnonymousActor(), None

        # Check expiry: if expires_at is set and in the past, treat as invalid
        if auth_token.expires_at is not None:
            now = timezone.now()
            if auth_token.expires_at <= now:
                return AnonymousActor(), None

        user = auth_token.user

        # Resolve the current event.
        # For now, we use the first (and likely only) event in the system.
        # In a multi-event system, this would be extracted from the URL.
        event = Event.objects.first()
        if event is None:
            # No event exists yet — authenticated but no event context
            return Actor(user=user, event=None), auth_source

        # Prefetch memberships for this user+event to avoid N+1 in Actor
        memberships = list(
            EventMembership.objects.filter(user=user, event=event)
        )
        return Actor(user=user, event=event, _memberships=memberships), auth_source

    def _extract_token(self, request):
        """
        Extract the raw token string from the request.

        Priority: Authorization header > session cookie.
        Returns (raw_token, source) where source is 'header' or 'cookie'.
        """
        # 1. Authorization: Bearer <token>
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith('Bearer '):
            return auth_header[7:].strip(), 'header'

        # 2. Cookie: session=<token>
        session_cookie = request.COOKIES.get('session', '')
        if session_cookie:
            return session_cookie, 'cookie'

        return None, None

    def _permission_denied_response(self, request):
        """
        Map PermissionDenied to the correct HTTP status.

        AUTHZ.md §1:
          AnonymousActor → 401 (not authenticated)
          resolved Actor → 403 (authenticated but forbidden)
        """
        if getattr(request, 'actor', None) is None or request.actor.is_anonymous:
            return JsonResponse(
                {'error': 'authentication_required', 'detail': 'Valid authentication credentials are required.'},
                status=401,
            )
        else:
            return JsonResponse(
                {'error': 'forbidden', 'detail': 'You do not have permission to perform this action.'},
                status=403,
            )
