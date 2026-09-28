"""
Tests for G5.8: Team invite links (T1) and judge invitation (T2).

Covers:
1. JudgeInvite model & service:
   - 32-byte URL-safe token, stored SHA-256 hash, 14-day expiry.
   - Audit-logged creation without leaking tokens.
   - Constant-time token verification.
2. Judge invitation rejection cases:
   - Expired tokens rejected.
   - Already-used tokens rejected.
   - Wrong-email user rejected with 403.
   - Tampered tokens rejected with 404.
   - Cross-event tokens rejected.
   - Non-invited user cannot self-promote.
3. Access control:
   - Anonymous (401), participants (403), and judges (403) blocked from /organizer/judges.
   - Organizer has access (200).
4. Full judge invitation lifecycle:
   - Invite created by organizer -> anon redirected to login/register -> registered with matching email ->
     accepts invite -> EventMembership(JUDGE) + JudgeTrackEligibility created -> accesses /judge/queue.
5. Team invite links:
   - /teams/new creates team, redirects to /teams/<id> showing invite link.
   - /teams/<id> shows invite link to members and organizers only; non-members cannot see it.
   - /teams/join/<code> redirects anonymous users to login with safe `next`.
   - /teams/join/<code> allows authenticated users to join team with audit log.
   - Joining when already a member is idempotent (redirects cleanly) and rejects duplicate DB membership.
"""

from datetime import timedelta
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.actors import Actor, PermissionDenied
from accounts.models import AuthToken, EventMembership, EventRole, JudgeTrackEligibility, User
from audit.models import AuditLogEntry
from events.models import Event, Track
from events import services as events_services
from importer.management.commands.seed_fixtures import SEED_TOKENS
from judging.models import JudgeInvite
from services import judging as judging_services
from teams.models import Team, TeamMembership
from teams import services as teams_services


class JudgeInviteServiceAndModelTests(TestCase):
    """
    Test JudgeInvite token generation, hashing, expiry, and audit logging.
    """

    def setUp(self):
        call_command('seed_fixtures')
        self.event = Event.objects.get(external_id='evt_01')
        self.org_user = User.objects.get(email='organizer@rubric.local')
        self.org_actor = Actor(self.org_user, self.event)
        self.tracks = list(self.event.tracks.all()[:2])

    def test_create_judge_invite_generates_valid_token_and_audit_log(self):
        now = timezone.now()
        invite, raw_token = judging_services.create_judge_invite(
            actor=self.org_actor,
            event=self.event,
            email='newjudge@example.org',
            track_ids=[t.pk for t in self.tracks],
        )

        # Token is non-empty and stored hashed
        self.assertTrue(len(raw_token) >= 32)
        self.assertNotEqual(invite.token_hash, raw_token)
        self.assertEqual(invite.token_hash, JudgeInvite.hash_token(raw_token))

        # 14-day expiry
        expected_expiry = now + timedelta(days=14)
        self.assertAlmostEqual(
            invite.expires_at.timestamp(),
            expected_expiry.timestamp(),
            delta=5,
        )
        self.assertFalse(invite.is_expired())
        self.assertFalse(invite.is_accepted())

        # Tracks assigned
        self.assertEqual(set(invite.tracks.all()), set(self.tracks))

        # Audit log written without token in payload
        entry = AuditLogEntry.objects.filter(
            action='judge.invite_created',
            target_id=str(invite.pk),
        ).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.payload['email'], 'newjudge@example.org')
        self.assertNotIn(raw_token, str(entry.payload))
        self.assertNotIn(invite.token_hash, str(entry.payload))

    def test_create_judge_invite_requires_organizer(self):
        part_user = User.objects.create_user(email='participant@test.org')
        part_actor = Actor(part_user, self.event)

        with self.assertRaises(PermissionDenied):
            judging_services.create_judge_invite(
                actor=part_actor,
                event=self.event,
                email='attempt@example.org',
            )

    def test_create_judge_invite_validates_email(self):
        with self.assertRaises(ValueError) as cm:
            judging_services.create_judge_invite(
                actor=self.org_actor,
                event=self.event,
                email='invalid-email-address',
            )
        self.assertIn("valid email", str(cm.exception).lower())


