"""
Actor resolution and policy enforcement layer.

This module is the single point of truth for "who is making this request and
what are they allowed to do."  Every service function takes an Actor (or
AnonymousActor) as its first argument; no view or API handler ever reaches
for request.user directly for anything permission-related.

Design references:
  - AUTHZ.md §1 (actor resolution)
  - SCHEMA.md §0, design principle 1 (service layer owns all mutations)
  - PLAN.md P-03 (service layer with explicit actor-based authorization)
"""

from django.utils import timezone

from accounts.models import EventMembership, EventRole


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class PermissionDenied(Exception):
    """
    Raised by service-layer require() calls when an actor lacks permission.

    The exception-handler mapping (AUTHZ.md §1):
      AnonymousActor + PermissionDenied  →  HTTP 401
      resolved Actor + PermissionDenied  →  HTTP 403
    """
    pass


# ---------------------------------------------------------------------------
# Actor classes
# ---------------------------------------------------------------------------

class AnonymousActor:
    """
    Represents an unauthenticated request (no token, invalid token, or
    expired token).  Every permission boolean is False — every check
    defaults closed.
    """
    is_anonymous = True
    user = None
    event = None

    @property
    def is_participant(self):
        return False

    @property
    def is_judge(self):
        return False

    @property
    def is_organizer(self):
        return False

    @property
    def is_site_admin(self):
        return False

    @property
    def judge_external_id(self):
        return None

    def __repr__(self):
        return "AnonymousActor()"


class Actor:
    """
    A resolved, authenticated identity scoped to a specific event.

    Role booleans (.is_participant, .is_judge, .is_organizer) are computed
    independently from EventMembership rows — a single user CAN hold more
    than one role in the same event (AUTHZ.md §1, stress-test F12).  There
    is deliberately no singular .role attribute.

    .is_site_admin comes from User.is_site_admin, which is event-independent.
    """

    is_anonymous = False

    def __init__(self, user, event=None, _memberships=None):
        self.user = user
        self.event = event

        # Pre-compute role flags from EventMembership rows.
        # If memberships were prefetched by the middleware, use them;
        # otherwise query (test convenience).
        if _memberships is not None:
            roles = {m.role for m in _memberships}
        elif event is not None:
            roles = set(
                EventMembership.objects.filter(
                    user=user, event=event,
                ).values_list('role', flat=True)
            )
        else:
            roles = set()

        self._roles = roles

    @property
    def is_participant(self):
        return EventRole.PARTICIPANT in self._roles

    @property
    def is_judge(self):
        return EventRole.JUDGE in self._roles

    @property
    def is_organizer(self):
        return EventRole.ORGANIZER in self._roles

    @property
    def is_site_admin(self):
        return self.user.is_site_admin

    @property
    def judge_external_id(self):
        """The external_id (e.g. 'jdg_07') of this user, if they are a judge."""
        if self.is_judge and self.user.external_id:
            return self.user.external_id
        return None

    def __repr__(self):
        roles = []
        if self.is_participant:
            roles.append('participant')
        if self.is_judge:
            roles.append('judge')
        if self.is_organizer:
            roles.append('organizer')
        if self.is_site_admin:
            roles.append('site_admin')
        event_slug = self.event.slug if self.event else '?'
        return f"Actor({self.user.email}, event={event_slug}, roles={roles})"


# ---------------------------------------------------------------------------
# Policy enforcement helper
# ---------------------------------------------------------------------------

def require(actor, condition, status=403):
    """
    Enforce a policy check.  If `condition` is falsy, raise PermissionDenied.

    The caller (a services.* function) passes the actor and the boolean
    condition that must be true for the operation to proceed.

    The HTTP status distinction (401 vs 403) is NOT decided here — it's
    decided by the exception handler that catches PermissionDenied, based
    on whether the actor is anonymous or resolved:

        AnonymousActor → 401  (you didn't authenticate at all)
        Actor          → 403  (you authenticated, but you're not allowed)

    The `status` parameter is intentionally unused for now — it exists
    as a future extension point (e.g., for a 404 "hide existence" case
    per AUTHZ.md §6) but the current design always maps 401/403 from the
    actor type alone.  This is deliberate: the service layer should never
    need to know what HTTP status to return.
    """
    if not condition:
        raise PermissionDenied()


def require_event_role(actor, event, role):
    """Require a role on the specified event; site administrators are allowed."""
    if not actor.is_anonymous and actor.is_site_admin:
        return
    event_id = getattr(event, 'pk', event)
    allowed = (
        not actor.is_anonymous
        and actor.user is not None
        and EventMembership.objects.filter(
            user=actor.user,
            event_id=event_id,
            role=role,
        ).exists()
    )
    require(actor, allowed)
