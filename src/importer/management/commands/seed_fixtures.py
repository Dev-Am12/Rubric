"""
Full fixture importer — idempotent by external_id throughout.

Imports:
  1. Event + Tracks (existing from G0)
  2. All 30 judges → User + EventMembership(JUDGE) + JudgeTrackEligibility
  3. All 40 teams → Team + TeamMembership
  4. All 41 projects → Project (with corrected is_duplicate_of direction)
  5. Four persona AuthTokens (organizer, judge_a, judge_b, participant)

Design reference:
  - SCHEMA.md §2 (fixture→schema mapping)
  - SCHEMA.md §1.1 (is_duplicate_of: prj_07 → prj_41, the EARLIER flags
    itself against the LATER canonical one; NORMALIZATION.md D-02)

Note: scores[] import is deferred to G3 (requires Rubric/Ballot/BallotScore
models from judging app). AuditLogEntry is G5 scope; duplicate flagging is
logged via Python's logging module for now.
"""

import json
import logging
import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify

from accounts.models import (
    AuthToken, EventMembership, EventRole, JudgeTrackEligibility, User,
)
from events.models import Event, Track
from submissions.models import Project, ProjectStatus
from teams.models import Team, TeamMembership
from judging.models import Rubric, RubricCriterion, JudgeAssignment, AssignmentStatus, Ballot, BallotScore

