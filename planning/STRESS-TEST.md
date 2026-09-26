# DogFood 2026 — Stress Test Report

**Rev 1 · 2026-09-25 · ~8h before kickoff**
Full re-read of every design file (SCHEMA, AUTHZ, NORMALIZATION, ASSIGNMENT, VOTING, API, DOCKER, UX, DOCS-PLAN, PROMPTS, SCHEDULE, PLAN, RESEARCH), checked against each other and against spec.md, looking specifically for contradictions, gaps, and things that would silently break. This is not a rubber stamp — every item below is a real finding, not a formality. Fixes are applied directly to the affected files; this doc is the record of what was wrong and why.

---

## CRITICAL — would have failed a required acceptance check

### F1. `services.judging.get_scores` was broken in both places it was written, in two different ways
- **SCHEMA.md's version** never checked whether the actor was a judge at all. A `participant` calling `GET /api/judge/scores` with no `?judge=` param would compute `target = None`, hit `target != actor.judge_id` → `None != None` → **False**, skip the permission check entirely, and return `200` with an empty queryset. **This is the literal T2 "participant blocked" check — it would have failed the official acceptance report.**
- **AUTHZ.md's version** added a fix (`if actor.judge_id is None: raise PermissionDenied`) but that fix went too far: it also blocks **organizers**, since most organizers aren't judges — but the route×persona table right above it says organizers get `200 (all)`. The fix broke a different row of its own table.
- Neither file's function distinguishes "resolve to my own scores" from "an organizer requesting anyone's/everyone's scores."
- **Fix applied**: one corrected function, used identically in both files now:
```
def get_scores(actor, judge_external_id=None):
    if actor.is_organizer:
        if judge_external_id:
            return Ballot.objects.filter(assignment__judge__external_id=judge_external_id, assignment__event=actor.event)
        return Ballot.objects.filter(assignment__event=actor.event)
    if not actor.is_judge:
        raise PermissionDenied
    target = judge_external_id or actor.judge_external_id
    if target != actor.judge_external_id:
        raise PermissionDenied
    return Ballot.objects.filter(assignment__judge__external_id=target, assignment__event=actor.event)
```
Also fixes a type bug: the old version filtered `assignment__judge_id=target` where `target` is an external-id-shaped string (e.g. `"jdg_07"`) against what SCHEMA defines as an internal integer FK — compared unlike types. Now resolves through `judge__external_id`.
- **401 vs 403 mapping**, stated explicitly now (was implicit): the view/exception-handler layer, not the service function, distinguishes them — `AnonymousActor` + `PermissionDenied` → 401; a resolved real `Actor` + `PermissionDenied` → 403. The service function only ever raises one exception type; it doesn't know which HTTP code that becomes.

---

## HIGH — real contradictions between design files

### F2. SCHEMA.md had the duplicate-submission direction backwards
SCHEMA.md's Rev-1 inline comment said `is_duplicate_of` is set on **`prj_41`** (pointing at `prj_07`). But NORMALIZATION.md's D-02 (refined in a later session, DL-026), VOTING.md's V-07/V-T6, and DOCS-PLAN.md's storyboard all correctly have it the other way: **the earlier `prj_07` is flagged, pointing at the later, canonical `prj_41`.** SCHEMA.md's comment was simply never updated when the policy was refined — a real instance of exactly the drift this stress test exists to catch. **Fixed** — SCHEMA.md now matches the authoritative direction everywhere.

### F3. No model actually stores judge–track eligibility
AUTHZ.md (A-01's hard constraint), ASSIGNMENT.md (the whole algorithm's first filter), and VOTING.md all reference "the judge's `tracks` list" as if SCHEMA.md defines it. **It never did.** The real fixture's `judges[]` array literally carries a `tracks` array per judge, and there was nowhere for it to land. **Fixed** — added `JudgeTrackEligibility(event_membership_id, track_id)` to SCHEMA.md §1.1/§1.2, wired into the import mapping (§2) and the Django app layout.

### F4. Docker: the environment plan assumed a local machine that no longer exists
Not a bug I found — the owner's own news — but it invalidates DOCKER.md §6 (V9, "fresh clone on a Windows machine") and PLAN §5.4 outright. Full rewrite below (§"Docker strategy, revised").

---

## MEDIUM — real gaps, wouldn't fail the suite but would weaken the submission or confuse the build

