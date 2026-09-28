from django.conf import settings
from django.db import models
from django.utils import timezone


class Rubric(models.Model):
    event = models.ForeignKey('events.Event', on_delete=models.CASCADE, related_name='rubrics')
    name = models.CharField(max_length=255)

    class Meta:
        db_table = 'judging_rubric'
        constraints = [models.UniqueConstraint(fields=['event'], name='uniq_rubric_per_event')]


class RubricCriterion(models.Model):
    rubric = models.ForeignKey(Rubric, on_delete=models.CASCADE, related_name='criteria')
    name = models.CharField(max_length=255)
    weight = models.DecimalField(max_digits=8, decimal_places=4, default=1)
    max_score = models.DecimalField(max_digits=8, decimal_places=2, default=5)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'judging_rubriccriterion'
        ordering = ['order', 'id']
        constraints = [models.UniqueConstraint(fields=['rubric', 'name'], name='uniq_criterion_rubric_name')]


class AssignmentStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    COMPLETED = 'COMPLETED', 'Completed'


class JudgeAssignment(models.Model):
    event = models.ForeignKey('events.Event', on_delete=models.CASCADE, related_name='judge_assignments')
    judge = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='judge_assignments')
    project = models.ForeignKey('submissions.Project', on_delete=models.CASCADE, related_name='judge_assignments')
    status = models.CharField(max_length=16, choices=AssignmentStatus.choices, default=AssignmentStatus.PENDING)
    assigned_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'judging_judgeassignment'
        constraints = [models.UniqueConstraint(fields=['judge', 'project'], name='uniq_judge_project_assignment')]


class Ballot(models.Model):
    assignment = models.OneToOneField(JudgeAssignment, on_delete=models.CASCADE, related_name='ballot')
    comment = models.TextField(blank=True, default='')
    submitted_at = models.DateTimeField(null=True, blank=True)
    is_complete = models.BooleanField(default=False)

    class Meta:
        db_table = 'judging_ballot'


class BallotScore(models.Model):
    ballot = models.ForeignKey(Ballot, on_delete=models.CASCADE, related_name='scores')
    criterion = models.ForeignKey(RubricCriterion, on_delete=models.CASCADE, related_name='ballot_scores')
    value = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        db_table = 'judging_ballotscore'
        constraints = [models.UniqueConstraint(fields=['ballot', 'criterion'], name='uniq_ballot_criterion_score')]


class NormalizationRun(models.Model):
    event = models.ForeignKey('events.Event', on_delete=models.CASCADE, related_name='normalization_runs')
    computed_at = models.DateTimeField(default=timezone.now)
    method_name = models.CharField(max_length=128)
    parameters = models.JSONField(default=dict)

    class Meta:
        db_table = 'judging_normalizationrun'
        ordering = ['id']


class NormalizedScore(models.Model):
    run = models.ForeignKey(NormalizationRun, on_delete=models.CASCADE, related_name='scores')
    project = models.ForeignKey('submissions.Project', on_delete=models.CASCADE, related_name='normalized_scores')
    raw_mean = models.DecimalField(max_digits=14, decimal_places=8, null=True, blank=True)
    normalized_mean = models.DecimalField(max_digits=14, decimal_places=8, null=True, blank=True)
    rank = models.PositiveIntegerField(null=True, blank=True)
    judge_graph_component_id = models.PositiveIntegerField(null=True, blank=True)
    judge_graph_fiedler_value = models.FloatField(null=True, blank=True)
    rank_ci_low = models.DecimalField(max_digits=14, decimal_places=8, null=True, blank=True)
    rank_ci_high = models.DecimalField(max_digits=14, decimal_places=8, null=True, blank=True)

    class Meta:
        db_table = 'judging_normalizedscore'
        ordering = ['project_id']
        constraints = [models.UniqueConstraint(fields=['run', 'project'], name='uniq_normalized_score_run_project')]


class AssignmentRun(models.Model):
    event = models.ForeignKey('events.Event', on_delete=models.CASCADE, related_name='assignment_runs')
    run_at = models.DateTimeField(default=timezone.now)
    target_k = models.PositiveIntegerField()
    seed = models.BigIntegerField()
    under_coverage = models.JSONField(default=list)
    connectivity_report = models.JSONField(default=dict)
    anchor_injections = models.JSONField(default=list)

    class Meta:
        db_table = 'judging_assignmentrun'
        ordering = ['id']


class JudgeInvite(models.Model):
    event = models.ForeignKey(
        'events.Event',
        on_delete=models.CASCADE,
        related_name='judge_invites',
    )
    email = models.EmailField(max_length=255)
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    tracks = models.ManyToManyField(
        'events.Track',
        blank=True,
        related_name='judge_invites',
    )
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_judge_invites',
    )

    class Meta:
        db_table = 'judging_judgeinvite'
        ordering = ['-created_at']

    @classmethod
    def hash_token(cls, raw_token: str) -> str:
        import hashlib
        return hashlib.sha256(raw_token.encode('utf-8')).hexdigest()

    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    def is_accepted(self) -> bool:
        return self.accepted_at is not None

    def __str__(self):
        status = "Accepted" if self.accepted_at else ("Expired" if self.is_expired() else "Pending")
        return f"JudgeInvite({self.email} - {self.event.slug} - {status})"

