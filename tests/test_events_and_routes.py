"""
Tests for G1 Step 2:
  1. P-11 route name resolution via reverse() (.dogfood.toml)
  2. Placeholder view responses (200 OK)
  3. events.Prize model fields and relationships
  4. events service layer: create_event, create_track, create_prize, get_event
     (organizer-only enforcement via require(), public read for get_event)
"""

from datetime import timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from accounts.actors import Actor, AnonymousActor, PermissionDenied
from accounts.models import EventMembership, EventRole, User
from events.models import Event, Track, Prize
from events.services import (
    create_event,
    create_track,
    create_prize,
    get_event,
)
import services.events  # Verify domain package import works too


class P11RouteResolutionTest(TestCase):
    """
    Verify all five P-11 route names resolve to the exact paths declared in
    .dogfood.toml:
      - gallery      -> /projects
      - submit       -> /projects/new
      - judge_scores -> /api/judge/scores
      - csv_export   -> /api/export.csv

    This prevents any future refactor from silently renaming these routes.
    """

    def test_gallery_route_resolves(self):
        self.assertEqual(reverse('gallery'), '/projects')

    def test_submit_route_resolves(self):
        self.assertEqual(reverse('submit'), '/projects/new')

    def test_judge_scores_route_resolves(self):
        self.assertEqual(reverse('judge_scores'), '/api/judge/scores')

    def test_csv_export_route_resolves(self):
        self.assertEqual(reverse('csv_export'), '/api/export.csv')

    def test_p11_routes_are_reachable(self):
        """Public routes respond; protected routes reject anonymous callers."""
        client = Client()

        resp = client.get(reverse('gallery'))
        self.assertEqual(resp.status_code, 200)

        resp = client.get(reverse('submit'))
        self.assertEqual(resp.status_code, 200)

        resp = client.get(reverse('judge_scores'))
        self.assertEqual(resp.status_code, 401)

        # Peer score access is the same URL with an optional ?judge= parameter.
        resp = client.get(reverse('judge_scores') + '?judge=jdg_07')
        self.assertEqual(resp.status_code, 401)

        # In G4, csv_export is real and organizer-only (rejects anonymous with 401)
        resp = client.get(reverse('csv_export'))
        self.assertEqual(resp.status_code, 401)



class PrizeModelTest(TestCase):
    """
    Verify events.Prize model:
      id, event (FK), rank_label, description.
    """

    def setUp(self):
        self.event = Event.objects.create(
            slug='hackathon-2026',
            name='Hackathon 2026',
            submissions_close_at=timezone.now() + timedelta(days=7),
        )

    def test_create_prize(self):
        prize = Prize.objects.create(
            event=self.event,
            rank_label='1st Place',
            description='Overall winner of Hackathon 2026',
        )
        self.assertIsNotNone(prize.id)
        self.assertEqual(prize.event, self.event)
        self.assertEqual(prize.rank_label, '1st Place')
        self.assertEqual(prize.description, 'Overall winner of Hackathon 2026')
        self.assertIn('1st Place', str(prize))
        self.assertIn('hackathon-2026', str(prize))

    def test_prize_relationship_to_event(self):
        Prize.objects.create(event=self.event, rank_label='1st', description='Gold')
        Prize.objects.create(event=self.event, rank_label='2nd', description='Silver')
        self.assertEqual(self.event.prizes.count(), 2)


