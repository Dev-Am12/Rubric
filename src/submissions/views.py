"""
Views for submissions (gallery, project detail, submission forms, my submissions).

Design reference:
  - UX.md §1 (screen inventory: /projects, /projects/{id}, /projects/new,
               /projects/{id}/edit, /my/submissions)
  - UX.md §4 (clean, minimal, professional)
  - API.md §2 (thin presentation layer calling services.submissions.*)
  - AUTHZ.md §3.1 (draft visibility, owner permissions)
"""

import json
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.actors import PermissionDenied, require
from events.models import Event, Track
from submissions.models import Project, ProjectStatus
from submissions import services as submissions_services
from teams.models import Team, TeamMembership


def _is_team_member(actor, team):
    if actor.is_anonymous:
        return False
    return TeamMembership.objects.filter(team=team, user=actor.user).exists()


def gallery_view(request):
    """
    Public gallery of SUBMITTED projects (/projects).
    P-11 public project gallery (API.md §2, D-13).
    No auth required. Shows all submitted projects without pagination.
    """
    q = request.GET.get('q', '').strip() or None
    track = request.GET.get('track', '').strip() or None
    tag = request.GET.get('tag', '').strip() or None

    projects = list(submissions_services.gallery(
        request.actor,
        q=q,
        track=track,
        tag=tag,
    ))

    tracks = Track.objects.all().order_by('name')

    context = {
        'projects': projects,
        'tracks': tracks,
        'q': q or '',
        'selected_track': track or '',
        'selected_tag': tag or '',
    }

    return render(request, 'submissions/gallery.html', context)


def project_detail_view(request, id):
    """
    Project detail (/projects/{id}).
    Public if SUBMITTED, owner/organizer otherwise.
    Calls services.submissions.get(actor, id) and lets PermissionDenied
    flow through normally to AuthMiddleware.
    """
    try:
        project = submissions_services.get(request.actor, id)
    except ValueError:
        raise Http404("Project not found.")

    is_owner = False
    is_org = False
    if not request.actor.is_anonymous:
        is_owner = _is_team_member(request.actor, project.team)
        is_org = request.actor.is_organizer or request.actor.is_site_admin

    return render(request, 'submissions/project_detail.html', {
        'project': project,
        'is_owner': is_owner,
        'is_org': is_org,
    })


def submit_view(request):
    """
    Create a new project submission (/projects/new).
    P-11 submit route (API.md §2).
    Requires participant on their own team while submissions are open.
    Supports both JSON POST (API/checker) and HTMX/HTML form.
    """
    # Look up participant teams and event
    user_teams = []
    if not request.actor.is_anonymous:
        user_teams = list(Team.objects.filter(memberships__user=request.actor.user))

    event = getattr(request.actor, 'event', None) or Event.objects.first()
    is_org = request.actor.is_organizer or request.actor.is_site_admin
    is_closed = bool(event and event.submissions_close_at and timezone.now() > event.submissions_close_at)

    if request.method == 'POST':
        # Check content type for JSON vs form data
        if request.content_type == 'application/json':
            try:
                data = json.loads(request.body.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return JsonResponse({'error': 'bad_request', 'detail': 'Invalid JSON'}, status=400)

            require(request.actor, not request.actor.is_anonymous)

            team_id = data.get('team') or data.get('team_id')
            if team_id:
                try:
                    team = Team.objects.get(id=team_id)
                except Team.DoesNotExist:
                    return JsonResponse({'error': 'bad_request', 'detail': 'Team not found'}, status=400)
            elif user_teams:
                team = user_teams[0]
            elif event:
                # Solo participant: 1-person team per SCHEMA.md §1.1
                team = Team.objects.create(
                    event=event,
                    name=request.actor.user.display_name or 'Solo Team',
                    created_by=request.actor.user,
                )
                TeamMembership.objects.create(team=team, user=request.actor.user)
            else:
                raise PermissionDenied("Team membership required to submit.")

            track_id = data.get('track') or data.get('track_id')
            if track_id:
                try:
                    track = Track.objects.get(id=track_id)
                except Track.DoesNotExist:
                    track = Track.objects.filter(event=team.event).first()
            else:
                track = Track.objects.filter(event=team.event).first()

            if not track and event:
                track = Track.objects.create(event=event, name='General')

            tags = data.get('tech_tags') or []
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(',') if t.strip()]

            project = submissions_services.create(
                request.actor,
                team=team,
                track=track,
                title=data.get('title', ''),
                summary=data.get('summary', ''),
                description=data.get('description', ''),
                repo_url=data.get('repo_url', ''),
                demo_video_url=data.get('demo_video_url', ''),
                live_url=data.get('live_url', ''),
                tech_tags=tags,
                custom_answers=data.get('custom_answers', {}),
            )
            return JsonResponse({
                'id': project.id,
                'title': project.title,
                'status': project.status,
            }, status=200)

        # Form submission
        require(request.actor, not request.actor.is_anonymous)

        team_id = request.POST.get('team_id')
        if team_id:
            try:
                team = Team.objects.get(id=team_id)
            except Team.DoesNotExist:
                raise Http404("Team not found.")
        elif user_teams:
            team = user_teams[0]
        else:
            raise PermissionDenied("Team membership required to submit.")

        track_id = request.POST.get('track_id')
        if track_id:
            try:
                track = Track.objects.get(id=track_id)
            except Track.DoesNotExist:
                track = Track.objects.filter(event=team.event).first()
        else:
            track = Track.objects.filter(event=team.event).first()

        tags_str = request.POST.get('tech_tags', '')
        tech_tags = [t.strip() for t in tags_str.split(',') if t.strip()]

        try:
            project = submissions_services.create(
                request.actor,
                team=team,
                track=track,
                title=request.POST.get('title', ''),
                summary=request.POST.get('summary', ''),
                description=request.POST.get('description', ''),
                repo_url=request.POST.get('repo_url', ''),
                demo_video_url=request.POST.get('demo_video_url', ''),
                live_url=request.POST.get('live_url', ''),
                tech_tags=tech_tags,
            )
        except PermissionDenied:
            if is_closed and not is_org:
                return render(request, 'submissions/project_form.html', {
                    'is_new': True,
                    'closed': True,
                    'error_message': 'Submissions are closed for this event. New submissions are no longer accepted.',
                    'event': event,
                    'teams': user_teams,
                    'tracks': Track.objects.filter(event=event).order_by('name') if event else [],
                }, status=403)
            raise

        if request.headers.get('HX-Request'):
            response = HttpResponse(status=204)
            response['HX-Redirect'] = f'/projects/{project.id}'
            return response
        return redirect(f'/projects/{project.id}')

    # GET request
    tracks = Track.objects.filter(event=event).order_by('name') if event else Track.objects.all().order_by('name')

    return render(request, 'submissions/project_form.html', {
        'is_new': True,
        'closed': is_closed and not is_org,
        'event': event,
        'teams': user_teams,
        'tracks': tracks,
    })


