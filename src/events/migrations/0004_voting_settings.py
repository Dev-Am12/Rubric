import secrets

from django.db import migrations, models

import events.models


def populate_voting_seed(apps, schema_editor):
    Event = apps.get_model('events', 'Event')
    alias = schema_editor.connection.alias
    for event in Event.objects.using(alias).filter(voting_seed__isnull=True).iterator():
        Event.objects.using(alias).filter(pk=event.pk).update(voting_seed=secrets.token_hex(32))


class Migration(migrations.Migration):
    dependencies = [('events', '0003_event_is_current')]

    operations = [
        migrations.AddField(
            model_name='event',
            name='voting_access',
            field=models.CharField(
                choices=[('OPEN', 'Open link'), ('AUTH', 'Authenticated users')],
                default='OPEN',
                max_length=8,
            ),
        ),
        migrations.AddField(
            model_name='event',
            name='votes_per_voter',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='event',
            name='voting_seed',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.RunPython(populate_voting_seed, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='event',
            name='voting_seed',
            field=models.CharField(default=events.models.generate_voting_seed, editable=False, max_length=64),
        ),
    ]
