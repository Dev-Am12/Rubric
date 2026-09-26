# DogFood 2026 — Assignment Algorithm & Graph Health (backlog item 4)

**Rev 2 · 2026-09-25 · Status: design only, no code yet — incorporates a fix from STRESS-TEST.md (F9)**
Depends on SCHEMA.md (`JudgeAssignment`) and NORMALIZATION.md (D-05, graph connectivity policy). This is also priority #1 of the signature-feature order (DL-019) — it's built as core T2/JUDGING.md work regardless, because it's nearly free once the model exists, not deferred as a "someday" extra.

**Scope clarification, stated up front to avoid confusion later:** this algorithm assigns judges to **new** submissions in a live event (the organizer's own future use, or any projects/judges added after fixture import). The real fixture's 126 existing scores are **imported as already-completed history** (`JudgeAssignment.status=COMPLETED`, backfilled directly from `scores[]` per SCHEMA.md §2) — this algorithm never runs against them, and never reshuffles them. Re-running assignment only ever adds new `JudgeAssignment` rows for projects/judges that don't have enough coverage yet; it never touches an assignment that already has a submitted `Ballot`.

---

## 1. Policies (stated before implementation, same discipline as NORMALIZATION.md)

**A-01 — Track eligibility is a hard constraint, never a preference.** A judge is only ever assigned to a project whose track is in the judge's `tracks` list (SCHEMA.md's `EventMembership`/judge-track relation). No exceptions, no "close enough."

**A-02 — Conflict of interest is a hard constraint.** A judge who is a `TeamMembership` of a project's team is never assigned to that project, full stop. (The real fixture has zero such cases — RESEARCH §2B — but the check runs regardless, because a live event's data won't be curated the way the fixture is.)

**A-03 — Load is balanced, not just "eventually even."** The algorithm actively minimizes the spread between the most- and least-loaded eligible judge at every assignment step, not just on average across the whole run. We do **not** reproduce the real fixture's own load pattern (1 to 11 reviews per judge, RESEARCH §2B) — that's historical, imported data, not a model to imitate.

**A-04 — Under-coverage is reported, never hidden.** If a track has too few eligible judges to give every project *k* reviews, the shortfall is surfaced on the organizer dashboard by name (which projects, how short) rather than silently assigning fewer reviews with no signal.

**A-05 — Connectivity is measured and reported on every run, never assumed.** Multi-track judges are used as deliberate connectivity anchors where they exist; where they don't, a genuinely disconnected result is reported honestly (feeds NORMALIZATION.md's D-05), not forced together.

**A-06 — Assignment is idempotent and additive.** Re-running assignment (e.g., after adding a late judge) only fills gaps — it never removes or reshuffles an assignment that already has a ballot attached, submitted or in progress.

**A-07 — Randomness is seeded and logged.** Tie-breaking among equally-loaded, equally-eligible judges is randomized (avoids a systematic bias toward whichever judge happens to sort first), but the seed is recorded on the `AssignmentRun` row so a given run is exactly reproducible for audit purposes.

---

## 2. The algorithm

### 2.1 New model: `AssignmentRun` (added to SCHEMA.md §1.2)
| field | type | notes |
|---|---|---|
| id, event_id | | |
| run_at | timestamp | |
| target_k | int | reviews-per-project target for this run |
| seed | int | for A-07 |
| under_coverage | JSON | list of `{project_id, got, wanted}` — A-04 |
| connectivity_report | JSON | component count, sizes, Fiedler value(s) — A-05 |

### 2.2 Per-track greedy assignment with load balancing
```
def run_assignment(event, k, seed):
    rng = Random(seed)
    under_coverage = []
    for track in event.tracks:
        eligible = [j for j in event.judges if track in j.tracks]
        projects = [p for p in track.projects if p.status == SUBMITTED]
        rng.shuffle(projects)               # A-07: order doesn't bias who gets reviewed "first"
        load = {j: current_assignment_count(j) for j in eligible}   # A-06: starts from existing state, additive
        for project in projects:
            existing = current_reviewer_count(project)
            needed = max(0, k - existing)
            conflicted = team_members(project.team)
            candidates = sorted(
                (j for j in eligible if j not in conflicted and not already_assigned(j, project)),
                key=lambda j: (load[j], rng.random())         # A-03: min-load first, randomized tie-break
            )
            picked = candidates[:needed]
            for j in picked:
                create JudgeAssignment(judge=j, project=project, status=PENDING)
                load[j] += 1
            if len(picked) < needed:
                under_coverage.append({project: project.id, got: existing + len(picked), wanted: k})   # A-04
    connectivity = compute_graph_health(event)                  # A-05, §2.3
    save AssignmentRun(event, k, seed, under_coverage, connectivity)
```

