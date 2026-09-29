from django.conf import settings
from django.db import models
from django.utils import timezone


class VoteMode(models.TextChoices):
    OPEN = 'OPEN', 'Open link'
    AUTH = 'AUTH', 'Authenticated user'


class VoteAttemptOutcome(models.TextChoices):
    ACCEPTED = 'ACCEPTED', 'Accepted'
    REJECTED_DUPLICATE = 'REJECTED_DUPLICATE', 'Duplicate'
    REJECTED_RATE_LIMIT = 'REJECTED_RATE_LIMIT', 'Rate limited'
    REJECTED_CLOSED = 'REJECTED_CLOSED', 'Voting closed'
    REJECTED_BUDGET = 'REJECTED_BUDGET', 'Vote budget exhausted'
    WITHDRAWN = 'WITHDRAWN', 'Withdrawn'


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise TypeError('VoteAttempt rows are append-only')

    def delete(self):
        raise TypeError('VoteAttempt rows are append-only')


class VoteAttempt(models.Model):
    event = models.ForeignKey('events.Event', on_delete=models.PROTECT, related_name='vote_attempts')
    project = models.ForeignKey('submissions.Project', on_delete=models.PROTECT, related_name='vote_attempts')
    mode = models.CharField(max_length=8, choices=VoteMode.choices)
    voter_fingerprint = models.CharField(max_length=128, db_index=False)
    outcome = models.CharField(max_length=32, choices=VoteAttemptOutcome.choices)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        db_table = 'voting_voteattempt'
        indexes = [
            models.Index(
                fields=['voter_fingerprint', 'created_at'],
                name='vote_attempt_fingerprint_time',
            ),
            models.Index(
                fields=['event', 'mode', 'voter_fingerprint', 'created_at'],
                name='vote_attempt_rate_lookup',
            ),
        ]
        ordering = ['created_at', 'id']

    def save(self, *args, **kwargs):
        if self.pk is not None and type(self).objects.filter(pk=self.pk).exists():
            raise TypeError('VoteAttempt rows are append-only')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise TypeError('VoteAttempt rows are append-only')


class Vote(models.Model):
    event = models.ForeignKey('events.Event', on_delete=models.CASCADE, related_name='votes')
    project = models.ForeignKey('submissions.Project', on_delete=models.CASCADE, related_name='votes')
    mode = models.CharField(max_length=8, choices=VoteMode.choices)
    voter_fingerprint = models.CharField(max_length=128)
    weight = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    # Nullable only to permit the vote's unique insert before appending its immutable attempt.
    # Both rows are linked before the enclosing transaction commits.
    attempt = models.ForeignKey(
        VoteAttempt,
        on_delete=models.SET_NULL,
        related_name='accepted_votes',
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'voting_vote'
        constraints = [
            models.UniqueConstraint(
                fields=['event', 'project', 'mode', 'voter_fingerprint'],
                name='uniq_vote_event_project_mode_fingerprint',
            )
        ]
        ordering = ['created_at', 'id']


class Comment(models.Model):
    project = models.ForeignKey('submissions.Project', on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='voting_comments',
    )
    mode = models.CharField(max_length=8, choices=VoteMode.choices)
    voter_fingerprint = models.CharField(max_length=128)
    body = models.TextField()
    is_flagged = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'voting_comment'
        ordering = ['created_at', 'id']
