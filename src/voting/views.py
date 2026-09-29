"""Thin HTTP adapters; authorization, identity, and voting rules live in services.voting."""

import json

from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_GET, require_POST

from accounts.actors import PermissionDenied
from voting import models
from services import voting as voting_services


def _json_requested(request):
    return request.GET.get('format') == 'json' or 'application/json' in request.headers.get('Accept', '')


def _request_identity(request):
    # REMOTE_ADDR is intentional: X-Forwarded-For is client-controlled unless a trusted proxy is configured.
    return {
        'ip': request.META.get('REMOTE_ADDR', ''),
        'user_agent': request.META.get('HTTP_USER_AGENT', ''),
    }


def _load_body(request):
    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None, JsonResponse({'error': 'bad_request', 'detail': 'Invalid JSON.'}, status=400)
        if not isinstance(data, dict):
            return None, JsonResponse({'error': 'bad_request', 'detail': 'JSON body must be an object.'}, status=400)
        return data, None
    return request.POST, None


def _attempt_response(request, attempt, *, redirect_to=None):
    outcome = attempt.outcome
    status = {
        models.VoteAttemptOutcome.ACCEPTED: 201,
        models.VoteAttemptOutcome.WITHDRAWN: 200,
        models.VoteAttemptOutcome.REJECTED_DUPLICATE: 409,
        models.VoteAttemptOutcome.REJECTED_RATE_LIMIT: 429,
        models.VoteAttemptOutcome.REJECTED_CLOSED: 403,
        models.VoteAttemptOutcome.REJECTED_BUDGET: 409,
    }[outcome]
    if status in (200, 201) and redirect_to:
        return redirect(redirect_to)
    return JsonResponse({'outcome': outcome, 'attempt_id': attempt.pk}, status=status)


def _is_htmx(request):
    return request.headers.get('HX-Request', '').lower() == 'true'


def _attempt_message(attempt):
    return {
        models.VoteAttemptOutcome.REJECTED_DUPLICATE: 'You have already voted for this project.',
        models.VoteAttemptOutcome.REJECTED_RATE_LIMIT: 'Too many voting actions. Please wait a minute and try again.',
        models.VoteAttemptOutcome.REJECTED_BUDGET: 'Your vote budget is used. Withdraw another vote to free a slot.',
        models.VoteAttemptOutcome.REJECTED_CLOSED: 'Voting is not open right now.',
        models.VoteAttemptOutcome.WITHDRAWN: 'Vote withdrawn. Your budget slot is available again.',
        models.VoteAttemptOutcome.ACCEPTED: 'Vote recorded.',
    }.get(attempt.outcome, 'Voting action was not accepted.')


def _render_vote_update(request, event_slug, project_id, attempt):
    ballot = voting_services.get_ballot(
        request.actor, event_slug, **_request_identity(request),
    )
    project = next((item for item in ballot['projects'] if item.pk == project_id), None)
    if project is None:
        raise Http404('Project not found.')
    html = render_to_string('voting/_vote_card.html', {
        'ballot': ballot,
        'project': project,
        'vote_message': _attempt_message(attempt),
    }, request=request)
    html += render_to_string('voting/_vote_budget.html', {
        'ballot': ballot,
        'oob': True,
    }, request=request)
    return HttpResponse(html)


def _ballot_json(ballot):
    return {
        'event': {'slug': ballot['event'].slug, 'name': ballot['event'].name},
        'mode': ballot['mode'],
        'voting_open': ballot['voting_open'],
        'vote_budget': ballot['vote_budget'],
        'remaining_budget': ballot['remaining_budget'],
        'cast_project_ids': sorted(ballot['cast_project_ids']),
        'projects': [
            {
                'id': project.pk,
                'external_id': project.external_id,
                'title': project.title,
                'summary': project.summary,
                'track': project.track.name,
                'has_voted': project.pk in ballot['cast_project_ids'],
            }
            for project in ballot['projects']
        ],
    }


