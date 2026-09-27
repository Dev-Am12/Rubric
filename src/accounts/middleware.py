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
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.actor = self._resolve_actor(request)

        try:
            response = self.get_response(request)
        except PermissionDenied:
            return self._permission_denied_response(request)

        return response

    def _resolve_actor(self, request):
        """Extract token from header/cookie, look up AuthToken, build Actor."""
        raw_token = self._extract_token(request)
        if not raw_token:
            return AnonymousActor()

        token_hash = AuthToken.hash_token(raw_token)
        try:
            auth_token = AuthToken.objects.select_related('user').get(
                token_hash=token_hash,
            )
        except AuthToken.DoesNotExist:
            return AnonymousActor()

        # Check expiry: if expires_at is set and in the past, treat as invalid
        if auth_token.expires_at is not None:
            now = timezone.now()
            if auth_token.expires_at <= now:
                return AnonymousActor()

        user = auth_token.user

        # Resolve the current event.
        # For now, we use the first (and likely only) event in the system.
        # In a multi-event system, this would be extracted from the URL.
        event = Event.objects.first()
        if event is None:
            # No event exists yet — authenticated but no event context
            return Actor(user=user, event=None)

        # Prefetch memberships for this user+event to avoid N+1 in Actor
        memberships = list(
            EventMembership.objects.filter(user=user, event=event)
        )
        return Actor(user=user, event=event, _memberships=memberships)

    def _extract_token(self, request):
        """
        Extract the raw token string from the request.

        Priority: Authorization header > session cookie.
        """
        # 1. Authorization: Bearer <token>
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith('Bearer '):
            return auth_header[7:].strip()

        # 2. Cookie: session=<token>
        session_cookie = request.COOKIES.get('session', '')
        if session_cookie:
            return session_cookie

        return None

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