### F5. `AuthToken` stored raw tokens; `ApiToken` (a near-identical model) correctly used `token_hash`
Inconsistent security posture between two structurally similar models in the same schema — a stray DB read would leak live session tokens for `AuthToken` but not for `ApiToken`. **Fixed** — `AuthToken.token_hash` now, same pattern as passwords: the raw value is shown once (printed at boot / set as the cookie), never stored.

### F6. The normalization pipeline never said how a multi-criterion ballot becomes one number
`y_ij` appears in the shrinkage formula as if it's already a scalar, but a `Ballot` has multiple `BallotScore` rows (one per `RubricCriterion`), and T2 explicitly requires "a weighted scoring rubric the organizer can configure." Nothing connected the organizer's weights to the math. **Fixed** — added an explicit step 0 to NORMALIZATION.md §2.2: `y_ij = Σ(BallotScore.value × RubricCriterion.weight) / Σ(RubricCriterion.weight)`, computed **before** any cross-judge normalization.

### F7. The audit-log hash chain had no concurrency handling
A linear hash chain (`previous_hash`/`current_hash`) under concurrent inserts can race — two transactions computing a hash against the same "previous" row corrupts the chain. Not exercised by our real usage pattern (a solo organizer, low write volume) but a real correctness gap in a feature we're specifically submitting as evidence of rigor. **Fixed** — SCHEMA.md now specifies an advisory lock (`pg_advisory_xact_lock`) taken at the start of the insert trigger, serializing chain writes without serializing the whole table.

### F8. `AssignmentRun` couldn't actually prove what ASSIGNMENT.md's own test A6 requires
A6 requires the anchor-bridging assignment to be "traceable in the `AssignmentRun` record," but the model had no field to record it. **Fixed** — added `anchor_injections: JSON` (`[{judge_external_id, bridged_components: [...]}]`) to `AssignmentRun`.

### F9. `compute_graph_health`'s per-component Fiedler value undefined for singleton components
A connected component of exactly one judge has a 1×1 Laplacian — "second-smallest eigenvalue" doesn't exist. Unhandled, this either crashes or silently returns garbage. **Fixed** — ASSIGNMENT.md now specifies `fiedler_value: null` (not `0`) for any component of size 1, stated explicitly rather than left to be discovered mid-build.

### F10. A phantom "results public after close (config)" appeared in two places with nothing backing it
API.md's endpoint table and VOTING.md's test V-T3 both say results go public "per event config" after voting closes — but V-02's own stated logic never mentions a config flag, and no such field exists on `Event`. **Fixed** — simplified to the one real rule V-02 already describes: results are organizer-only during the window, public to everyone once it closes, no separate toggle. Removed "(config)" from both files.

### F11. VOTING.md pointed at a `THREAT-MODEL.md` file that was explicitly decided not to exist
DOCS-PLAN.md folded the threat model into `JUDGING.md §6` specifically to avoid two files making the same claims (the exact doc-drift risk this stress test is about). VOTING.md's own open item still referenced the old filename. **Fixed** — corrected the reference.

---

## LOW — precision fixes, not bugs

### F12. `Actor` should expose per-role booleans, not an implied singular `.role`
`EventMembership`'s own unique constraint (`event, user, role`) explicitly allows one user to hold multiple roles in the same event. AUTHZ.md's Actor description implied a singular `.role`. **Fixed** — `Actor` exposes `is_participant`/`is_judge`/`is_organizer` independently.

### F13. The shrinkage formula should be labeled a heuristic, not claimed as a rigorous posterior
It's a defensible, standard-shaped pragmatic shrinkage estimator, not a full hierarchical Bayesian model with a derived posterior. Claiming more than that risks a stats-literate judge poking a real hole in JUDGING.md. **Fixed** — NORMALIZATION.md/DOCS-PLAN's JUDGING.md outline now say "a pragmatic shrinkage estimator inspired by empirical-Bayes methods," not "the empirical-Bayes posterior."

### F14. The synthetic normalization test needs a fixed seed
`test_shrinkage_beats_raw_on_synthetic_ground_truth` generates random judges/noise — without a fixed seed this is flaky, and flaky tests undermine the determinism principle we hold everything else to. **Fixed** — noted in NORMALIZATION.md's test table.

