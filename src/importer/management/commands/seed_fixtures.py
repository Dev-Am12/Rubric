import json
import os
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify

from accounts.models import AuthToken, EventMembership, EventRole, User
from events.models import Event, Track

SEED_TOKENS = {
    'organizer': 'rubric_seed_organizer_tok_9f8e7d6c5b4a',
    'judge_a': 'rubric_seed_judge_a_tok_1a2b3c4d5e6f',
    'judge_b': 'rubric_seed_judge_b_tok_7a8b9c0d1e2f',
    'participant': 'rubric_seed_participant_tok_3f4e5d6c7b8a',
}


def find_fixtures_file(explicit_path=None):
    if explicit_path and os.path.exists(explicit_path):
        return Path(explicit_path)
    candidates = [
        Path.cwd() / 'fixtures.json',
        Path(settings.BASE_DIR).parent / 'fixtures.json',
        Path(settings.BASE_DIR) / 'fixtures.json',
        Path('/app/fixtures.json'),
    ]
    for c in candidates:
        if c.is_file():
            return c
    raise FileNotFoundError(
        "Could not find fixtures.json. Looked at: "
        + ", ".join(str(c) for c in candidates)
    )


class Command(BaseCommand):
    help = "Seed minimal fixtures (Event, Tracks, and D-11 personas) from fixtures.json"

    def add_arguments(self, parser):
        parser.add_argument(
            '--fixtures',
            default=None,
            help="Path to fixtures.json file",
        )
        parser.add_argument(
            '--idempotent',
            action='store_true',
            help="Safe to re-run without duplicating anything (default behavior)",
        )

    def handle(self, *args, **options):
        fixture_path = find_fixtures_file(options.get('fixtures'))
        with open(fixture_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 1. Organizer account (dedicated seed account, no fixture equivalent)
        organizer_user, _ = User.objects.update_or_create(
            email='organizer@rubric.local',
            defaults={
                'display_name': 'Organizer',
                'is_site_admin': True,
            },
        )

        # 2. Event (submissions_close_at verbatim from fixture)
        evt_data = data['event']
        evt_id = evt_data['id']
        evt_name = evt_data['name']
        submissions_close_raw = evt_data['submissions_close']
        submissions_close_at = parse_datetime(submissions_close_raw)
        if timezone.is_naive(submissions_close_at):
            submissions_close_at = timezone.make_aware(
                submissions_close_at, timezone=timezone.utc
            )

        slug = slugify(evt_name) or 'sample-hack-2026'
        event, _ = Event.objects.update_or_create(
            external_id=evt_id,
            defaults={
                'name': evt_name,
                'slug': slug,
                'submissions_close_at': submissions_close_at,
                'created_by': organizer_user,
            },
        )

        # 3. Tracks
        for t in data.get('tracks', []):
            Track.objects.update_or_create(
                external_id=t['id'],
                defaults={
                    'name': t['name'],
                    'event': event,
                },
            )

        # 4. EventMembership & AuthToken for Organizer
        EventMembership.objects.update_or_create(
            event=event,
            user=organizer_user,
            role=EventRole.ORGANIZER,
        )
        org_token_hash = AuthToken.hash_token(SEED_TOKENS['organizer'])
        AuthToken.objects.update_or_create(
            user=organizer_user,
            label='seed:organizer',
            defaults={
                'token_hash': org_token_hash,
                'expires_at': None,
            },
        )

        # 5. judge_a -> jdg_07 (Iva Petrova)
        jdg_07_info = next(
            (j for j in data.get('judges', []) if j.get('id') == 'jdg_07'),
            None,
        )
        judge_a_email = (
            jdg_07_info['email'] if jdg_07_info else 'iva.petrova@example.org'
        )
        judge_a_name = (
            jdg_07_info['name'] if jdg_07_info else 'Iva Petrova'
        )
        judge_a_user, _ = User.objects.update_or_create(
            external_id='jdg_07',
            defaults={
                'email': judge_a_email,
                'display_name': judge_a_name,
                'is_site_admin': False,
            },
        )
        EventMembership.objects.update_or_create(
            event=event,
            user=judge_a_user,
            role=EventRole.JUDGE,
        )
        ja_token_hash = AuthToken.hash_token(SEED_TOKENS['judge_a'])
        AuthToken.objects.update_or_create(
            user=judge_a_user,
            label='seed:judge_a',
            defaults={
                'token_hash': ja_token_hash,
                'expires_at': None,
            },
        )

        # 6. judge_b -> jdg_29 (Ines Rocha)
        jdg_29_info = next(
            (j for j in data.get('judges', []) if j.get('id') == 'jdg_29'),
            None,
        )
        judge_b_email = (
            jdg_29_info['email'] if jdg_29_info else 'ines.rocha@example.org'
        )
        judge_b_name = (
            jdg_29_info['name'] if jdg_29_info else 'Ines Rocha'
        )
        judge_b_user, _ = User.objects.update_or_create(
            external_id='jdg_29',
            defaults={
                'email': judge_b_email,
                'display_name': judge_b_name,
                'is_site_admin': False,
            },
        )
        EventMembership.objects.update_or_create(
            event=event,
            user=judge_b_user,
            role=EventRole.JUDGE,
        )
        jb_token_hash = AuthToken.hash_token(SEED_TOKENS['judge_b'])
        AuthToken.objects.update_or_create(
            user=judge_b_user,
            label='seed:judge_b',
            defaults={
                'token_hash': jb_token_hash,
                'expires_at': None,
            },
        )

        # 7. participant -> any one tm_07 member's email
        tm_07_info = next(
            (t for t in data.get('teams', []) if t.get('id') == 'tm_07'),
            None,
        )
        participant_email = (
            tm_07_info['members'][0]
            if (tm_07_info and tm_07_info.get('members'))
            else 'sana7@example.org'
        )
        participant_user, _ = User.objects.update_or_create(
            email=participant_email,
            defaults={
                'display_name': 'Sana (tm_07)',
                'is_site_admin': False,
            },
        )
        EventMembership.objects.update_or_create(
            event=event,
            user=participant_user,
            role=EventRole.PARTICIPANT,
        )
        part_token_hash = AuthToken.hash_token(SEED_TOKENS['participant'])
        AuthToken.objects.update_or_create(
            user=participant_user,
            label='seed:participant',
            defaults={
                'token_hash': part_token_hash,
                'expires_at': None,
            },
        )

        # Output the four lines for .dogfood.toml
        self.stdout.write(
            f"organizer: Authorization: Bearer {SEED_TOKENS['organizer']}"
        )
        self.stdout.write(
            f"judge_a: Authorization: Bearer {SEED_TOKENS['judge_a']}"
        )
        self.stdout.write(
            f"judge_b: Authorization: Bearer {SEED_TOKENS['judge_b']}"
        )
        self.stdout.write(
            f"participant: Authorization: Bearer {SEED_TOKENS['participant']}"
        )