logger = logging.getLogger('importer.seed_fixtures')

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
    help = (
        "Seed the full fixture dataset (Event, Tracks, Judges, Teams, "
        "Projects, D-11 personas) from fixtures.json — idempotent by "
        "external_id throughout."
    )

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

        with transaction.atomic():
            event = self._import_event(data)
            track_map = self._import_tracks(data, event)
            self._import_organizer(event)
            self._import_judges(data, event, track_map)
            team_map = self._import_teams(data, event)
            self._import_projects(data, event, track_map, team_map)
            rubric = self._import_rubric(event)
            self._import_scores(data, event, rubric)
            self._import_persona_tokens(data, event)

        self._print_seed_tokens()

    # ------------------------------------------------------------------
    # Event + Tracks
    # ------------------------------------------------------------------

    def _import_event(self, data):
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

        # We need the organizer user for created_by — get or create first
        organizer_user, _ = User.objects.update_or_create(
            email='organizer@rubric.local',
            defaults={
                'display_name': 'Organizer',
                'is_site_admin': True,
            },
        )

        event, created = Event.objects.update_or_create(
            external_id=evt_id,
            defaults={
                'name': evt_name,
                'slug': slug,
                'submissions_close_at': submissions_close_at,
                'created_by': organizer_user,
            },
        )
        action = 'created' if created else 'updated'
        self.stdout.write(f"  Event '{evt_name}' ({evt_id}) {action}")
        return event

    def _import_tracks(self, data, event):
        """Import tracks, return {external_id: Track} map."""
        track_map = {}
        for t in data.get('tracks', []):
            track, _ = Track.objects.update_or_create(
                external_id=t['id'],
                defaults={
                    'name': t['name'],
                    'event': event,
                },
            )
            track_map[t['id']] = track
        self.stdout.write(f"  Tracks: {len(track_map)} imported")
        return track_map

    def _import_rubric(self, event):
        rubric, _ = Rubric.objects.update_or_create(
            event=event, name='Default Rubric', defaults={},
        )
        for order, name in enumerate(('functionality', 'quality', 'innovation')):
            RubricCriterion.objects.update_or_create(
                rubric=rubric, name=name,
                defaults={'weight': 1, 'max_score': 5, 'order': order},
            )
        return rubric

    def _import_scores(self, data, event, rubric):
        """Import fixture scores; submitted_at records import provenance only."""
        imported_at = timezone.now()
        users = {u.external_id: u for u in User.objects.filter(external_id__isnull=False)}
        projects = {p.external_id: p for p in Project.objects.filter(event=event)}
        criteria = {c.name: c for c in RubricCriterion.objects.filter(rubric=rubric)}
        scores = data.get('scores', [])
        for row in scores:
            judge = users[row['judge']]
            project = projects[row['project']]
            assignment, _ = JudgeAssignment.objects.update_or_create(
                judge=judge, project=project,
                defaults={'event': event, 'status': AssignmentStatus.COMPLETED},
            )
            ballot, _ = Ballot.objects.update_or_create(
                assignment=assignment,
                defaults={'comment': row.get('comment') or '', 'is_complete': True,
                          'submitted_at': imported_at},
            )
            for name, value in row.get('criteria', {}).items():
                criterion = criteria[name]
                BallotScore.objects.update_or_create(
                    ballot=ballot, criterion=criterion,
                    defaults={'value': value},
                )
        self.stdout.write(f"  Scores: {len(scores)} imported")

    # ------------------------------------------------------------------
    # Organizer (dedicated seed account)
    # ------------------------------------------------------------------

    def _import_organizer(self, event):
        organizer_user, _ = User.objects.update_or_create(
            email='organizer@rubric.local',
            defaults={
                'display_name': 'Organizer',
                'is_site_admin': True,
            },
        )
        EventMembership.objects.update_or_create(
            event=event,
            user=organizer_user,
            role=EventRole.ORGANIZER,
        )
        self._upsert_token(organizer_user, 'seed:organizer', SEED_TOKENS['organizer'])

    # ------------------------------------------------------------------
    # Judges (all 30)
    # ------------------------------------------------------------------

    def _import_judges(self, data, event, track_map):
        judges = data.get('judges', [])
        for j in judges:
            user, _ = User.objects.update_or_create(
                external_id=j['id'],
                defaults={
                    'email': j['email'],
                    'display_name': j['name'],
                    'is_site_admin': False,
                },
            )
            membership, _ = EventMembership.objects.update_or_create(
                event=event,
                user=user,
                role=EventRole.JUDGE,
            )

            # JudgeTrackEligibility — one row per track in judges[].tracks
            for track_ext_id in j.get('tracks', []):
                track = track_map.get(track_ext_id)
                if track:
                    JudgeTrackEligibility.objects.get_or_create(
                        event_membership=membership,
                        track=track,
                    )

        self.stdout.write(f"  Judges: {len(judges)} imported")

    # ------------------------------------------------------------------
    # Teams (all 40)
    # ------------------------------------------------------------------

    def _import_teams(self, data, event):
        """Import teams and their members. Returns {external_id: Team} map."""
        teams = data.get('teams', [])
        team_map = {}

        for t in teams:
            # Generate a deterministic invite code from the external_id
            # so re-runs produce the same code
            invite_code = f"invite-{t['id']}"

            team, _ = Team.objects.update_or_create(
                external_id=t['id'],
                defaults={
                    'name': t['name'],
                    'event': event,
                    'invite_code': invite_code,
                },
            )
            team_map[t['id']] = team

            # Members — emails → get-or-create User + TeamMembership +
            # EventMembership(PARTICIPANT)
            for member_email in t.get('members', []):
                user, _ = User.objects.get_or_create(
                    email=member_email,
                    defaults={
                        'display_name': member_email.split('@')[0],
                        'is_site_admin': False,
                    },
                )
                TeamMembership.objects.get_or_create(
                    team=team,
                    user=user,
                )
                EventMembership.objects.get_or_create(
                    event=event,
                    user=user,
                    role=EventRole.PARTICIPANT,
                )

        self.stdout.write(f"  Teams: {len(teams)} imported")
        return team_map

    # ------------------------------------------------------------------
    # Projects (all 41, with corrected duplicate direction)
    # ------------------------------------------------------------------

    def _import_projects(self, data, event, track_map, team_map):
        projects = data.get('projects', [])

        # First pass: create/update all projects without is_duplicate_of
        for p in projects:
            track = track_map.get(p['track'])
            team = team_map.get(p['team'])

            submitted_at = parse_datetime(p.get('submitted_at', ''))
            if submitted_at and timezone.is_naive(submitted_at):
                submitted_at = timezone.make_aware(
                    submitted_at, timezone=timezone.utc
                )

            Project.objects.update_or_create(
                external_id=p['id'],
                defaults={
                    'event': event,
                    'team': team,
                    'track': track,
                    'title': p['title'],
                    'summary': p.get('summary', ''),
                    'description': p.get('description', ''),
                    'repo_url': p.get('repo_url', ''),
                    'demo_video_url': p.get('demo_video_url', ''),
                    'live_url': p.get('live_url', ''),
                    'tech_tags': p.get('tech_tags', []),
                    'status': ProjectStatus.SUBMITTED,
                    'submitted_at': submitted_at,
                },
            )

        # Second pass: detect and flag duplicate submissions per NORMALIZATION.md D-02
        # (general duplicate detector replaces hardcoded prj_07/prj_41 assignment)
        from submissions.services import detect_duplicates_for_event
        flagged = detect_duplicates_for_event(event)
        for earlier in flagged:
            logger.info(
                "Duplicate flag set: %s.is_duplicate_of = %s (per D-02). Reason: %s",
                earlier.external_id or earlier.id,
                earlier.is_duplicate_of.external_id or earlier.is_duplicate_of.id,
                earlier.duplicate_flag_reason,
            )

        self.stdout.write(f"  Projects: {len(projects)} imported")

    # ------------------------------------------------------------------
    # Persona tokens (the four from .dogfood.toml)
    # ------------------------------------------------------------------

    def _import_persona_tokens(self, data, event):
        """
        Ensure the four D-11 persona tokens exist.
        Does not recreate users — they should already exist from the
        judge/team/organizer import above.
        """
        # judge_a → jdg_07
        judge_a = User.objects.get(external_id='jdg_07')
        self._upsert_token(judge_a, 'seed:judge_a', SEED_TOKENS['judge_a'])

        # judge_b → jdg_29
        judge_b = User.objects.get(external_id='jdg_29')
        self._upsert_token(judge_b, 'seed:judge_b', SEED_TOKENS['judge_b'])

        # participant → first member of tm_07
        tm_07 = data.get('teams', [])
        tm_07_info = next((t for t in tm_07 if t.get('id') == 'tm_07'), None)
        if tm_07_info and tm_07_info.get('members'):
            participant_email = tm_07_info['members'][0]
            participant_user = User.objects.get(email=participant_email)
            self._upsert_token(
                participant_user, 'seed:participant',
                SEED_TOKENS['participant'],
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _upsert_token(self, user, label, raw_token):
        """Create or update an AuthToken for the user."""
        token_hash = AuthToken.hash_token(raw_token)
        AuthToken.objects.update_or_create(
            user=user,
            label=label,
            defaults={
                'token_hash': token_hash,
                'expires_at': None,
            },
        )

    def _print_seed_tokens(self):
        self.stdout.write("")
        self.stdout.write("seeded. test logins:")
        self.stdout.write(
            f"  organizer: Authorization: Bearer {SEED_TOKENS['organizer']}"
        )
        self.stdout.write(
            f"  judge_a:   Authorization: Bearer {SEED_TOKENS['judge_a']}"
        )
        self.stdout.write(
            f"  judge_b:   Authorization: Bearer {SEED_TOKENS['judge_b']}"
        )
        self.stdout.write(
            f"  participant: Authorization: Bearer {SEED_TOKENS['participant']}"
        )
