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
