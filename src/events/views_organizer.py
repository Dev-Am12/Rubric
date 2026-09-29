from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from accounts.actors import require
from events.models import Event, Track, Prize
from events import services as events_services
from services import voting as voting_services


def _check_organizer(actor):
    require(actor, actor.is_organizer or getattr(actor, 'is_site_admin', False))


@require_http_methods(["GET", "POST"])
def organizer_events_view(request):
    """
    Organizer events management dashboard (/organizer/events).
    GET: List all events with status, dates, and tracks/prizes counts.
    POST: Create a new event.
    """
    _check_organizer(request.actor)

    error_message = None
    success_message = None

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        slug = request.POST.get("slug", "").strip() or None
        submissions_open_at = request.POST.get("submissions_open_at", "").strip() or None
        submissions_close_at = request.POST.get("submissions_close_at", "").strip() or None
        voting_opens_at = request.POST.get("voting_opens_at", "").strip() or None
        voting_closes_at = request.POST.get("voting_closes_at", "").strip() or None

        try:
            event = events_services.create_event(
                request.actor,
                name=name,
                slug=slug,
                submissions_open_at=submissions_open_at,
                submissions_close_at=submissions_close_at,
                voting_opens_at=voting_opens_at,
                voting_closes_at=voting_closes_at,
            )
            return redirect(f"{reverse('organizer_events')}?created={event.slug}")
        except ValueError as exc:
            error_message = str(exc)

    if request.GET.get("created"):
        success_message = f"Event '{request.GET.get('created')}' created successfully. Note: It is not current by default."
    elif request.GET.get("updated"):
        success_message = f"Event '{request.GET.get('updated')}' updated successfully."
    elif request.GET.get("switched"):
        success_message = f"Active event successfully switched to '{request.GET.get('switched')}'. The entire portal is now scoped to this event."

    events = Event.objects.prefetch_related('tracks', 'prizes').order_by('-is_current', '-id')

    return render(request, "organizer/events_list.html", {
        "events": events,
        "error_message": error_message,
        "success_message": success_message,
    })


@require_http_methods(["GET", "POST"])
def organizer_event_dates_view(request, event_id):
    """
    Edit event name and dates (/organizer/events/<int:event_id>/dates).
    Validates close > open and rejects naive datetimes.
    """
    _check_organizer(request.actor)
    event = get_object_or_404(Event, pk=event_id)

    error_message = None

    if request.method == "POST":
        name = request.POST.get("name", "").strip() or None
        slug = request.POST.get("slug", "").strip() or None
        sub_open = request.POST.get("submissions_open_at", "").strip() or None
        sub_close = request.POST.get("submissions_close_at", "").strip() or None
        vote_open = request.POST.get("voting_opens_at", "").strip() or None
        vote_close = request.POST.get("voting_closes_at", "").strip() or None
        voting_access = request.POST.get("voting_access", "OPEN").strip().upper()
        votes_per_voter = request.POST.get("votes_per_voter", "").strip() or None

        try:
            events_services.update_event(
                request.actor,
                event,
                name=name,
                slug=slug,
                submissions_open_at=sub_open,
                submissions_close_at=sub_close,
                voting_opens_at=vote_open,
                voting_closes_at=vote_close,
                voting_access=voting_access,
                votes_per_voter=votes_per_voter,
            )
            return redirect(f"{reverse('organizer_events')}?updated={event.slug}")
        except ValueError as exc:
            error_message = str(exc)

    return render(request, "organizer/event_dates.html", {
        "event": event,
        "error_message": error_message,
    })


@require_POST
def organizer_open_voting_now_view(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    voting_services.open_voting_now(request.actor, event)
    return redirect('organizer_event_dates', event_id=event.pk)


@require_POST
def organizer_close_voting_now_view(request, event_id):
    event = get_object_or_404(Event, pk=event_id)
    voting_services.close_voting_now(request.actor, event)
    return redirect('organizer_event_dates', event_id=event.pk)


@require_http_methods(["GET", "POST"])
def organizer_event_tracks_view(request, event_id):
    """
    List and add tracks for an event (/organizer/events/<int:event_id>/tracks).
    """
    _check_organizer(request.actor)
    event = get_object_or_404(Event, pk=event_id)

    error_message = None

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        external_id = request.POST.get("external_id", "").strip() or None

        try:
            events_services.create_track(
                request.actor,
                event=event,
                name=name,
                external_id=external_id,
            )
            return redirect(reverse('organizer_event_tracks', args=[event.pk]))
        except ValueError as exc:
            error_message = str(exc)

    tracks = event.tracks.all().order_by('name')

    return render(request, "organizer/event_tracks.html", {
        "event": event,
        "tracks": tracks,
        "error_message": error_message,
    })


@require_POST
def organizer_event_track_edit_view(request, event_id, track_id):
    """
    Edit an existing track (/organizer/events/<int:event_id>/tracks/<int:track_id>).
    """
    _check_organizer(request.actor)
    event = get_object_or_404(Event, pk=event_id)
    track = get_object_or_404(Track, pk=track_id, event=event)

    name = request.POST.get("name", "").strip() or None
    external_id = request.POST.get("external_id", "").strip() or None

    try:
        events_services.update_track(request.actor, track, name=name, external_id=external_id)
    except ValueError:
        pass

    return redirect(reverse('organizer_event_tracks', args=[event.pk]))


@require_http_methods(["GET", "POST"])
def organizer_event_prizes_view(request, event_id):
    """
    List and add prizes for an event (/organizer/events/<int:event_id>/prizes).
    """
    _check_organizer(request.actor)
    event = get_object_or_404(Event, pk=event_id)

    error_message = None

    if request.method == "POST":
        rank_label = request.POST.get("rank_label", "").strip()
        description = request.POST.get("description", "").strip()

        try:
            events_services.create_prize(
                request.actor,
                event=event,
                rank_label=rank_label,
                description=description,
            )
            return redirect(reverse('organizer_event_prizes', args=[event.pk]))
        except ValueError as exc:
            error_message = str(exc)

    prizes = event.prizes.all().order_by('id')

    return render(request, "organizer/event_prizes.html", {
        "event": event,
        "prizes": prizes,
        "error_message": error_message,
    })


@require_POST
def organizer_event_prize_edit_view(request, event_id, prize_id):
    """
    Edit an existing prize (/organizer/events/<int:event_id>/prizes/<int:prize_id>).
    """
    _check_organizer(request.actor)
    event = get_object_or_404(Event, pk=event_id)
    prize = get_object_or_404(Prize, pk=prize_id, event=event)

    rank_label = request.POST.get("rank_label", "").strip() or None
    description = request.POST.get("description", "").strip() or None

    try:
        events_services.update_prize(request.actor, prize, rank_label=rank_label, description=description)
    except ValueError:
        pass

    return redirect(reverse('organizer_event_prizes', args=[event.pk]))


@require_POST
def organizer_event_make_current_view(request, event_id):
    """
    Explicit 'make current' action with warning (/organizer/events/<int:event_id>/make-current).
    Changes what the whole portal shows.
    """
    _check_organizer(request.actor)
    event = get_object_or_404(Event, pk=event_id)

    events_services.set_current_event(request.actor, event)

    return redirect(f"{reverse('organizer_events')}?switched={event.slug}")