### 2.3 Graph health (`compute_graph_health`, priority #1 signature feature — DL-019)
```
def compute_graph_health(event):
    # adjacency: two judges linked if they share a reviewed project (PENDING or COMPLETED)
    A = build_adjacency_matrix(event.judge_assignments)
    L = degree_matrix(A) - A                         # graph Laplacian
    eigenvalues = numpy.linalg.eigvalsh(L)            # symmetric, so eigvalsh (real, sorted) not eig
    n_components = count(eigenvalues < 1e-9)          # standard spectral fact: multiplicity of eigenvalue 0
    components = connected_components_via_bfs(A)      # same construction we used in RESEARCH §2B
    report = {
        "n_components": n_components,
        "component_sizes": [len(c) for c in components],
        "fiedler_value_global": eigenvalues[1] if n_components == 1 else 0.0,
        "fiedler_value_per_component": [
            (fiedler(subgraph(A, c)) if len(c) > 1 else None)   # fixed by the stress test, F9: a 1-node component has no "second-smallest eigenvalue" — report null, not 0 or a crash
            for c in components
        ],
    }
    return report
```
Cheap: ~30 nodes, `numpy.linalg.eigvalsh` on a dense 30×30 Laplacian is sub-millisecond. This report is what feeds both JUDGING.md's assignment defense and, per the Best Judging Engine prize's own stated criteria ("most defensible assignment, normalization and isolation"), a direct answer to that specific prize.

### 2.4 Anchor injection (only via judges who are already multi-track — never fabricated)
If `n_components > 1` after the main pass, check whether any judge is eligible for tracks spanning two different components (the real fixture shows 9 of 30 judges are genuinely multi-track — RESEARCH §2B — this is the natural mechanism, not a workaround). If such a judge exists and is under the mean load + 1, give them one additional assignment bridging the two components; recompute connectivity. **This never fabricates eligibility** — a track pairing with zero shared-eligible judges stays genuinely disconnected and is reported as such (A-05), not artificially merged.

---

## 3. Planted-truth test specs

| # | Test | Setup | Assertion |
|---|---|---|---|
| A1 | `test_track_eligibility_never_violated` | Any event, any judge/project mix | No `JudgeAssignment` row exists where `track(project) not in judge.tracks` |
| A2 | `test_conflict_of_interest_never_assigned` | A synthetic case: a judge who is also on the project's team | That judge is never assigned to that project, even if they're the only eligible one left (project shows up in `under_coverage` instead) |
| A3 | `test_load_balanced_within_bound` | A track with 10 eligible judges, 30 projects, k=3 | `max(load) - min(load) <= 1` at the end of the run |
| A4 | `test_under_coverage_reported_not_hidden` | A track with only 2 eligible judges but k=3 | Every project in that track appears in `under_coverage` with the correct `got`/`wanted`; no project silently ships with fewer reviews and no flag |
| A5 | `test_assignment_additive_never_reshuffles` | Run assignment once, submit a ballot for one assignment, run again with a new judge added | The submitted-ballot assignment is untouched; only new gaps get new assignments |
| A6 | `test_anchor_injection_only_via_real_multitrack_judges` | Synthetic: two tracks, no shared judges → then add one genuinely multi-track judge | Without the anchor judge: 2 components reported honestly. With: 1 component, and the bridging assignment is traceable to that specific judge in the `AssignmentRun` record |
| A7 | `test_deterministic_given_seed` | Same event, same seed, run twice (as two separate `AssignmentRun`s on a fresh copy of the same pre-state) | Identical resulting assignments |
| A8 | `test_graph_health_matches_manual_bfs_on_real_fixture` | Load the real fixture's 126 scores as completed assignments (not generated by this algorithm — see scope note) | `compute_graph_health` reports exactly 1 component of size 30 — matching the BFS result we already computed by hand in RESEARCH §2B, as a cross-check that the shipped code agrees with our own manual verification |

---

## 4. Open items for G3

- Whether `target_k` is fixed per event or per-track (a track with very few submissions might reasonably want a smaller k) — leaning per-event default with a per-track override, low cost to add once the model exists.
- Whether under-coverage automatically triggers an organizer notification (T4-adjacent, webhook territory) or is dashboard-only for the submission — dashboard-only by default, matches the "one command, no extra services" adoptability stance.