class JudgeInviteAcceptanceTests(TestCase):
    """
    Test rejection of expired, already-used, wrong-email, tampered,
    and cross-event invitations.
    """

    def setUp(self):
        call_command('seed_fixtures')
        self.event = Event.objects.get(external_id='evt_01')
        self.org_user = User.objects.get(email='organizer@rubric.local')
        self.org_actor = Actor(self.org_user, self.event)

        self.judge_email = 'invited.judge@example.org'
        self.invite, self.raw_token = judging_services.create_judge_invite(
            actor=self.org_actor,
            event=self.event,
            email=self.judge_email,
        )

        self.client = Client()

    def _auth(self, client, user):
        _, raw_token = AuthToken.create_token(user)
        client.cookies['session'] = raw_token
        return raw_token

    def test_expired_token_rejected(self):
        self.invite.expires_at = timezone.now() - timedelta(days=1)
        self.invite.save()

        # Direct service call
        user = User.objects.create_user(email=self.judge_email)
        actor = Actor(user, self.event)
        with self.assertRaises(ValueError) as cm:
            judging_services.accept_judge_invite(actor, self.raw_token)
        self.assertIn("expired", str(cm.exception).lower())

        # HTTP flow
        self._auth(self.client, user)
        resp = self.client.get(f'/invite/judge/{self.raw_token}')
        self.assertEqual(resp.status_code, 400)
        self.assertIn("expired", resp.content.decode().lower())

    def test_already_used_token_rejected(self):
        self.invite.accepted_at = timezone.now() - timedelta(hours=2)
        self.invite.save()

        user = User.objects.create_user(email=self.judge_email)
        actor = Actor(user, self.event)
        with self.assertRaises(ValueError) as cm:
            judging_services.accept_judge_invite(actor, self.raw_token)
        self.assertIn("already been accepted", str(cm.exception).lower())

        self._auth(self.client, user)
        resp = self.client.get(f'/invite/judge/{self.raw_token}')
        self.assertEqual(resp.status_code, 400)
        self.assertIn("already accepted", resp.content.decode().lower())

    def test_wrong_email_rejected_with_403(self):
        wrong_user = User.objects.create_user(email='other.person@example.org')
        actor = Actor(wrong_user, self.event)

        # Direct service call
        with self.assertRaises(PermissionDenied):
            judging_services.accept_judge_invite(actor, self.raw_token)

        # HTTP flow
        self._auth(self.client, wrong_user)
        resp = self.client.get(f'/invite/judge/{self.raw_token}')
        self.assertEqual(resp.status_code, 403)
        self.assertIn("email mismatch", resp.content.decode().lower())

    def test_tampered_token_rejected_with_404(self):
        tampered_token = self.raw_token[:-4] + "xxxx"
        user = User.objects.create_user(email=self.judge_email)

        self._auth(self.client, user)
        resp = self.client.get(f'/invite/judge/{tampered_token}')
        self.assertEqual(resp.status_code, 404)

    def test_cross_event_token_rejected(self):
        # Create second event and switch active event to it
        now = timezone.now()
        second_event = events_services.create_event(
            self.org_actor,
            name="Second Event",
            slug="second-event",
            submissions_open_at=now,
            submissions_close_at=now + timedelta(days=5),
        )
        events_services.set_current_event(self.org_actor, second_event)

        # Try to accept invite that was created for evt_01
        user = User.objects.create_user(email=self.judge_email)
        self._auth(self.client, user)
        resp = self.client.get(f'/invite/judge/{self.raw_token}')
        self.assertEqual(resp.status_code, 400)
        self.assertIn("cross-event", resp.content.decode().lower())

    def test_non_invited_cannot_self_promote(self):
        # User tries to access judge queue without having accepted an invite
        user = User.objects.create_user(email='wannabe.judge@example.org')
        self._auth(self.client, user)

        resp = self.client.get('/judge/queue')
        self.assertEqual(resp.status_code, 403)


