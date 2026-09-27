"""Deterministic, component-aware empirical-Bayes score normalization."""

import csv
import io
import itertools
import json
import math
from collections import Counter, defaultdict, deque
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from accounts.actors import PermissionDenied
from judging.models import Ballot, NormalizationRun, NormalizedScore
from submissions.models import Project


METHOD_NAME = 'empirical_bayes_shrinkage_v1'
KAPPA0 = 4.0
NU0 = 4.0


def _stable_key(obj):
    external_id = getattr(obj, 'external_id', None)
    if external_id is not None:
        return (0, str(external_id))
    return (1, f'{obj.pk:020d}')


def _project_key(project):
    return project.external_id or f'project:{project.pk}'


def _mean(values):
    ordered = sorted(float(v) for v in values)
    if not ordered:
        return 0.0
    return math.fsum(ordered) / len(ordered)


def _variance(values, mean=None):
    ordered = sorted(float(v) for v in values)
    if not ordered:
        return 0.0
    center = _mean(ordered) if mean is None else float(mean)
    return math.fsum((value - center) ** 2 for value in ordered) / len(ordered)


def _collapse_ballot(ballot):
    weighted_values = []
    for ballot_score in ballot.scores.all():
        weight = Decimal(ballot_score.criterion.weight)
        weighted_values.append((ballot_score.pk, Decimal(ballot_score.value), weight))
    weighted_values.sort(key=lambda item: item[0])
    weight_total = sum((weight for _, _, weight in weighted_values), Decimal('0'))
    if not weighted_values or weight_total <= 0:
        return None
    weighted_total = sum((value * weight for _, value, weight in weighted_values), Decimal('0'))
    return float(weighted_total / weight_total)


def _connected_components(judge_ids, adjacency, users_by_id):
    remaining = set(judge_ids)
    components = []
    while remaining:
        start = min(remaining, key=lambda judge_id: _stable_key(users_by_id[judge_id]))
        remaining.remove(start)
        queue = deque([start])
        component = []
        while queue:
            node = queue.popleft()
            component.append(node)
            neighbors = sorted(
                (neighbor for neighbor in adjacency[node] if neighbor in remaining),
                key=lambda judge_id: _stable_key(users_by_id[judge_id]),
            )
            for neighbor in neighbors:
                remaining.remove(neighbor)
                queue.append(neighbor)
        components.append(sorted(component, key=lambda judge_id: _stable_key(users_by_id[judge_id])))
    components.sort(key=lambda component: _stable_key(users_by_id[component[0]]))
    return components


def _jacobi_eigenvalues(matrix):
    """Eigenvalues of a small symmetric matrix via stable Jacobi rotations."""
    a = [row[:] for row in matrix]
    n = len(a)
    if n == 0:
        return []
    if n == 1:
        return [a[0][0]]
    tolerance = 1e-12
    max_rotations = max(1, 100 * n * n)
    for _ in range(max_rotations):
        p, q, largest = 0, 1, abs(a[0][1])
        for i in range(n):
            for j in range(i + 1, n):
                current = abs(a[i][j])
                if current > largest:
                    p, q, largest = i, j, current
        if largest <= tolerance:
            break
        apq = a[p][q]
        tau = (a[q][q] - a[p][p]) / (2.0 * apq)
        sign = 1.0 if tau >= 0.0 else -1.0
        t = sign / (abs(tau) + math.sqrt(1.0 + tau * tau))
        c = 1.0 / math.sqrt(1.0 + t * t)
        s = t * c
        app, aqq = a[p][p], a[q][q]
        a[p][p] = app - t * apq
        a[q][q] = aqq + t * apq
        a[p][q] = a[q][p] = 0.0
        for k in range(n):
            if k in (p, q):
                continue
            akp, akq = a[k][p], a[k][q]
            a[k][p] = a[p][k] = c * akp - s * akq
            a[k][q] = a[q][k] = s * akp + c * akq
    return sorted(a[i][i] for i in range(n))


