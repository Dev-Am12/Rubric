from django.conf import settings
from django.db import models
from django.utils import timezone


class ProjectStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    SUBMITTED = 'SUBMITTED', 'Submitted'


class Project(models.Model):
    event = models.ForeignKey(
        'events.Event',
        on_delete=models.CASCADE,
        related_name='projects',
    )
    team = models.ForeignKey(
        'teams.Team',
        on_delete=models.CASCADE,
        related_name='projects',
    )
    track = models.ForeignKey(
        'events.Track',
        on_delete=models.CASCADE,
        related_name='projects',
    )
    title = models.CharField(max_length=512)
    summary = models.TextField()
    description = models.TextField(blank=True, default='')
    repo_url = models.URLField(max_length=1024, blank=True, default='')
    demo_video_url = models.URLField(max_length=1024, blank=True, default='')
    live_url = models.URLField(max_length=1024, blank=True, default='')
    # JSONField instead of Postgres ArrayField — works on both Postgres
    # and the SQLite in-memory backend used by settings_test.py. Same
    # semantics (a list of strings), portable across test/prod backends.
    tech_tags = models.JSONField(default=list, blank=True)
    custom_answers = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16,
        choices=ProjectStatus.choices,
        default=ProjectStatus.DRAFT,
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    external_id = models.CharField(max_length=64, null=True, blank=True, unique=True)

    # Duplicate-submission handling (SCHEMA.md §1.1, NORMALIZATION.md D-02):
    # The EARLIER submission (prj_07) flags itself against the LATER
    # canonical one (prj_41): prj_07.is_duplicate_of = prj_41.
    is_duplicate_of = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='duplicates',
    )
    duplicate_flag_reason = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'submissions_project'

    def __str__(self):
        return f"{self.title} ({self.external_id or self.id})"
