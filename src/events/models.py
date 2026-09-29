import secrets

from django.conf import settings
from django.db import models


def generate_voting_seed():
    return secrets.token_hex(32)


class VotingAccess(models.TextChoices):
    OPEN = 'OPEN', 'Open link'
    AUTH = 'AUTH', 'Authenticated users'


class Event(models.Model):
    slug = models.SlugField(max_length=255, unique=True)
    name = models.CharField(max_length=255)
    external_id = models.CharField(max_length=64, null=True, blank=True, unique=True)
    submissions_open_at = models.DateTimeField(null=True, blank=True)
    submissions_close_at = models.DateTimeField()
    voting_opens_at = models.DateTimeField(null=True, blank=True)
    voting_closes_at = models.DateTimeField(null=True, blank=True)
    voting_access = models.CharField(
        max_length=8,
        choices=VotingAccess.choices,
        default=VotingAccess.OPEN,
    )
    votes_per_voter = models.PositiveIntegerField(null=True, blank=True)
    # Secret per-event entropy for OPEN voter fingerprints and V-03 ballot order.
    voting_seed = models.CharField(max_length=64, default=generate_voting_seed, editable=False)
    is_current = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_events',
    )

    class Meta:
        db_table = 'events_event'
        constraints = [
            models.UniqueConstraint(
                fields=['is_current'],
                condition=models.Q(is_current=True),
                name='unique_current_event',
            )
        ]

    def __str__(self):
        return self.name


class Track(models.Model):
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='tracks',
    )
    name = models.CharField(max_length=255)
    external_id = models.CharField(max_length=64, null=True, blank=True, unique=True)

    class Meta:
        db_table = 'events_track'

    def __str__(self):
        return f"{self.name} ({self.event.slug})"


class Prize(models.Model):
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name='prizes',
    )
    rank_label = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    class Meta:
        db_table = 'events_prize'

    def __str__(self):
        return f"{self.rank_label} ({self.event.slug})"
