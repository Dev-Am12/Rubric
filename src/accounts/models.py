import hashlib
import secrets
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    def create_user(self, email, display_name="", password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, display_name=display_name, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, display_name="", password=None, **extra_fields):
        extra_fields.setdefault('is_site_admin', True)
        return self.create_user(email, display_name, password, **extra_fields)


class User(AbstractBaseUser):
    email = models.EmailField(unique=True, max_length=255)
    display_name = models.CharField(max_length=255, blank=True)
    is_site_admin = models.BooleanField(default=False)
    external_id = models.CharField(max_length=64, null=True, blank=True, unique=True)
    created_at = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['display_name']

    class Meta:
        db_table = 'accounts_user'

    def __str__(self):
        return self.display_name or self.email


class AuthToken(models.Model):
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='auth_tokens',
    )
    label = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'accounts_authtoken'

    @classmethod
    def hash_token(cls, raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode('utf-8')).hexdigest()

    @classmethod
    def create_token(cls, user, label="", expires_at=None, raw_token=None):
        if raw_token is None:
            raw_token = secrets.token_urlsafe(32)
        token_hash = cls.hash_token(raw_token)
        instance = cls.objects.create(
            user=user,
            token_hash=token_hash,
            label=label,
            expires_at=expires_at,
        )
        return instance, raw_token

    def __str__(self):
        return f"AuthToken({self.label or self.user.email})"


class EventRole(models.TextChoices):
    PARTICIPANT = 'PARTICIPANT', 'Participant'
    JUDGE = 'JUDGE', 'Judge'
    ORGANIZER = 'ORGANIZER', 'Organizer'


class EventMembership(models.Model):
    event = models.ForeignKey(
        'events.Event',
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='event_memberships',
    )
    role = models.CharField(max_length=32, choices=EventRole.choices)

    class Meta:
        db_table = 'accounts_eventmembership'
        constraints = [
            models.UniqueConstraint(
                fields=['event', 'user', 'role'],
                name='unique_event_user_role',
            )
        ]

    def __str__(self):
        return f"{self.user.email} - {self.event.slug} ({self.role})"
