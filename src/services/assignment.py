"""Live, additive judge assignment and judge-graph health computation."""

from collections import defaultdict, deque
import random

import numpy as np
from django.db import transaction
from django.utils import timezone

from accounts.actors import PermissionDenied
from accounts.models import EventMembership, EventRole, JudgeTrackEligibility
from judging.models import AssignmentRun, AssignmentStatus, JudgeAssignment
from submissions.models import Project, ProjectStatus
from teams.models import TeamMembership


def _stable_key(obj):
    external_id = getattr(obj, 'external_id', None)
    return (0, str(external_id)) if external_id is not None else (1, f'{obj.pk:020d}')


def _project_key(project):
    return project.external_id or f'project:{project.pk}'


def _judge_key(judge):
    return judge.external_id or f'judge:{judge.pk}'


def _event_judges(event):
    memberships = EventMembership.objects.filter(
        event=event, role=EventRole.JUDGE,
    ).select_related('user').order_by('user__external_id', 'user_id')
    judges = [membership.user for membership in memberships]
    judges.sort(key=_stable_key)
    return judges


def _components(judge_ids, adjacency):
    remaining = set(judge_ids)
    components = []
    while remaining:
        start = min(remaining)
        remaining.remove(start)
        queue = deque([start])
        component = []
        while queue:
            current = queue.popleft()
            component.append(current)
            for neighbor in sorted(adjacency[current]):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    queue.append(neighbor)
        components.append(sorted(component))
    return components


def _laplacian(adjacency, node_ids):
    size = len(node_ids)
    index = {node_id: position for position, node_id in enumerate(node_ids)}
    matrix = np.zeros((size, size), dtype=float)
    for node_id in node_ids:
        row = index[node_id]
        neighbors = [neighbor for neighbor in adjacency[node_id] if neighbor in index]
        matrix[row, row] = len(neighbors)
        for neighbor in neighbors:
            matrix[row, index[neighbor]] = -1.0
    return matrix


def _fiedler(adjacency, node_ids):
    # F9: a singleton has no second-smallest eigenvalue.
    if len(node_ids) < 2:
        return None
    return float(np.linalg.eigvalsh(_laplacian(adjacency, node_ids))[1])


def compute_graph_health(event):
    """Return the spectral and BFS connectivity report for all event judges."""
    judges = _event_judges(event)
    judge_ids = [judge.pk for judge in judges]
    adjacency = {judge_id: set() for judge_id in judge_ids}
    assignments = JudgeAssignment.objects.filter(event=event).values_list('project_id', 'judge_id')
    judges_by_project = defaultdict(list)
    for project_id, judge_id in assignments:
        if judge_id in adjacency:
            judges_by_project[project_id].append(judge_id)
    for judge_list in judges_by_project.values():
        unique_ids = sorted(set(judge_list))
        for index, judge_id in enumerate(unique_ids):
            adjacency[judge_id].update(unique_ids[:index])
            adjacency[judge_id].update(unique_ids[index + 1:])

    components = _components(judge_ids, adjacency)
    global_eigenvalues = np.linalg.eigvalsh(_laplacian(adjacency, judge_ids)) if judge_ids else np.array([])
    spectral_count = int(np.sum(global_eigenvalues < 1e-9))
    return {
        'n_components': spectral_count,
        'component_sizes': [len(component) for component in components],
        'fiedler_value_global': _fiedler(adjacency, judge_ids) if len(components) == 1 else 0.0,
        'fiedler_value_per_component': [_fiedler(adjacency, component) for component in components],
    }


def _eligible_by_track(event):
    eligibility = defaultdict(list)
    rows = JudgeTrackEligibility.objects.filter(
        event_membership__event=event,
        event_membership__role=EventRole.JUDGE,
    ).select_related('event_membership__user', 'track')
    for row in rows:
        eligibility[row.track_id].append(row.event_membership.user)
    for judges in eligibility.values():
        judges.sort(key=_stable_key)
    return eligibility


