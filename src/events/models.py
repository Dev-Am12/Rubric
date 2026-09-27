from django.conf import settings
from django.db import models


class Event(models.Model):
    slug = models.SlugField(max_length=255, unique=True)
    name = models.CharField(max_length=255)
    external_id = models.CharField(max_length=64, null=True, blank=True, unique=True)
    submissions_open_at = models.DateTimeField(null=True, blank=True)
    submissions_close_at = models.DateTimeField()
    voting_opens_at = models.DateTimeField(null=True, blank=True)
    voting_closes_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_events',
    )

    class Meta:
        db_table = 'events_event'

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

