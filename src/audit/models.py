"""Tamper-evident, append-only audit chain models."""

from django.conf import settings
from django.db import models


class ImmutableAuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise TypeError('Audit log entries are immutable')

    def delete(self):
        raise TypeError('Audit log entries are immutable')


class AuditLogEntry(models.Model):
    seq = models.BigIntegerField(primary_key=True)
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name='audit_entries',
    )
    actor_label = models.CharField(max_length=255, blank=True, default='')
    action = models.CharField(max_length=255)
    target_type = models.CharField(max_length=255)
    target_id = models.CharField(max_length=255)
    payload = models.JSONField(default=dict)
    created_at = models.CharField(max_length=40)
    prev_hash = models.CharField(max_length=64)
    entry_hash = models.CharField(max_length=64)

    objects = ImmutableAuditQuerySet.as_manager()

    class Meta:
        db_table = 'audit_auditlogentry'
        ordering = ['seq']

    def save(self, *args, **kwargs):
        if self.pk is not None and type(self).objects.filter(pk=self.pk).exists():
            raise TypeError('Audit log entries are immutable')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise TypeError('Audit log entries are immutable')


class AuditChainHead(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    seq = models.BigIntegerField(default=0)
    head_hash = models.CharField(max_length=64)

    class Meta:
        db_table = 'audit_auditchainhead'
        constraints = [
            models.CheckConstraint(condition=models.Q(id=1), name='audit_chain_head_singleton'),
        ]