@require_GET
def ballot_view(request, event_slug):
    try:
        ballot = voting_services.get_ballot(
            request.actor, event_slug, **_request_identity(request),
        )
    except ValueError as exc:
        raise Http404(str(exc))
    except PermissionDenied:
        if request.actor.is_anonymous and not _json_requested(request):
            next_url = request.get_full_path()
            query = urlencode({'next': next_url, 'voting_required': '1'})
            return redirect(f"{reverse('login')}?{query}")
        raise
    if _json_requested(request):
        return JsonResponse(_ballot_json(ballot))
    return render(request, 'voting/ballot.html', {'ballot': ballot})


@require_POST
def cast_view(request, event_slug, project_id):
    data, error = _load_body(request)
    if error:
        return error
    try:
        attempt = voting_services.cast(
            request.actor, event_slug, project_id, **_request_identity(request),
        )
    except ValueError as exc:
        raise Http404(str(exc))
    if _is_htmx(request):
        return _render_vote_update(request, event_slug, project_id, attempt)
    return _attempt_response(
        request, attempt,
        redirect_to=reverse('voting_ballot', args=[event_slug]),
    )


@require_POST
def withdraw_view(request, event_slug, project_id):
    try:
        attempt = voting_services.withdraw(
            request.actor, event_slug, project_id, **_request_identity(request),
        )
    except ValueError as exc:
        return JsonResponse({'error': 'not_found', 'detail': str(exc)}, status=404)
    if _is_htmx(request):
        return _render_vote_update(request, event_slug, project_id, attempt)
    return _attempt_response(
        request, attempt,
        redirect_to=reverse('voting_ballot', args=[event_slug]),
    )


def _results_json(result):
    return {
        'event': {'slug': result['event'].slug, 'name': result['event'].name},
        'results': [
            {
                'project_id': row['project'].pk,
                'external_id': row['project'].external_id,
                'title': row['project'].title,
                'vote_count': row['vote_count'],
            }
            for row in result['results']
        ],
    }


@require_GET
def results_view(request, event_slug):
    try:
        result = voting_services.get_results(request.actor, event_slug)
    except PermissionDenied:
        if _json_requested(request):
            raise
        return render(request, 'voting/results_hidden.html', status=200)
    if _json_requested(request):
        return JsonResponse(_results_json(result))
    return render(request, 'voting/results.html', {'result': result})


@require_POST
def project_comment_view(request, project_id):
    data, error = _load_body(request)
    if error:
        return error
    body = data.get('body', '')
    try:
        result = voting_services.comment(
            request.actor, project_id, body, **_request_identity(request),
        )
    except ValueError as exc:
        return JsonResponse({'error': 'bad_request', 'detail': str(exc)}, status=400)
    if isinstance(result, models.VoteAttempt):
        return _attempt_response(request, result)
    if request.content_type == 'application/json' or _json_requested(request):
        return JsonResponse({'id': result.pk, 'project_id': result.project_id}, status=201)
    return redirect(reverse('project_detail', args=[project_id]))


@require_POST
def organizer_comment_flag_view(request, comment_id):
    data, error = _load_body(request)
    if error:
        return error
    flagged = str(data.get('flagged', 'true')).strip().lower() not in {'0', 'false', 'no'}
    try:
        comment = (
            voting_services.flag_comment(request.actor, comment_id)
            if flagged else voting_services.unflag_comment(request.actor, comment_id)
        )
    except ValueError as exc:
        return JsonResponse({'error': 'not_found', 'detail': str(exc)}, status=404)
    if not _is_htmx(request):
        return redirect(reverse('project_detail', args=[comment.project_id]))
    return JsonResponse({'id': comment.pk, 'is_flagged': comment.is_flagged})


@require_GET
def organizer_voting_summary_view(request):
    summary = voting_services.integrity_summary(request.actor, request.actor.event)
    if _is_htmx(request):
        return render(request, 'organizer/_voting_integrity.html', {'summary': summary})
    return JsonResponse({
        'event': summary['event'].slug,
        'total_attempts': summary['total_attempts'],
        'outcomes': summary['outcomes'],
        'projects': summary['projects'],
    })
