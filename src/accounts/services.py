"""
Account domain service layer.

Provides user registration, credential validation, token session management,
and audit logging for account operations.
"""

from django.db import transaction
from django.utils import timezone

from accounts.models import AuthToken, EventMembership, EventRole, User
from events.models import Event
from services import audit


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

        target_event = event or Event.objects.first()
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
