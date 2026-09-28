from django.shortcuts import render
from django.utils import timezone
from events.services import current_event


def landing_page_view(request):
    """
    Public landing page (/).
    Displays current event name, dates, tracks, prizes, open/closed status,
    and links to gallery, register, and login.
    """
    event = current_event()
    now = timezone.now()

    submissions_status = "Not Scheduled"
    submissions_open = False
    voting_status = "Not Scheduled"
    voting_open = False
    tracks = []
    prizes = []

    if event is not None:
        tracks = list(event.tracks.all().order_by("name"))
        prizes = list(event.prizes.all().order_by("id"))

        # Submissions status
        if event.submissions_close_at and now > event.submissions_close_at:
            submissions_status = "Closed"
            submissions_open = False
        elif event.submissions_open_at and now < event.submissions_open_at:
            submissions_status = "Opens Soon"
            submissions_open = False
        elif event.submissions_close_at:
            submissions_status = "Open"
            submissions_open = True

        # Voting status
        if event.voting_closes_at and now > event.voting_closes_at:
            voting_status = "Closed"
            voting_open = False
        elif event.voting_opens_at and now < event.voting_opens_at:
            voting_status = "Opens Soon"
            voting_open = False
        elif event.voting_opens_at and (not event.voting_closes_at or now <= event.voting_closes_at):
            voting_status = "Open"
            voting_open = True

    context = {
        "event": event,
        "tracks": tracks,
        "prizes": prizes,
        "submissions_status": submissions_status,
        "submissions_open": submissions_open,
        "voting_status": voting_status,
        "voting_open": voting_open,
        "actor": request.actor,
    }
    return render(request, "landing.html", context)