class EventsServiceTest(TestCase):
    """
    Verify services/events.py service-layer functions:
      - create_event (organizer-only via require())
      - create_track (organizer-only via require())
      - create_prize (organizer-only via require())
      - get_event (public read)
    """

    def setUp(self):
        # Create users for each persona
        self.organizer_user = User.objects.create_user(
            email='organizer@example.org', display_name='Organizer User',
        )
        self.participant_user = User.objects.create_user(
            email='participant@example.org', display_name='Participant User',
        )
        self.judge_user = User.objects.create_user(
            email='judge@example.org', display_name='Judge User',
        )
        self.site_admin_user = User.objects.create_user(
            email='admin@example.org', display_name='Site Admin',
            is_site_admin=True,
        )

        # Baseline event
        self.event = Event.objects.create(
            slug='base-event',
            name='Base Event',
            submissions_close_at=timezone.now() + timedelta(days=14),
        )

        # Memberships
        EventMembership.objects.create(
            event=self.event, user=self.organizer_user, role=EventRole.ORGANIZER,
        )
        EventMembership.objects.create(
            event=self.event, user=self.participant_user, role=EventRole.PARTICIPANT,
        )
        EventMembership.objects.create(
            event=self.event, user=self.judge_user, role=EventRole.JUDGE,
        )

        # Actors
        self.organizer_actor = Actor(user=self.organizer_user, event=self.event)
        self.participant_actor = Actor(user=self.participant_user, event=self.event)
        self.judge_actor = Actor(user=self.judge_user, event=self.event)
        self.admin_actor = Actor(user=self.site_admin_user, event=self.event)
        self.anon_actor = AnonymousActor()

    def test_get_event_public_read(self):
        """get_event(slug) works without any auth required."""
        evt = get_event('base-event')
        self.assertEqual(evt.id, self.event.id)
        self.assertEqual(evt.name, 'Base Event')

        # Also via services.events entrypoint
        evt_via_pkg = services.events.get_event('base-event')
        self.assertEqual(evt_via_pkg.id, self.event.id)

    def test_create_event_by_organizer(self):
        """Organizer can create an event via service layer."""
        new_event = create_event(
            self.organizer_actor,
            name='Winter Hack',
            slug='winter-hack',
            submissions_close_at=timezone.now() + timedelta(days=20),
        )
        self.assertEqual(new_event.slug, 'winter-hack')
        self.assertEqual(new_event.created_by, self.organizer_user)
        # EventMembership with ORGANIZER was created
        membership = EventMembership.objects.get(
            event=new_event, user=self.organizer_user, role=EventRole.ORGANIZER,
        )
        self.assertIsNotNone(membership)

    def test_create_event_by_site_admin(self):
        """Site admin has is_organizer=True and can create events."""
        new_event = create_event(
            self.admin_actor,
            name='Admin Event',
            slug='admin-event',
        )
        self.assertEqual(new_event.name, 'Admin Event')

    def test_create_event_forbidden_for_participant(self):
        """Participant cannot create an event (raises PermissionDenied)."""
        with self.assertRaises(PermissionDenied):
            create_event(
                self.participant_actor,
                name='Illegal Event',
                slug='illegal-event',
            )

    def test_create_event_forbidden_for_judge(self):
        """Judge cannot create an event (raises PermissionDenied)."""
        with self.assertRaises(PermissionDenied):
            create_event(
                self.judge_actor,
                name='Illegal Event',
                slug='illegal-event',
            )

    def test_create_event_forbidden_for_anonymous(self):
        """Anonymous actor cannot create an event (raises PermissionDenied)."""
        with self.assertRaises(PermissionDenied):
            create_event(
                self.anon_actor,
                name='Illegal Event',
                slug='illegal-event',
            )

    def test_create_track_by_organizer(self):
        """Organizer can create a track for an event."""
        track = create_track(
            self.organizer_actor,
            event=self.event,
            name='FinTech Track',
            external_id='trk_fintech',
        )
        self.assertEqual(track.name, 'FinTech Track')
        self.assertEqual(track.event, self.event)
        self.assertEqual(track.external_id, 'trk_fintech')

    def test_create_track_forbidden_for_participant(self):
        """Participant cannot create a track (raises PermissionDenied)."""
        with self.assertRaises(PermissionDenied):
            create_track(
                self.participant_actor,
                event=self.event,
                name='Illegal Track',
            )

    def test_create_track_forbidden_for_anonymous(self):
        """Anonymous actor cannot create a track (raises PermissionDenied)."""
        with self.assertRaises(PermissionDenied):
            create_track(
                self.anon_actor,
                event=self.event,
                name='Illegal Track',
            )

    def test_create_prize_by_organizer(self):
        """Organizer can create a prize for an event."""
        prize = create_prize(
            self.organizer_actor,
            event=self.event,
            rank_label='Best AI App',
            description='Most innovative AI implementation',
        )
        self.assertEqual(prize.rank_label, 'Best AI App')
        self.assertEqual(prize.event, self.event)
        self.assertEqual(prize.description, 'Most innovative AI implementation')

    def test_create_prize_forbidden_for_judge(self):
        """Judge cannot create a prize (raises PermissionDenied)."""
        with self.assertRaises(PermissionDenied):
            create_prize(
                self.judge_actor,
                event=self.event,
                rank_label='Illegal Prize',
            )

    def test_create_prize_forbidden_for_anonymous(self):
        """Anonymous actor cannot create a prize (raises PermissionDenied)."""
        with self.assertRaises(PermissionDenied):
            create_prize(
                self.anon_actor,
                event=self.event,
                rank_label='Illegal Prize',
            )
