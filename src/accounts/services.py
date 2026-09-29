"""
Account domain service layer.

Provides user registration, credential validation, token session management,
and audit logging for account operations.
"""

import hashlib
import hmac
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.models import AuthAttempt, AuthToken, EventMembership, EventRole, User
from events.models import Event
from events.services import current_event
from services import audit


AUTH_RATE_LIMIT_ATTEMPTS = 10
AUTH_RATE_LIMIT_WINDOW = timedelta(minutes=5)
AUTH_RATE_LIMIT_MESSAGE = "Too many authentication attempts. Please try again in 5 minutes."


GENERIC_LOGIN_ERROR = "Invalid email or password."


def register(email, password, display_name="", event=None):
    """
    Register a new user account.

    Validates inputs, hashes password using Django's hasher, creates the user,
    associates event participant membership, creates a session token, and records
    an audit log entry.
    """
    if not email or not isinstance(email, str) or not email.strip():
        raise ValueError("A valid email address is required.")
    email = email.strip().lower()

    if not password or not isinstance(password, str) or len(password) < 6:
        raise ValueError("Password must be at least 6 characters long.")

    if User.objects.filter(email__iexact=email).exists():
        raise ValueError("A user with this email already exists.")

    display_name = (display_name or "").strip() or email.split("@")[0]

    with transaction.atomic():
        user = User.objects.create_user(
            email=email,
            password=password,
            display_name=display_name,
        )

        target_event = event or current_event()
        if target_event is not None:
            EventMembership.objects.get_or_create(
                user=user,
                event=target_event,
                defaults={"role": EventRole.PARTICIPANT},
            )

        token_obj, raw_token = AuthToken.create_token(user=user, label="session")

        audit.record(
            user,
            "user.register",
            user,
            {
                "email": user.email,
                "display_name": user.display_name,
            },
        )

    return user, raw_token


def login(email, password):
    """
    Authenticate user credentials and create a session token.

    Failure must never reveal whether an email exists in the system.
    Successful logins are audit-logged.
    """
    if not email or not password:
        raise ValueError(GENERIC_LOGIN_ERROR)

    email = email.strip().lower()
    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        # Prevent timing-based user enumeration by running check_password against dummy
        User().set_password(password)
        raise ValueError(GENERIC_LOGIN_ERROR)

    if not user.has_usable_password() or not user.check_password(password):
        raise ValueError(GENERIC_LOGIN_ERROR)

    with transaction.atomic():
        token_obj, raw_token = AuthToken.create_token(user=user, label="session")

        audit.record(
            user,
            "user.login",
            user,
            {
                "email": user.email,
            },
        )

    return user, raw_token


def logout(raw_token):
    """
    Invalidate an active session token server-side.
    """
    if not raw_token:
        return False

    token_hash = AuthToken.hash_token(raw_token)
    deleted_count, _ = AuthToken.objects.filter(token_hash=token_hash).delete()
    return deleted_count > 0


def get_client_ip(request) -> str:
    """Extract client IP from request. Uses REMOTE_ADDR directly."""
    return request.META.get("REMOTE_ADDR", "") or ""


def hash_ip(ip: str) -> str:
    """Compute keyed HMAC-SHA256 hash of IP to prevent storing raw IPs."""
    key = getattr(settings, "SECRET_KEY", "rubric-default-secret-key").encode("utf-8")
    return hmac.new(key, (ip or "").encode("utf-8"), hashlib.sha256).hexdigest()


def check_auth_rate_limit(request, action: str = "auth") -> tuple[bool, str | None]:
    """
    Check if the client IP has exceeded the auth rate limit (10 attempts / 5 minutes).
    If within budget, records the attempt and returns (True, None).
    If exceeded, returns (False, AUTH_RATE_LIMIT_MESSAGE).
    """
    ip = get_client_ip(request)
    ip_h = hash_ip(ip)
    cutoff = timezone.now() - AUTH_RATE_LIMIT_WINDOW

    count = AuthAttempt.objects.filter(
        ip_hash=ip_h,
        action=action,
        created_at__gte=cutoff,
    ).count()

    if count >= AUTH_RATE_LIMIT_ATTEMPTS:
        return False, AUTH_RATE_LIMIT_MESSAGE

    AuthAttempt.objects.create(
        ip_hash=ip_h,
        action=action,
    )
    return True, None