class OrganizerJudgesPageAccessControlTests(TestCase):
    """
    Test /organizer/judges access control.
    """

    def setUp(self):
        call_command('seed_fixtures')
        self.client = Client()

    def test_organizer_judges_access_matrix(self):
        # 1. Anonymous -> 401
        resp = self.client.get('/organizer/judges')
        self.assertEqual(resp.status_code, 401)

        # 2. Participant -> 403
        resp = self.client.get(
            '/organizer/judges',
            HTTP_AUTHORIZATION=f"Bearer {SEED_TOKENS['participant']}",
        )
        self.assertEqual(resp.status_code, 403)

        # 3. Judge -> 403
        resp = self.client.get(
            '/organizer/judges',
            HTTP_AUTHORIZATION=f"Bearer {SEED_TOKENS['judge_a']}",
        )
        self.assertEqual(resp.status_code, 403)

        # 4. Organizer -> 200
        resp = self.client.get(
            '/organizer/judges',
            HTTP_AUTHORIZATION=f"Bearer {SEED_TOKENS['organizer']}",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Judge Management", resp.content.decode())


class FullJudgeInvitationFlowIntegrationTests(TestCase):
    """
    Test the full lifecycle:
    Organizer invites judge -> Link generated once ->
    Anon opens link (redirected to login/register) ->
    User registers with matching email ->
    Visits invite link -> accepted ->
    Enrolled as JUDGE with track eligibilities ->
    Reaches /judge/queue.
    """

    def setUp(self):
        call_command('seed_fixtures')
        self.event = Event.objects.get(external_id='evt_01')
        self.tracks = list(self.event.tracks.all()[:2])
        self.org_token = SEED_TOKENS['organizer']
        self.client = Client()

    def test_full_invite_register_accept_queue_lifecycle(self):
        new_email = 'dr.smith@university.edu'

        # 1. Organizer generates invite link via POST /organizer/judges
        resp = self.client.post(
            '/organizer/judges',
            {
                'email': new_email,
                'tracks': [t.pk for t in self.tracks],
            },
            HTTP_AUTHORIZATION=f'Bearer {self.org_token}',
        )
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("Judge Invite Link Generated", content)
        self.assertIn(new_email, content)

        # Extract token from the single JudgeInvite record created
        invite = JudgeInvite.objects.get(email=new_email)
        self.assertFalse(invite.is_accepted())

        # Retrieve raw token from test database query
        # Since hash is stored, we look up the raw token from the HTML input field
        import re
        match = re.search(r'/invite/judge/([A-Za-z0-9_-]+)', content)
        self.assertIsNotNone(match)
        raw_token = match.group(1)

        # 2. Anonymous client tries to access invite link -> redirected to login
        anon_client = Client()
        resp_anon = anon_client.get(f'/invite/judge/{raw_token}')
        self.assertEqual(resp_anon.status_code, 302)
        self.assertIn(f'/login?next=/invite/judge/{raw_token}', resp_anon.url)

        # 3. User registers with the invited email address
        reg_resp = anon_client.post(
            '/accounts/register',
            {
                'email': new_email,
                'display_name': 'Dr. Smith',
                'password': 'StrongPassword2026!',
            },
        )
        self.assertEqual(reg_resp.status_code, 302)

        # 4. Now authenticated as new_email, visits the invite link
        accept_resp = anon_client.get(f'/invite/judge/{raw_token}')
        self.assertEqual(accept_resp.status_code, 302)
        self.assertEqual(accept_resp.url, '/judge/queue?accepted=1')

        # 5. Verify database state
        user = User.objects.get(email=new_email)
        invite.refresh_from_db()
        self.assertTrue(invite.is_accepted())

        membership = EventMembership.objects.get(
            event=self.event,
            user=user,
            role=EventRole.JUDGE,
        )
        self.assertIsNotNone(membership)

        # Verify track eligibilities
        eligibilities = JudgeTrackEligibility.objects.filter(event_membership=membership)
        self.assertEqual(eligibilities.count(), 2)
        self.assertEqual(
            set(eligibilities.values_list('track_id', flat=True)),
            {t.pk for t in self.tracks},
        )

        # 6. Verify judge queue is accessible
        queue_resp = anon_client.get('/judge/queue')
        self.assertEqual(queue_resp.status_code, 200)


class TeamInviteAndJoinFlowTests(TestCase):
    """
    Test team creation, members-only invite link display, and joining by code.
    """

    def setUp(self):
        call_command('seed_fixtures')
        self.event = Event.objects.get(external_id='evt_01')

        self.creator = User.objects.create_user(email='creator@team.test', display_name='Team Creator')
        self.joiner = User.objects.create_user(email='joiner@team.test', display_name='Team Joiner')
        self.outsider = User.objects.create_user(email='outsider@team.test', display_name='Outsider')

        self.client = Client()

    def _auth(self, client, user):
        _, raw_token = AuthToken.create_token(user)
        client.cookies['session'] = raw_token
        return raw_token

    def test_team_create_shows_invite_link_on_detail(self):
        self._auth(self.client, self.creator)

        # POST to /teams/new
        resp = self.client.post('/teams/new', {'name': 'Quantum Coders'})
        self.assertEqual(resp.status_code, 302)

        team = Team.objects.get(name='Quantum Coders')
        self.assertIn(f'/teams/{team.id}?created=1', resp.url)

        # Follow redirect to /teams/<id>
        resp_detail = self.client.get(f'/teams/{team.id}')
        self.assertEqual(resp_detail.status_code, 200)
        content = resp_detail.content.decode()
        self.assertIn('Quantum Coders', content)
        self.assertIn(f'/teams/join/{team.invite_code}', content)

    def test_invite_link_visible_to_members_and_organizers_only(self):
        team = teams_services.create_team(
            actor=Actor(self.creator, self.event),
            event=self.event,
            name='Secret Society',
        )

        # 1. Creator (member) can see invite link
        c_creator = Client()
        self._auth(c_creator, self.creator)
        resp_creator = c_creator.get(f'/teams/{team.id}')
        self.assertIn(team.invite_code, resp_creator.content.decode())

        # 2. Outsider (non-member participant) CANNOT see invite link
        c_outsider = Client()
        self._auth(c_outsider, self.outsider)
        resp_outsider = c_outsider.get(f'/teams/{team.id}')
        self.assertNotIn(team.invite_code, resp_outsider.content.decode())

        # 3. Anonymous viewer CANNOT see invite link
        anon_client = Client()
        resp_anon = anon_client.get(f'/teams/{team.id}')
        self.assertNotIn(team.invite_code, resp_anon.content.decode())

        # 4. Organizer CAN see invite link (for administration)
        org_user = User.objects.get(email='organizer@rubric.local')
        c_org = Client()
        self._auth(c_org, org_user)
        resp_org = c_org.get(f'/teams/{team.id}')
        self.assertIn(team.invite_code, resp_org.content.decode())

    def test_team_join_anonymous_redirects_with_safe_next(self):
        team = teams_services.create_team(
            actor=Actor(self.creator, self.event),
            event=self.event,
            name='Alpha Team',
        )

        anon_client = Client()
        resp = anon_client.get(f'/teams/join/{team.invite_code}')
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f'/login?next=/teams/join/{team.invite_code}', resp.url)

    def test_team_join_authenticated_success(self):
        team = teams_services.create_team(
            actor=Actor(self.creator, self.event),
            event=self.event,
            name='Beta Team',
        )

        c_joiner = Client()
        self._auth(c_joiner, self.joiner)
        resp = c_joiner.get(f'/teams/join/{team.invite_code}')
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f'/teams/{team.id}?joined=1', resp.url)

        # Check TeamMembership and EventMembership
        self.assertTrue(TeamMembership.objects.filter(team=team, user=self.joiner).exists())
        self.assertTrue(
            EventMembership.objects.filter(event=self.event, user=self.joiner, role=EventRole.PARTICIPANT).exists()
        )

        # Check audit log entry
        audit_entry = AuditLogEntry.objects.filter(action='team.join', target_id=str(team.id)).first()
        self.assertIsNotNone(audit_entry)
        self.assertEqual(audit_entry.payload['user_id'], self.joiner.pk)

    def test_team_join_idempotent_and_rejects_duplicate_membership(self):
        team = teams_services.create_team(
            actor=Actor(self.creator, self.event),
            event=self.event,
            name='Gamma Team',
        )

        # Joiner joins once
        c_joiner = Client()
        self._auth(c_joiner, self.joiner)
        resp1 = c_joiner.get(f'/teams/join/{team.invite_code}')
        self.assertEqual(resp1.status_code, 302)

        # Joiner clicks invite link second time -> idempotent redirect
        resp2 = c_joiner.get(f'/teams/join/{team.invite_code}')
        self.assertEqual(resp2.status_code, 302)
        self.assertIn(f'/teams/{team.id}?already_member=1', resp2.url)

        # Exactly 1 membership row exists
        self.assertEqual(
            TeamMembership.objects.filter(team=team, user=self.joiner).count(),
            1,
        )

        # Direct service call rejects duplicate membership with ValueError
        actor = Actor(self.joiner, self.event)
        with self.assertRaises(ValueError) as cm:
            teams_services.join_by_code(actor, team.invite_code)
        self.assertIn("already a member", str(cm.exception).lower())