def project_edit_view(request, id):
    """
    Edit project submission (/projects/{id}/edit).
    Owner or organizer only.
    Before deadline for non-organizers.
    If update() rejects because the event is closed, shows an honest
    "submissions are closed" state instead of a generic error.
    """
    try:
        project = submissions_services.get(request.actor, id)
    except ValueError:
        raise Http404("Project not found.")

    event = project.event
    is_org = request.actor.is_organizer or request.actor.is_site_admin
    is_closed = bool(event.submissions_close_at and timezone.now() > event.submissions_close_at)

    if request.method == 'POST':
        action = request.POST.get('action', 'save')

        tags_str = request.POST.get('tech_tags', '')
        tech_tags = [t.strip() for t in tags_str.split(',') if t.strip()]

        update_fields = {
            'title': request.POST.get('title', project.title),
            'summary': request.POST.get('summary', project.summary),
            'description': request.POST.get('description', project.description),
            'repo_url': request.POST.get('repo_url', project.repo_url),
            'demo_video_url': request.POST.get('demo_video_url', project.demo_video_url),
            'live_url': request.POST.get('live_url', project.live_url),
            'tech_tags': tech_tags,
        }

        try:
            if action == 'submit_final':
                # Save latest fields first, then submit
                submissions_services.update(request.actor, id, **update_fields)
                submissions_services.submit(request.actor, id)
            else:
                submissions_services.update(request.actor, id, **update_fields)
        except PermissionDenied:
            # If rejected because the event is closed, render honest closed state
            if is_closed and not is_org:
                context = {
                    'project': project,
                    'is_new': False,
                    'closed': True,
                    'error_message': 'Submissions are closed for this event. Changes could not be saved because the deadline has passed.',
                    'event': event,
                }
                if request.headers.get('HX-Request'):
                    return render(request, 'submissions/partials/form_closed_alert.html', context, status=403)
                return render(request, 'submissions/project_form.html', context, status=403)
            raise

        if request.headers.get('HX-Request'):
            response = HttpResponse(status=204)
            response['HX-Redirect'] = f'/projects/{project.id}'
            return response
        return redirect(f'/projects/{project.id}')

    # GET request
    return render(request, 'submissions/project_form.html', {
        'project': project,
        'is_new': False,
        'closed': is_closed and not is_org,
        'event': event,
    })


def my_submissions_view(request):
    """
    Participant's own team's submissions (/my/submissions).
    Shows projects submitted by the participant's team(s).
    Shows the duplicate-flag banner when is_duplicate_of is set (tm_07 screen).
    """
    require(request.actor, not request.actor.is_anonymous)

    teams = list(Team.objects.filter(memberships__user=request.actor.user))
    projects = list(
        Project.objects.filter(team__in=teams)
        .select_related('team', 'track', 'is_duplicate_of', 'event')
        .order_by('-submitted_at', '-id')
    )

    return render(request, 'submissions/my_submissions.html', {
        'projects': projects,
        'teams': teams,
    })
