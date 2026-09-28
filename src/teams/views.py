from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods

from accounts.actors import require
from events.services import current_event
from teams.models import Team, TeamMembership
from teams import services as teams_services


@require_http_methods(["GET", "POST"])
def team_create_view(request):
    """
    Create a new team (/teams/new).
    Requires a logged-in user. Automatically enlists creator in the team and event.
    Redirects to the team detail page showing the invite link.
    """
    if request.actor.is_anonymous:
        return redirect(f"{reverse('login')}?next={reverse('team_create')}")

    event = getattr(request.actor, 'event', None) or current_event()
    if not event:
        raise Http404("No active event found.")

    error_message = None

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if not name:
            error_message = "Team name cannot be blank."
        else:
            try:
                team = teams_services.create_team(
                    request.actor,
                    event=event,
                    name=name,
                )
                return redirect(f"{reverse('team_detail', args=[team.id])}?created=1")
            except ValueError as exc:
                error_message = str(exc)

    return render(request, "teams/team_form.html", {
        "event": event,
        "error_message": error_message,
    })


@require_GET
def team_join_view(request, code):
    """
    Join a team via invite code link (/teams/join/<code>).
    If anonymous, redirects to login/register with safe `next`.
    If authenticated, joins the team (or redirects to team detail if already a member).
    """
    if request.actor.is_anonymous:
        join_url = reverse('team_join', args=[code])
        return redirect(f"{reverse('login')}?next={join_url}")

    team = get_object_or_404(Team, invite_code=code)

    if TeamMembership.objects.filter(team=team, user=request.actor.user).exists():
        return redirect(f"{reverse('team_detail', args=[team.id])}?already_member=1")

    try:
        teams_services.join_by_code(request.actor, code)
        return redirect(f"{reverse('team_detail', args=[team.id])}?joined=1")
    except ValueError as exc:
        return render(request, "teams/team_join_error.html", {
            "team": team,
            "error_message": str(exc),
        }, status=400)


@require_GET
def team_detail_view(request, id):
    """
    Team detail page (/teams/<id>).
    Displays team members and, for team members or organizers only, the invite link.
    """
    team = get_object_or_404(Team.objects.select_related('event', 'created_by'), pk=id)
    memberships = list(team.memberships.select_related('user').order_by('id'))

    is_member = False
    is_org = False

    if not request.actor.is_anonymous:
        is_member = any(m.user_id == request.actor.user.id for m in memberships)
        is_org = request.actor.is_organizer or getattr(request.actor, 'is_site_admin', False)

    invite_link = None
    if is_member or is_org:
        invite_link = request.build_absolute_uri(reverse('team_join', args=[team.invite_code]))

    created_banner = bool(request.GET.get('created'))
    joined_banner = bool(request.GET.get('joined'))
    already_member_banner = bool(request.GET.get('already_member'))

    return render(request, "teams/team_detail.html", {
        "team": team,
        "memberships": memberships,
        "is_member": is_member,
        "is_org": is_org,
        "invite_link": invite_link,
        "created_banner": created_banner,
        "joined_banner": joined_banner,
        "already_member_banner": already_member_banner,
    })