def _fiedler_value(component, adjacency):
    if len(component) == 1:
        return None
    index = {judge_id: position for position, judge_id in enumerate(component)}
    size = len(component)
    laplacian = [[0.0 for _ in range(size)] for _ in range(size)]
    for judge_id in component:
        i = index[judge_id]
        neighbors = sorted(neighbor for neighbor in adjacency[judge_id] if neighbor in index)
        laplacian[i][i] = float(len(neighbors))
        for neighbor in neighbors:
            laplacian[i][index[neighbor]] = -1.0
    eigenvalues = _jacobi_eigenvalues(laplacian)
    return max(0.0, eigenvalues[1])


def _target_review_count(review_counts, requested_target=None):
    if requested_target is not None:
        target = int(requested_target)
        if target < 1:
            raise ValueError('target_k must be at least 1')
        return target, 'explicit'
    positive = [count for count in review_counts if count > 0]
    if not positive:
        return 1, 'modal_completed_review_count'
    frequencies = Counter(positive)
    # Prefer the higher target if two coverage counts tie in frequency.
    return max(frequencies, key=lambda count: (frequencies[count], count)), 'modal_completed_review_count'


def _rank_group(items):
    ordered = sorted(items, key=lambda item: (-item['normalized_mean'], item['project_key']))
    return {item['project_id']: rank for rank, item in enumerate(ordered, start=1)}


def _decimal_or_none(value):
    if value is None:
        return None
    if not math.isfinite(float(value)):
        return None
    return Decimal(str(value)).quantize(Decimal('0.00000001'))


