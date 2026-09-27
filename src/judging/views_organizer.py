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

from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from accounts.actors import PermissionDenied
from events.models import Track
from judging.models import AssignmentRun, NormalizationRun
from services import assignment as assignment_services
from services import normalization as norm_services
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
                project = Project.objects.get(pk=project_id, event=event)
                project.is_duplicate_of = None
                project.save(update_fields=['is_duplicate_of'])
                # Re-run normalization so flags and rankings update immediately
                norm_services.run(request.actor)
            except Project.DoesNotExist:
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

    context = {
        'latest_run': latest_run,
        'params': params,
        'table_rows': table_rows,
        'total_scores': len(table_rows),
        'ranked_scores': sum(1 for r in table_rows if r['normalized_rank'] is not None),
        'excluded_scores': sum(1 for r in table_rows if r['normalized_rank'] is None),
    }
    return render(request, 'organizer/normalization.html', context)
