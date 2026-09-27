from django.conf import settings
from django.db import models


class Team(models.Model):
    event = models.ForeignKey(
        'events.Event',
        on_delete=models.CASCADE,
        related_name='teams',
    )
    name = models.CharField(max_length=255)
    invite_code = models.CharField(max_length=64, unique=True)
    external_id = models.CharField(max_length=64, null=True, blank=True, unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_teams',
    )

    class Meta:
        db_table = 'teams_team'

    def __str__(self):
        return f"{self.name} ({self.event.slug})"


class TeamMembership(models.Model):
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='team_memberships',
    )

    class Meta:
        db_table = 'teams_teammembership'
        constraints = [
            models.UniqueConstraint(
                fields=['team', 'user'],
                name='unique_team_user',
            )
        ]

    def __str__(self):
        return f"{self.user.email} in {self.team.name}"