### F15. Fixture-imported ballots have no natural `submitted_at` value
`fixtures.json`'s `scores[]` records carry no timestamp at all. **Fixed** — policy: `Ballot.submitted_at` = the import run's own timestamp for fixture-derived ballots, documented in DATA-MODEL.md as provenance ("this data existed as of import"), not a real judging-time claim.

---

## Docker strategy, revised (the owner's news: no local machine can run Docker at all)

This changes more than DOCKER.md §6 — it changes the whole dev loop.

**What's still true:** DOCKER.md §§2–5 (the compose file, Dockerfile, entrypoint, CI workflow) are unaffected — they were never designed assuming local Docker, only *verified* that way. What breaks is purely how we develop and verify them without any local Docker at all.

**The revised plan:**
1. **Install PostgreSQL natively (not via Docker) on the dev machine, today, before kickoff.** This is the single highest-leverage thing to do in the remaining ~8 hours — it gives a fast local dev loop (`python manage.py runserver` against a real local Postgres) with full parity to what ships in the container (same DB engine, same `pgcrypto` availability for the audit-log hash chain), and removes almost all the "works locally, fails in the container" risk that a Docker-less setup would otherwise create. **I don't know your OS or whether you have install permissions — this is the one thing in this whole session I'd genuinely ask you to confirm rather than assume.**
2. **The repo goes public from kickoff (T-0), not just at submission.** Spec.md requires it public "at submission," not from day one, but there's no reason to wait — a public repo gets **unlimited GitHub Actions minutes**, whereas a private one is capped (2,000 min/month on a free personal account). Since Actions is about to become our *primary* Docker-verification mechanism (not an occasional check), unlimited minutes matters a lot more now than it did in the original plan.
3. **GitHub Actions becomes the primary, frequent Docker verification loop.** DOCKER.md §5's clean-room + offline-check jobs already exist — the change is cadence: push often (every meaningful step, not just at gate boundaries), and treat a green Actions run as the actual proof that the containerized app works, since we have no other way to know.
4. **A free, interactive fallback for when Actions logs alone aren't enough**: a manually-triggered CI step using an SSH-into-the-runner action (e.g. `mxschmitt/action-tmate`) gives a real interactive shell on a genuine Docker-capable Linux host, on demand, at zero cost beyond the Actions minutes already free on a public repo. This substitutes for "poke around inside the container" without touching the Codespaces budget at all.
5. **GitHub Codespaces, budgeted deliberately** (120 free core-hours/month): reserved for (a) one early session right after the skeleton exists, specifically to prove the compose/entrypoint/healthchecks actually boot on a real Docker host *before* building the rest of the app on top of an unverified skeleton, and (b) the final pre-freeze end-to-end dry run. Estimated need: 5–7 hours of actual session time total — well inside the free allowance, provided sessions are stopped when not in active use (Codespaces bills/counts only while running).
6. **V9 (second-environment check) is redefined, not dropped**: a literal Windows-Docker-Desktop test is no longer possible, and that's a real, honest gap — not fully replaceable. Two partial mitigations: every Actions run is already a fresh, ephemeral Linux VM (catches "only worked because of local leftover state," just not Windows-specific issues), and the compose design (§2 of DOCKER.md) never bind-mounts source into the container — everything is `COPY`'d in at build time — which sidesteps the single most common Windows-Docker-Desktop friction point (bind-mount permission/performance bugs) even though it can't rule out something else Windows-specific we haven't thought of. **README's honest-limitations section should say this plainly**: "not tested on Windows directly; the design avoids the most common Windows-Docker friction points, but this isn't a substitute for testing." This is exactly the kind of disclosure spec.md rewards, not just risk management.

---

## What's confirmed solid (no issues found)
The core service-layer/policy-layer architecture, the `peer_scores` isolation design once F1 is fixed, the `VoteAttempt`/`Vote` split, the fixture import's `external_id` provenance strategy, the tier-gating CI rule (V10), the route×role matrix mechanism and its control case, the empirical-Bayes shrinkage math itself (formula is correct, just needed the F6 pipeline connection and the F13 framing), the graph-connectivity approach, and the overall gate/schedule structure all held up under scrutiny.

---

## Open question for the owner (the one thing I can't resolve myself)
**Can you install PostgreSQL natively (no Docker) on your dev machine, and what OS is it?** This is the one recommendation above that depends on something I have no way to verify — everything else in this report is fixed or is a documented, defensible design choice.