@transaction.atomic
def run(actor, target_k=None, allow_disconnected_ranking=False):
    """Compute and persist one organizer-authorized normalization snapshot."""
    if not actor.is_organizer or actor.event is None:
        raise PermissionDenied

    projects = list(Project.objects.filter(event=actor.event).select_related('is_duplicate_of'))
    projects.sort(key=_stable_key)
    projects_by_id = {project.pk: project for project in projects}
    duplicate_ids = {project.pk for project in projects if project.is_duplicate_of_id is not None}

    ballots = Ballot.objects.filter(
        assignment__event=actor.event,
        is_complete=True,
    ).select_related(
        'assignment__judge', 'assignment__project',
    ).prefetch_related(
        'scores__criterion',
    ).order_by('pk')

    observations = []
    all_project_observations = defaultdict(list)
    for ballot in ballots:
        project = ballot.assignment.project
        judge = ballot.assignment.judge
        value = _collapse_ballot(ballot)
        if value is None:
            continue
        observation = {
            'ballot_id': ballot.pk,
            'project_id': project.pk,
            'project_key': _project_key(project),
            'judge_id': judge.pk,
            'y': value,
        }
        all_project_observations[project.pk].append(observation)
        if project.pk not in duplicate_ids:
            observations.append(observation)
    # Establish a stable judge identity order independently of query/dict order.
    users_by_id = {ballot.assignment.judge_id: ballot.assignment.judge for ballot in ballots}
    observations.sort(key=lambda item: (
        _stable_key(projects_by_id[item['project_id']]),
        _stable_key(users_by_id[item['judge_id']]),
        item['ballot_id'],
    ))
    observations_by_project = defaultdict(list)
    observations_by_judge = defaultdict(list)
    for observation in observations:
        observations_by_project[observation['project_id']].append(observation)
        observations_by_judge[observation['judge_id']].append(observation)

    review_counts = {
        project.pk: len(all_project_observations.get(project.pk, []))
        for project in projects
    }
    target, target_source = _target_review_count(
        [review_counts[project.pk] for project in projects if project.pk not in duplicate_ids],
        target_k,
    )

    judge_ids = sorted(observations_by_judge, key=lambda judge_id: _stable_key(users_by_id[judge_id]))
    adjacency = {judge_id: set() for judge_id in judge_ids}
    for project_id in sorted(observations_by_project, key=lambda pk: _stable_key(projects_by_id[pk])):
        project_judges = sorted(
            {item['judge_id'] for item in observations_by_project[project_id]},
            key=lambda judge_id: _stable_key(users_by_id[judge_id]),
        )
        for left, right in itertools.combinations(project_judges, 2):
            adjacency[left].add(right)
            adjacency[right].add(left)

    components = _connected_components(judge_ids, adjacency, users_by_id) if judge_ids else []
    component_for_judge = {
        judge_id: component_id
        for component_id, component in enumerate(components, start=1)
        for judge_id in component
    }
    disconnected = len(components) > 1

    # D-05: disconnected groups get independent pools and independent ranks
    # unless the organizer explicitly acknowledges cross-component ranking.
    values_by_component = defaultdict(list)
    for observation in observations:
        component_id = component_for_judge[observation['judge_id']]
        values_by_component[component_id].append(observation['y'])
    global_values = [observation['y'] for observation in observations]
    global_mu = _mean(global_values)
    global_variance = _variance(global_values, global_mu)
    pools = {}
    for component_id in range(1, len(components) + 1):
        values = values_by_component[component_id]
        pools[component_id] = (
            _mean(values) if disconnected else global_mu,
            _variance(values) if disconnected else global_variance,
        )

    judge_stats = {}
    judge_flags = []
    for judge_id in judge_ids:
        judge_observations = observations_by_judge[judge_id]
        ys = [item['y'] for item in judge_observations]
        n_j = len(ys)
        mean_j = _mean(ys)
        variance_j = _variance(ys, mean_j)
        component_id = component_for_judge[judge_id]
        mu0, sigma0_squared = pools[component_id]
        shrunk_mean = (n_j * mean_j + KAPPA0 * mu0) / (n_j + KAPPA0)
        shrunk_variance = (n_j * variance_j + NU0 * sigma0_squared) / (n_j + NU0)
        if not math.isfinite(shrunk_variance) or shrunk_variance < 0:
            raise ValueError(f'Invalid shrunk variance for judge {judge_id}')
        judge_stats[judge_id] = {
            'n': n_j,
            'mean': mean_j,
            'variance': variance_j,
            'shrunk_mean': shrunk_mean,
            'shrunk_variance': shrunk_variance,
            'component_id': component_id,
        }
        if variance_j == 0.0 and n_j >= 2:
            judge = users_by_id[judge_id]
            judge_flags.append({
                'type': 'constant_judge',
                'judge_id': judge_id,
                'judge_external_id': judge.external_id,
                'display_name': judge.display_name,
                'review_count': n_j,
                'variance': 0.0,
            })

    contributions = defaultdict(list)
    z_values_by_project = defaultdict(list)
    for observation in observations:
        judge_id = observation['judge_id']
        stats = judge_stats[judge_id]
        variance = stats['shrunk_variance']
        # Constant-event fallback: all ratings coincide, so every z is zero.
        z_value = 0.0 if variance <= 0.0 else (observation['y'] - stats['shrunk_mean']) / math.sqrt(variance)
        if not math.isfinite(z_value):
            raise ValueError('Normalization produced a non-finite z-score')
        z_values_by_project[observation['project_id']].append(z_value)
        judge = users_by_id[judge_id]
        contributions[observation['project_id']].append({
            'judge_id': judge_id,
            'judge_external_id': judge.external_id,
            'z_score': z_value,
        })

    normalized_by_project = {}
    for project_id in sorted(observations_by_project, key=lambda pk: _stable_key(projects_by_id[pk])):
        project = projects_by_id[project_id]
        component_ids = sorted({component_for_judge[item['judge_id']] for item in observations_by_project[project_id]})
        component_id = component_ids[0]
        mu0, sigma0_squared = pools[component_id]
        project_z = _mean(z_values_by_project[project_id])
        normalized = mu0 + project_z * math.sqrt(max(0.0, sigma0_squared))
        normalized = min(5.0, max(1.0, normalized))
        if not math.isfinite(normalized):
            raise ValueError('Normalization produced a non-finite project score')
        normalized_by_project[project_id] = {
            'normalized_mean': normalized,
            'component_id': component_id,
        }

    rankable = defaultdict(list)
    for project_id, values in normalized_by_project.items():
        project = projects_by_id[project_id]
        rank_scope = 0 if allow_disconnected_ranking else values['component_id']
        rankable[rank_scope].append({
            'project_id': project_id,
            'project_key': _project_key(project),
            'normalized_mean': values['normalized_mean'],
        })
    ranks = {}
    for scope in sorted(rankable):
        ranks.update(_rank_group(rankable[scope]))

    project_flags = {}
    for project in projects:
        key = _project_key(project)
        flags = []
        if project.pk in duplicate_ids:
            flags.append({
                'type': 'duplicate',
                'excluded_from_ranking': True,
                'duplicate_of': _project_key(project.is_duplicate_of),
            })
        count = review_counts[project.pk]
        if count < target:
            flags.append({
                'type': 'thin_batch',
                'review_count': count,
                'target_k': target,
            })
        for observation in observations_by_project.get(project.pk, []):
            judge_flag = next((flag for flag in judge_flags if flag['judge_id'] == observation['judge_id']), None)
            if judge_flag is not None:
                flags.append({
                    'type': 'constant_judge',
                    'judge_id': judge_flag['judge_id'],
                    'judge_external_id': judge_flag['judge_external_id'],
                    'display_name': judge_flag['display_name'],
                })
        # A judge appears at most once per project; stable de-duplication keeps
        # the project reference to its flag separate from the thin-batch flag.
        deduped = []
        seen = set()
        for flag in flags:
            marker = (flag['type'], flag.get('judge_id'), flag.get('duplicate_of'))
            if marker not in seen:
                seen.add(marker)
                deduped.append(flag)
        project_flags[key] = deduped

    component_reports = []
    component_fiedler = {}
    for component_id, component in enumerate(components, start=1):
        fiedler = _fiedler_value(component, adjacency)
        component_fiedler[component_id] = fiedler
        component_reports.append({
            'component_id': component_id,
            'judge_ids': component,
            'judge_external_ids': [users_by_id[judge_id].external_id for judge_id in component],
            'judge_count': len(component),
            'project_ids': sorted({
                _project_key(projects_by_id[item['project_id']])
                for judge_id in component
                for item in observations_by_judge[judge_id]
            }),
            'fiedler_value': fiedler,
            'pooled_mean': pools[component_id][0],
            'pooled_variance': pools[component_id][1],
        })

    parameters = {
        'kappa0': KAPPA0,
        'nu0': NU0,
        'target_k': target,
        'target_k_source': target_source,
        'allow_disconnected_ranking': bool(allow_disconnected_ranking),
        'ranking_scope': 'global' if not disconnected or allow_disconnected_ranking else 'component',
        'pooled_mean': global_mu,
        'pooled_variance': global_variance,
        'component_count': len(components),
        'components': component_reports,
        'judge_flags': judge_flags,
        'judge_statistics': [
            {
                'judge_id': judge_id,
                'judge_external_id': users_by_id[judge_id].external_id,
                'n': judge_stats[judge_id]['n'],
                'raw_variance': judge_stats[judge_id]['variance'],
                'shrunk_variance': judge_stats[judge_id]['shrunk_variance'],
                'component_id': judge_stats[judge_id]['component_id'],
            }
            for judge_id in judge_ids
        ],
        'project_flags': project_flags,
        'project_review_counts': {_project_key(project): review_counts[project.pk] for project in projects},
        'contributions': {
            _project_key(projects_by_id[project_id]): contributions[project_id]
            for project_id in sorted(contributions, key=lambda pk: _stable_key(projects_by_id[pk]))
        },
    }
    # Fail closed if any future calculation accidentally introduces NaN/Inf;
    # Python's default JSON encoder would otherwise persist these non-standard values.
    json.dumps(parameters, allow_nan=False)
    run_record = NormalizationRun.objects.create(
        event=actor.event,
        computed_at=timezone.now(),
        method_name=METHOD_NAME,
        parameters=parameters,
    )

    normalized_rows = []
    for project in projects:
        project_observations = all_project_observations.get(project.pk, [])
        raw_mean = _mean(item['y'] for item in project_observations) if project_observations else None
        normalized = normalized_by_project.get(project.pk)
        component_id = normalized['component_id'] if normalized else None
        normalized_rows.append(NormalizedScore(
            run=run_record,
            project=project,
            raw_mean=_decimal_or_none(raw_mean),
            normalized_mean=_decimal_or_none(normalized['normalized_mean']) if normalized else None,
            rank=ranks.get(project.pk),
            judge_graph_component_id=component_id,
            judge_graph_fiedler_value=component_fiedler.get(component_id) if component_id else None,
        ))
    NormalizedScore.objects.bulk_create(normalized_rows)
    return run_record


