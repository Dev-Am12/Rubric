"""
Organizer views for Rubric:
- /organizer (dashboard): Live progress, track under-coverage, graph health, flags.
- /organizer/assignments: Trigger runs, run history, connectivity report.
- /organizer/normalization: Trigger runs, Normalization Proof table with rank changes.

Design reference:
- UX.md §3 (the dashboard mockup — progress, under-coverage, graph health, flags, action buttons)
- UX.md §4 (clean, simple, professional, quietly sophisticated)
- API.md (organizer/assignments, organizer/normalization, export.csv routes)
- AUTHZ.md §3.2 (organizer access control)
"""

from collections import defaultdict

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from accounts.actors import PermissionDenied, require
from accounts.models import EventMembership, EventRole
from events.models import Track
from events.services import current_event
from judging.models import AssignmentRun, NormalizationRun, JudgeInvite
from services import assignment as assignment_services
from services import judging as judging_services
from services import normalization as norm_services
from services import submissions as submission_services
from services import voting as voting_services
from submissions.models import Project, ProjectStatus


@require_http_methods(['GET', 'POST'])
def organizer_dashboard_view(request):
    """
    Organizer dashboard (/organizer), per UX.md §3.
    Live progress, track under-coverage, graph health, flags.
    """
    if not request.actor.is_organizer:
        raise PermissionDenied

    event = request.actor.event

    # Handle duplicate restore action via POST
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'restore_duplicate':
            project_id = request.POST.get('project_id')
            try:
                submission_services.restore_duplicate(request.actor, project_id)
                # Re-run normalization so flags and rankings update immediately
                norm_services.run(request.actor)
            except (Project.DoesNotExist, ValueError):
                pass
            return redirect('organizer_dashboard')

    # Get latest normalization run, or compute if not yet run
    norm_run = NormalizationRun.objects.filter(event=event).order_by('-computed_at', '-id').first()
    if norm_run is None:
        norm_run = norm_services.run(request.actor)

    params = norm_run.parameters
    target_k = params.get('target_k', 3)
    review_counts = params.get('project_review_counts', {})
    project_flags_map = params.get('project_flags', {})
    judge_flags = params.get('judge_flags', [])

    # 1. Live progress
    all_projects = list(
        Project.objects.filter(event=event, status=ProjectStatus.SUBMITTED)
        .select_related('track', 'team')
        .order_by('pk')
    )
    total_projects = len(all_projects)
    projects_meeting_target = [
        p for p in all_projects
        if review_counts.get(p.external_id or f'project:{p.pk}', 0) >= target_k
    ]
    target_met_count = len(projects_meeting_target)
    progress_pct = int(target_met_count / total_projects * 100) if total_projects else 0

    # 2. Under-coverage by track
    under_covered_tracks = []
    total_short_reviews = 0
    tracks = list(Track.objects.filter(event=event).order_by('name'))
    for track in tracks:
        track_projects = [p for p in all_projects if p.track_id == track.pk and p.is_duplicate_of_id is None]
        short_count = 0
        short_proj_keys = []
        for p in track_projects:
            pkey = p.external_id or f'project:{p.pk}'
            cnt = review_counts.get(pkey, 0)
            if cnt < target_k:
                short_count += (target_k - cnt)
                short_proj_keys.append(pkey)
        if short_count > 0:
            total_short_reviews += short_count
            under_covered_tracks.append({
                'track': track,
                'short_count': short_count,
                'projects': short_proj_keys,
            })

    # 3. Graph health
    latest_assignment = AssignmentRun.objects.filter(event=event).order_by('-run_at', '-id').first()
    if latest_assignment and latest_assignment.connectivity_report:
        report = latest_assignment.connectivity_report
    else:
        report = assignment_services.compute_graph_health(event)

    n_components = report.get('n_components', 1)
    component_sizes = report.get('component_sizes', [30])
    total_judges = sum(component_sizes)
    fiedler_val = report.get('fiedler_value_global')
    if fiedler_val is None:
        fiedler_val = 0.0

    # 4. Flags
    # Constant-score judge flags
    constant_judges = [f for f in judge_flags if f.get('type') == 'constant_judge']

    # Thin-review-count projects
    thin_projects = []
    compound_flagged_projects = []
    for p in all_projects:
        pkey = p.external_id or f'project:{p.pk}'
        pflags = project_flags_map.get(pkey, [])
        flag_types = {f.get('type') for f in pflags}
        if 'thin_batch' in flag_types:
            thin_projects.append(p)
            if 'constant_judge' in flag_types:
                compound_flagged_projects.append(pkey)

    # Duplicate submissions
    duplicates = []
    for p in all_projects:
        if p.is_duplicate_of_id is not None:
            canonical = p.is_duplicate_of
            canonical_key = canonical.external_id or f'project:{canonical.pk}'
            team_label = (p.team.external_id or p.team.name) if p.team else 'Unknown team'
            duplicates.append({
                'project': p,
                'project_key': p.external_id or f'project:{p.pk}',
                'canonical_key': canonical_key,
                'team_name': team_label,
            })

    context = {
        'total_projects': total_projects,
        'target_met_count': target_met_count,
        'target_k': target_k,
        'progress_pct': progress_pct,
        'under_covered_tracks': under_covered_tracks,
        'total_short_reviews': total_short_reviews,
        'n_components': n_components,
        'component_sizes': component_sizes,
        'total_judges': total_judges,
        'fiedler_value': fiedler_val,
        'constant_judges': constant_judges,
        'thin_projects': thin_projects,
        'thin_count': len(thin_projects),
        'compound_flagged_projects': compound_flagged_projects,
        'duplicates': duplicates,
        'latest_norm_run': norm_run,
        'latest_assignment_run': latest_assignment,
        'voting_summary': voting_services.integrity_summary(request.actor, event),
    }
    return render(request, 'organizer/dashboard.html', context)


