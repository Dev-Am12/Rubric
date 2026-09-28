from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import EventMembership, EventRole, User
from events.services import current_event
from services import audit


class Command(BaseCommand):
    help = "Bootstrap an organizer account for deployment."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="Organizer email address")
        parser.add_argument("--password", required=True, help="Organizer password")
        parser.add_argument("--name", default="", help="Organizer display name")

    def handle(self, *args, **options):
        email = options["email"].strip()
        password = options["password"]
        name = options["name"].strip() or email.split("@")[0]

        if not email or not password:
            raise CommandError("Both --email and --password are required.")

        with transaction.atomic():
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "display_name": name,
                    "is_site_admin": True,
                },
            )
            if not created:
                if name:
                    user.display_name = name
                user.is_site_admin = True
                user.set_password(password)
                user.save()
            else:
                user.set_password(password)
                user.save()

            # Ensure ORGANIZER membership for current event if present
            event = current_event()
            if event is not None:
                EventMembership.objects.update_or_create(
                    event=event,
                    user=user,
                    defaults={"role": EventRole.ORGANIZER},
                )

            # Audit log the bootstrapping (never log raw password)
            audit.record(
                user,
                "organizer.bootstrap",
                user,
                {
                    "email": user.email,
                    "created": created,
                    "is_site_admin": True,
                },
            )

        status_msg = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(f"{status_msg} organizer account for '{user.email}' (is_site_admin=True).")
        )