def get_run(actor, run_id):
    if not actor.is_organizer or actor.event is None:
        raise PermissionDenied
    return NormalizationRun.objects.get(pk=run_id, event=actor.event)


def normalized_score_payload(score):
    """Serialize a normalized row with its run-scoped warnings and review count."""
    project_key = _project_key(score.project)
    parameters = score.run.parameters
    return {
        'project_id': project_key,
        'raw_mean': str(score.raw_mean) if score.raw_mean is not None else None,
        'normalized_mean': str(score.normalized_mean) if score.normalized_mean is not None else None,
        'rank': score.rank,
        'judge_graph_component_id': score.judge_graph_component_id,
        'judge_graph_fiedler_value': score.judge_graph_fiedler_value,
        'review_count': parameters.get('project_review_counts', {}).get(project_key, 0),
        'flags': parameters.get('project_flags', {}).get(project_key, []),
    }


def normalized_output_bytes(run_record):
    """Canonical normalized-score bytes, excluding generated row/run IDs."""
    rows = run_record.scores.select_related('project').order_by('project_id')
    payload = []
    for row in rows:
        payload.append({
            'project_id': _project_key(row.project),
            'raw_mean': str(row.raw_mean) if row.raw_mean is not None else None,
            'normalized_mean': str(row.normalized_mean) if row.normalized_mean is not None else None,
            'rank': row.rank,
            'component_id': row.judge_graph_component_id,
            'fiedler_value': row.judge_graph_fiedler_value,
        })
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def build_proof_artifact(run_record):
    """Return a deterministic CSV proof table that can be written offline."""
    score_rows = list(run_record.scores.select_related('project').order_by('project_id'))
    params = run_record.parameters
    flags = params.get('project_flags', {})
    review_counts = params.get('project_review_counts', {})
    raw_rank_groups = defaultdict(list)
    for row in score_rows:
        if row.rank is None or row.raw_mean is None or row.normalized_mean is None:
            continue
        scope = 0 if params.get('ranking_scope') == 'global' else row.judge_graph_component_id
        raw_rank_groups[scope].append(row)
    raw_ranks = {}
    for scope, rows in raw_rank_groups.items():
        ordered = sorted(rows, key=lambda row: (-float(row.raw_mean), _stable_key(row.project)))
        raw_ranks.update({row.project_id: rank for rank, row in enumerate(ordered, start=1)})

    output = io.StringIO(newline='')
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow(['project_id', 'raw_mean', 'normalized_mean', 'raw_rank', 'normalized_rank', 'rank_change', 'review_count', 'flags'])
    for row in score_rows:
        project_key = _project_key(row.project)
        raw_rank = raw_ranks.get(row.project_id)
        rank_change = raw_rank - row.rank if raw_rank is not None and row.rank is not None else None
        writer.writerow([
            project_key,
            str(row.raw_mean) if row.raw_mean is not None else '',
            str(row.normalized_mean) if row.normalized_mean is not None else '',
            raw_rank if raw_rank is not None else '',
            row.rank if row.rank is not None else '',
            rank_change if rank_change is not None else '',
            review_counts.get(project_key, 0),
            json.dumps(flags.get(project_key, []), sort_keys=True, separators=(',', ':'), allow_nan=False),
        ])
    return output.getvalue().encode('utf-8')