@require_http_methods(['GET', 'POST'])
def organizer_assignments_view(request):
    """
    Organizer assignments view (/organizer/assignments).
    Trigger a run via services.assignment.run(), show AssignmentRun history and connectivity report.
    """
    if not request.actor.is_organizer:
        raise PermissionDenied

    event = request.actor.event

    if request.method == 'POST':
        target_k = request.POST.get('target_k', '3').strip() or '3'
        seed_val = request.POST.get('seed', '').strip()
        seed = int(seed_val) if seed_val else None
        try:
            assignment_services.run(request.actor, k=int(target_k), seed=seed)
        except (ValueError, TypeError):
            pass
        return redirect('organizer_assignments')

    # GET
    runs = list(AssignmentRun.objects.filter(event=event).order_by('-run_at', '-id'))
    latest_run = runs[0] if runs else None

    # Current connectivity report (latest run or live calculation)
    if latest_run and latest_run.connectivity_report:
        connectivity = latest_run.connectivity_report
    else:
        connectivity = assignment_services.compute_graph_health(event)

    context = {
        'runs': runs,
        'latest_run': latest_run,
        'connectivity': connectivity,
        'n_components': connectivity.get('n_components', 1),
        'component_sizes': connectivity.get('component_sizes', []),
        'fiedler_global': connectivity.get('fiedler_value_global', 0.0),
        'fiedler_per_component': connectivity.get('fiedler_value_per_component', []),
    }
    return render(request, 'organizer/assignments.html', context)