def _inject_anchors(event, rng, eligibility_by_track):
    """Bridge components only through genuine multi-track eligibility."""
    injections = []
    while True:
        health = compute_graph_health(event)
        if health['n_components'] <= 1:
            return injections
        judges = _event_judges(event)
        judge_ids = [judge.pk for judge in judges]
        assignments = list(JudgeAssignment.objects.filter(event=event).select_related('judge', 'project__team'))
        projects_by_judge = defaultdict(set)
        judges_by_project = defaultdict(set)
        for assignment in assignments:
            projects_by_judge[assignment.judge_id].add(assignment.project_id)
            judges_by_project[assignment.project_id].add(assignment.judge_id)
        adjacency = {judge_id: set() for judge_id in judge_ids}
        for reviewer_ids in judges_by_project.values():
            for judge_id in reviewer_ids:
                adjacency[judge_id].update(reviewer_ids - {judge_id})
        components = _components(judge_ids, adjacency)
        component_for_judge = {
            judge_id: component_id for component_id, component in enumerate(components) for judge_id in component
        }
        mean_load = sum(len(projects_by_judge[judge.pk]) for judge in judges) / len(judges) if judges else 0.0
        eligible_track_ids = defaultdict(set)
        for track_id, eligible_judges in eligibility_by_track.items():
            for judge in eligible_judges:
                eligible_track_ids[judge.pk].add(track_id)
        team_members = defaultdict(set)
        for team_id, user_id in TeamMembership.objects.filter(team__event=event).values_list('team_id', 'user_id'):
            team_members[team_id].add(user_id)
        candidates = []
        projects = list(Project.objects.filter(event=event, status=ProjectStatus.SUBMITTED).select_related('team'))
        projects.sort(key=_stable_key)
        for judge in judges:
            if len(eligible_track_ids[judge.pk]) < 2 or len(projects_by_judge[judge.pk]) >= mean_load + 1:
                continue
            own_component = component_for_judge[judge.pk]
            for project in projects:
                if project.track_id not in eligible_track_ids[judge.pk]:
                    continue
                if project.pk in projects_by_judge[judge.pk] or judge.pk in team_members[project.team_id]:
                    continue
                reviewer_components = {component_for_judge[reviewer] for reviewer in judges_by_project[project.pk]}
                other_components = reviewer_components - {own_component}
                if other_components:
                    candidates.append((judge, project, own_component, min(other_components)))
        if not candidates:
            return injections
        candidates.sort(key=lambda item: (_stable_key(item[0]), _stable_key(item[1])))
        # Seeded choice removes a systematic bias between otherwise viable anchors.
        judge, project, from_component, to_component = candidates[rng.randrange(len(candidates))]
        JudgeAssignment.objects.create(
            event=event, judge=judge, project=project, status=AssignmentStatus.PENDING,
        )
        injections.append({
            'judge_external_id': judge.external_id,
            'judge_id': judge.pk,
            'project_id': _project_key(project),
            'bridged_components': [from_component + 1, to_component + 1],
        })


@transaction.atomic
def run(actor, k, seed=None):
    """Add pending assignments for eligible, non-conflicted judges; never reshuffle."""
    if not actor.is_organizer or actor.event is None:
        raise PermissionDenied
    if int(k) < 1:
        raise ValueError('k must be at least 1')
    seed = 0 if seed is None else int(seed)
    event = actor.event
    rng = random.Random(seed)
    under_coverage = []
    eligibility_by_track = _eligible_by_track(event)
    team_members = defaultdict(set)
    for team_id, user_id in TeamMembership.objects.filter(team__event=event).values_list('team_id', 'user_id'):
        team_members[team_id].add(user_id)

    tracks = list(event.tracks.all())
    tracks.sort(key=_stable_key)
    for track in tracks:
        eligible = eligibility_by_track.get(track.pk, [])
        projects = list(Project.objects.filter(track=track, status=ProjectStatus.SUBMITTED).select_related('team'))
        projects.sort(key=_stable_key)
        rng.shuffle(projects)
        loads = {
            judge.pk: JudgeAssignment.objects.filter(event=event, judge=judge).count()
            for judge in eligible
        }
        for project in projects:
            existing_assignments = set(JudgeAssignment.objects.filter(event=event, project=project).values_list('judge_id', flat=True))
            existing = len(existing_assignments)
            needed = max(0, int(k) - existing)
            candidate_rows = [
                (loads[judge.pk], rng.random(), judge)
                for judge in eligible
                if judge.pk not in team_members[project.team_id] and judge.pk not in existing_assignments
            ]
            candidate_rows.sort(key=lambda item: (item[0], item[1]))
            picked = candidate_rows[:needed]
            for _, _, judge in picked:
                JudgeAssignment.objects.create(
                    event=event, judge=judge, project=project, status=AssignmentStatus.PENDING,
                )
                loads[judge.pk] += 1
            if len(picked) < needed:
                under_coverage.append({
                    'project_id': _project_key(project),
                    'got': existing + len(picked),
                    'wanted': int(k),
                })

    anchor_injections = _inject_anchors(event, rng, eligibility_by_track)
    connectivity_report = compute_graph_health(event)
    assignment_run = AssignmentRun.objects.create(
        event=event,
        run_at=timezone.now(),
        target_k=int(k),
        seed=seed,
        under_coverage=under_coverage,
        connectivity_report=connectivity_report,
        anchor_injections=anchor_injections,
    )

    from services import audit
    audit.record(
        actor=actor,
        action='assignment.run',
        target=assignment_run,
        payload={
            'target_k': int(k),
            'seed': seed,
            'under_coverage_count': len(under_coverage),
            'anchor_injections_count': len(anchor_injections),
        },
    )

    return assignment_run


def get_run(actor, run_id):
    if not actor.is_organizer or actor.event is None:
        raise PermissionDenied
    return AssignmentRun.objects.get(pk=run_id, event=actor.event)