@require_http_methods(['GET', 'POST'])
def organizer_normalization_view(request):
    """
    Organizer normalization view (/organizer/normalization).
    Trigger a run via services.normalization.run(), show the raw/normalized/rank-change table (Normalization Proof artifact).
    """
    if not request.actor.is_organizer:
        raise PermissionDenied

    event = request.actor.event

    if request.method == 'POST':
        norm_services.run(request.actor)
        return redirect('organizer_normalization')

    # Support downloading the raw proof artifact CSV
    if request.GET.get('format') == 'csv':
        latest_run = NormalizationRun.objects.filter(event=event).order_by('-computed_at', '-id').first()
        if latest_run is None:
            latest_run = norm_services.run(request.actor)
        csv_bytes = norm_services.build_proof_artifact(latest_run)
        response = HttpResponse(csv_bytes, content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="normalization_proof_run_{latest_run.pk}.csv"'
        return response

    latest_run = NormalizationRun.objects.filter(event=event).order_by('-computed_at', '-id').first()
    if latest_run is None:
        latest_run = norm_services.run(request.actor)

    params = latest_run.parameters
    flags_map = params.get('project_flags', {})
    review_counts = params.get('project_review_counts', {})

    score_rows = list(
        latest_run.scores.select_related('project', 'project__track', 'project__team')
        .order_by('project_id')
    )

    # Compute raw ranks within ranking scopes
    raw_rank_groups = defaultdict(list)
    for row in score_rows:
        if row.rank is None or row.raw_mean is None or row.normalized_mean is None:
            continue
        scope = 0 if params.get('ranking_scope') == 'global' else row.judge_graph_component_id
        raw_rank_groups[scope].append(row)
    raw_ranks = {}
    for scope, rows in raw_rank_groups.items():
        ordered = sorted(
            rows,
            key=lambda row: (
                -float(row.raw_mean),
                (0, row.project.external_id) if row.project.external_id else (1, f'{row.project.pk:020d}')
            ),
        )
        raw_ranks.update({row.project_id: rank for rank, row in enumerate(ordered, start=1)})

    table_rows = []
    for row in score_rows:
        project_key = row.project.external_id or f'project:{row.project.pk}'
        raw_rank = raw_ranks.get(row.project_id)
        rank_change = (raw_rank - row.rank) if (raw_rank is not None and row.rank is not None) else None
        pflags = flags_map.get(project_key, [])
        table_rows.append({
            'project': row.project,
            'project_key': project_key,
            'raw_mean': row.raw_mean,
            'normalized_mean': row.normalized_mean,
            'raw_rank': raw_rank,
            'normalized_rank': row.rank,
            'rank_change': rank_change,
            'review_count': review_counts.get(project_key, 0),
            'flags': pflags,
            'is_duplicate': row.project.is_duplicate_of_id is not None,
        })

    # Sort: ranked items by normalized_rank ascending, then unranked
    table_rows.sort(
        key=lambda item: (0, item['normalized_rank']) if item['normalized_rank'] is not None else (1, item['project_key'])
    )

    calibration_evidence = norm_services.compute_judge_calibration_evidence(latest_run)
    synthetic_evidence = norm_services.synthetic_validation(seed=2026)

    context = {
        'latest_run': latest_run,
        'params': params,
        'table_rows': table_rows,
        'total_scores': len(table_rows),
        'ranked_scores': sum(1 for r in table_rows if r['normalized_rank'] is not None),
        'excluded_scores': sum(1 for r in table_rows if r['normalized_rank'] is None),
        'calibration_evidence': calibration_evidence,
        'synthetic_evidence': synthetic_evidence,
    }
    return render(request, 'organizer/normalization.html', context)


@require_http_methods(['GET'])
def organizer_audit_log_page_view(request):
    """
    HTML viewer for organizer audit log (/organizer/audit-log).
    Displays the chain, head hash, Verify button, and Export download.
    """
    if not (request.actor.is_organizer or getattr(request.actor, 'is_site_admin', False)):
        raise PermissionDenied

    from audit.models import AuditChainHead
    from services import audit as audit_services

    page_raw = request.GET.get('page', 1)
    page_size_raw = request.GET.get('page_size', 25)
    try:
        page = max(1, int(page_raw))
    except (ValueError, TypeError):
        page = 1
    try:
        page_size = max(1, min(int(page_size_raw), 200))
    except (ValueError, TypeError):
        page_size = 25

    log_data = audit_services.list(request.actor, page=page, page_size=page_size)
    head = AuditChainHead.objects.filter(pk=1).first()

    verified = False
    is_valid = False
    first_bad_seq = None
    if request.GET.get('verify'):
        verified = True
        is_valid, first_bad_seq, _ = audit_services.verify(request.actor)

    context = {
        'entries': log_data['results'],
        'page': log_data['page'],
        'pages': log_data['pages'],
        'total': log_data['total'],
        'has_prev': log_data['page'] > 1,
        'has_next': log_data['page'] < log_data['pages'],
        'prev_page': log_data['page'] - 1,
        'next_page': log_data['page'] + 1,
        'head_seq': head.seq if head else 0,
        'head_hash': head.head_hash if head else audit_services.GENESIS_HASH,
        'verified': verified,
        'is_valid': is_valid,
        'first_bad_seq': first_bad_seq,
    }
    return render(request, 'organizer/audit_log.html', context)


@require_http_methods(['GET', 'POST'])
def organizer_rubric_view(request):
    """
    Organizer view to inspect and configure rubric criteria and weights (/organizer/rubric).
    """
    if not (request.actor.is_organizer or getattr(request.actor, 'is_site_admin', False)):
        raise PermissionDenied

    from services import judging as judging_services

    rubric = judging_services.get_rubric(request.actor)
    error = None
    saved = bool(request.GET.get('saved'))

    if request.method == 'POST':
        import json
        if request.content_type == 'application/json':
            payload = json.loads(request.body or '{}')
            criteria = payload.get('criteria', [])
        else:
            names = request.POST.getlist('name')
            weights = request.POST.getlist('weight')
            max_scores = request.POST.getlist('max_score')
            orders = request.POST.getlist('order')
            criteria = []
            for i in range(len(names)):
                clean_name = names[i].strip()
                if clean_name:
                    criteria.append({
                        'name': clean_name,
                        'weight': weights[i] if i < len(weights) else '1.0',
                        'max_score': max_scores[i] if i < len(max_scores) else '5.0',
                        'order': orders[i] if i < len(orders) else i,
                    })

        try:
            judging_services.configure_rubric(request.actor, criteria)
            return redirect('/organizer/rubric?saved=1')
        except ValueError as exc:
            error = str(exc)

    criteria_list = []
    if rubric:
        for c in rubric.criteria.all():
            score_count = c.ballot_scores.count()
            criteria_list.append({
                'id': c.pk,
                'name': c.name,
                'weight': c.weight,
                'max_score': c.max_score,
                'order': c.order,
                'is_scored': score_count > 0,
                'score_count': score_count,
            })

    context = {
        'rubric': rubric,
        'criteria': criteria_list,
        'error': error,
        'saved': saved,
        'has_scored_criteria': any(c['is_scored'] for c in criteria_list),
    }
    status_code = 400 if error else 200
    return render(request, 'organizer/rubric.html', context, status=status_code)


@require_http_methods(['GET', 'POST'])
def organizer_judges_view(request):
    """
    Organizer judges management page (/organizer/judges).
    Lists invited and accepted judges for the active event.
    Provides a form to invite a judge by email + tracks.
    Shows the generated invite link ONCE upon creation.
    """
    if not (request.actor.is_organizer or getattr(request.actor, 'is_site_admin', False)):
        raise PermissionDenied

    event = getattr(request.actor, 'event', None) or current_event()
    if not event:
        raise Http404("No active event found.")

    new_invite_url = None
    new_invite_email = None
    error_message = None

    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        track_ids = request.POST.getlist('tracks')

        try:
            invite, raw_token = judging_services.create_judge_invite(
                actor=request.actor,
                event=event,
                email=email,
                track_ids=track_ids,
            )
            new_invite_url = request.build_absolute_uri(
                reverse('judge_invite_accept', args=[raw_token])
            )
            new_invite_email = email
        except ValueError as exc:
            error_message = str(exc)

    invites = list(
        JudgeInvite.objects.filter(event=event)
        .select_related('created_by')
        .prefetch_related('tracks')
        .order_by('-created_at')
    )

    accepted_judges = list(
        EventMembership.objects.filter(event=event, role=EventRole.JUDGE)
        .select_related('user')
        .prefetch_related('track_eligibilities__track')
        .order_by('user__email')
    )

    tracks = list(event.tracks.all().order_by('name'))

    context = {
        'event': event,
        'invites': invites,
        'accepted_judges': accepted_judges,
        'tracks': tracks,
        'new_invite_url': new_invite_url,
        'new_invite_email': new_invite_email,
        'error_message': error_message,
    }
    return render(request, 'organizer/judges.html', context)


@require_http_methods(['GET', 'POST'])
def judge_invite_accept_view(request, token):
    """
    Accept flow for judge invitations (/invite/judge/<token>).
    1. If anonymous: redirects to /login?next=/invite/judge/<token> (or register).
    2. Verifies token validity, event matching, expiry, and already-used state.
    3. Requires logged-in user whose email matches the invitation email.
    4. Upon acceptance, creates EventMembership(JUDGE) and JudgeTrackEligibility rows,
       audit-logs the acceptance, and redirects to /judge/queue.
    """
    if request.actor.is_anonymous:
        login_url = reverse('login')
        next_path = reverse('judge_invite_accept', args=[token])
        return redirect(f"{login_url}?next={next_path}")

    invite = judging_services.get_judge_invite(token)
    if not invite:
        return render(request, 'judging/invite_error.html', {
            'error_title': 'Invalid Invitation Link',
            'error_message': 'The judge invitation token is invalid or has been corrupted.',
        }, status=404)

    curr_event = current_event()
    if curr_event and invite.event_id != curr_event.pk:
        return render(request, 'judging/invite_error.html', {
            'error_title': 'Cross-Event Invitation',
            'error_message': 'This judge invitation is for a different event than the currently active event.',
        }, status=400)

    if invite.is_expired():
        return render(request, 'judging/invite_error.html', {
            'error_title': 'Invitation Expired',
            'error_message': 'This judge invitation has expired (exceeded 14-day validity).',
        }, status=400)

    if invite.is_accepted():
        return render(request, 'judging/invite_error.html', {
            'error_title': 'Already Accepted',
            'error_message': f'This judge invitation was already accepted on {invite.accepted_at.strftime("%Y-%m-%d %H:%M UTC")}.',
        }, status=400)

    # Check email match
    user_email = request.actor.user.email.strip().lower()
    invite_email = invite.email.strip().lower()
    if user_email != invite_email:
        return render(request, 'judging/invite_error.html', {
            'error_title': 'Email Mismatch',
            'error_message': (
                f"This invitation was issued to '{invite.email}', but you are logged in as "
                f"'{request.actor.user.email}'. Please log out and log in or register with "
                f"'{invite.email}' to accept this invitation."
            ),
        }, status=403)

    # Accept the invite
    try:
        judging_services.accept_judge_invite(request.actor, token)
        return redirect(f"{reverse('judge_queue')}?accepted=1")
    except (ValueError, PermissionDenied) as exc:
        return render(request, 'judging/invite_error.html', {
            'error_title': 'Error Accepting Invitation',
            'error_message': str(exc),
        }, status=400)


