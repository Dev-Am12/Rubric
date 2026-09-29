# DogFood 2026 — Authorization Matrix & Policy Layer (backlog item 2)

**Rev 2 · 2026-09-25 · Status: design only, no code yet — incorporates fixes from STRESS-TEST.md (F1, F12)**
Depends on SCHEMA.md (entities, service boundaries, `AuthToken`). This is the design that has to hold up against a `curl` — spec.md's own words: "if I can curl another judge's scores it is not isolation."

---

## 1. Actor resolution (how a raw header becomes a checked identity)

```
AuthMiddleware:
    token_str = extract_from_header(request)   # "Cookie: session=X" or "Authorization: Bearer X"
    if not token_str:
        request.actor = AnonymousActor()        # = "visitor" in T1's role list
        return
    token = AuthToken.objects.select_related("user").get_or_none(token=token_str)
    if token is None or token.is_expired:
        request.actor = AnonymousActor()
        return
    request.actor = Actor(user=token.user, event=current_event())  # resolves .is_participant/.is_judge/.is_organizer/.judge_external_id independently from EventMembership — never a singular .role, since EventMembership's own unique(event, user, role) explicitly allows one user to hold more than one role
```
`Actor` is a thin, read-only wrapper — it is **not** the Django user object, precisely so every service function takes an `Actor` and nothing can accidentally bypass it by reaching for `request.user` out of habit. `AnonymousActor.is_participant = .is_judge = .is_organizer = False` — every check defaults closed. (Corrected by the stress test, F12: an earlier draft implied a single `.role` field, which can't represent a user holding two roles at once — a case the schema explicitly allows.)

**No view or API handler ever checks `request.actor.role` directly and then queries the model.** Every check happens inside a `services.*` function, which is the only thing views are allowed to call for anything beyond a fully-public read (the gallery). This is what makes the matrix below enforceable by a single test suite rather than a promise about UI discipline.

---

## 2. Personas used for testing (fixed set, matches SCHEMA.md §2's real mapping where possible)

| Persona | Concretely | AuthToken |
|---|---|---|
| `anon` | no header at all | none |
| `participant_owner` | member of team `tm_07` | seeded `participant` token |
| `participant_other` | a different team's member, not `tm_07` | a second seed token, test-only |
| `judge_a` (assigned) | `jdg_07`, assigned to `prj_09/17/19` | seeded `judge_a` token |
| `judge_b` (assigned, different projects) | `jdg_29` | seeded `judge_b` token |
| `judge_unassigned` | a judge with zero assignments to the project under test | test-only token |
| `organizer` | dedicated seed account | seeded `organizer` token |
| `site_admin` | `User.is_site_admin=True` | test-only token, not part of the required four but part of T1's role list |

---

## 3. The route × persona matrix

Status legend: **200** = success, **403** = authenticated but forbidden, **401** = would-be-authenticated-but-token-invalid (we treat missing/garbage tokens as 401, a resolved-but-wrong-role actor as 403 — matches spec.md accepting either for the two isolation checks), **404** = deliberately don't even reveal existence (used sparingly, see note below), **N/A** = route doesn't apply to this object state (e.g. editing a submitted project as a non-owner).

### 3.1 Gallery & submissions (T1)

| Route | anon | participant_owner | participant_other | judge_a | organizer |
|---|---|---|---|---|---|
| `GET /projects` (gallery, submitted only) | 200 | 200 | 200 | 200 | 200 |
| `GET /projects/{draft_id}` (a **draft**, not yet submitted) | 403 | 200 (own) | 403 | 403 | 200 |
| `POST /projects/new` (submit) | 401 | 200 | 200 (own team) | 403 | 403 (organizers don't submit) |
| `PATCH /projects/{id}` (edit, before deadline) | 401 | 200 (own) | 403 | 403 | 200 |
| `PATCH /projects/{id}` (edit, **after** deadline) | 401 | 403 (4xx — the literal T1 check) | 403 | 403 | 200 (organizer override, logged) |

**Note on the draft-visibility row:** this is new relative to our earlier notes — the gallery check (`run.py`'s "gallery is public") only requires that *a submitted* fixture project's title appears; it says nothing about drafts. Leaving drafts out of the public gallery is a Code-Quality/Judging-Integrity-adjacent choice (a half-finished idea shouldn't leak to competitors) and costs nothing against the suite, since all 41 real fixture projects import as already-`SUBMITTED`.

### 3.2 Judging (T2 — this is the section that matters most)

| Route | anon | participant_owner | judge_a (`jdg_07`) | judge_b (`jdg_29`) | judge_unassigned | organizer |
|---|---|---|---|---|---|---|
| `GET /api/judge/scores` (own, no `?judge=`) | 401 | 403 | **200**, sees only `jdg_07`'s ballots | 403 | **200**, empty result | 200 (all) |
| `GET /api/judge/scores?judge=jdg_07` (as `jdg_07`, i.e. self) | — | — | **200** (identity matches) | — | — | 200 |
| **`GET /api/judge/scores?judge=jdg_07` as `judge_b`** | — | — | — | **403 — the exact spec.md check** | — | — |
| `GET /api/judge/scores?judge=<other judge id>` as `judge_unassigned` | — | — | — | — | **403**; without `?judge=`, their own list is **200** with no ballots | — |
| `POST /judging/ballots/{assignment_id}` (submit a score) | 401 | 403 | 200, only for `jdg_07`'s own assignments | 200, only for `jdg_29`'s own | 403 (no assignment exists) | 403 (organizers don't score) |
| `GET /organizer/progress` (live dashboard) | 401 | 403 | 403 | 403 | 403 | 200 |
| `POST /organizer/assignments` (assign judges) | 401 | 403 | 403 | 403 | 403 | 200 |
| `POST /organizer/normalization/run` | 401 | 403 | 403 | 403 | 403 | 200 |
| `GET /api/export.csv` | 401 | 403 | 403 | 403 | 403 | **200** (the literal T1/T2 check) |

**The single function this whole section routes through** (from SCHEMA.md §1.2 — corrected by the stress test, F1: an earlier version here let an organizer-who-isn't-a-judge get wrongly denied, contradicting the "organizer sees all" row above; SCHEMA.md's own earlier version had the opposite bug, letting a participant through with an empty 200 instead of a 403):
```
services.judging.get_scores(actor, judge_external_id=None):
    if actor.is_organizer:
        if judge_external_id:
            return Ballot.objects.filter(assignment__judge__external_id=judge_external_id, assignment__event=actor.event)
        return Ballot.objects.filter(assignment__event=actor.event)
    if not actor.is_judge:
        raise PermissionDenied
    if judge_external_id and judge_external_id != actor.judge_external_id:
        raise PermissionDenied
    return Ballot.objects.filter(assignment__judge=actor.user, assignment__event=actor.event)
```
The own-score query filters by the authenticated user because non-fixture judges may have `external_id=None`; filtering by that value would collide and expose other such judges' ballots.
Both `routes.judge_scores` and `routes.peer_scores` in `.dogfood.toml` point at the same URL pattern with an optional query parameter — there is exactly **one** function where the check can be forgotten, and it's covered by two dedicated tests named after the real spec.md check ("judge cannot see peer scores") plus the generic matrix below.

### 3.3 Public voting (T3 — mechanisms are exercised in voting tests and manually demonstrable)

OPEN and AUTH are the only modes. Anonymous users may read/cast/comment only in OPEN mode; authenticated users may do so in either mode. Organizers cannot cast votes or comments. A closed or unopened window rejects writes. Bearer-authenticated POSTs use the existing CSRF split; anonymous browser POSTs require a CSRF token.

| Route | anonymous, OPEN during window | authenticated participant/judge during window | organizer during window | anonymous after close | authenticated after close | organizer any time |
|---|---|---|---|---|---|---|
| `GET /vote/{event}` | 200 (401 if mode is AUTH) | 200 | 200 | 200 | 200 | 200 |
| `POST /vote/{event}/{project}` | 201 if accepted; service rejection status otherwise; closed maps to 401 | 201 if accepted; duplicate/budget 409, rate limit 429, closed 403 | 403 | 401 closed | 403 closed | 403 |
| `POST /vote/{event}/{project}/withdraw` | 200 if withdrawn; closed maps to 401 | 200 if withdrawn; closed 403 | 403 | 401 closed | 403 closed | 403 |
| `GET /results/{event}` | 401 while open | 403 while open | 200 | 200 only after a non-null close time has passed | same | 200 |
| `POST /projects/{id}/comments` | 201 while open; 401 closed or if mode is AUTH | 201 while open; 403 closed | 403 | 401 closed | 403 closed | 403 |
| `POST /api/v1/organizer/comments/{id}/flag` | 401 | 403 | 200 | 403 | 403 | 200 |
| `GET /api/v1/organizer/voting/summary` | 401 | 403 | 200 | 403 | 403 | 200 |

If `voting_closes_at` is null, results never become public to non-organizers. In AUTH mode anonymous ballot and write calls return 401; authenticated forbidden callers return 403.

### 3.4 Stretch (T4)

| Route | judge (own) | organizer | anon |
|---|---|---|---|
| `GET /judges/{id}/record.json` + `verify_record.py` | 200 (own record) | 200 (any) | 200 — signed records are **meant** to be publicly verifiable, so this one route is deliberately open; verification happens offline against the public key, not by trusting the server |
| `POST /organizer/webhooks` | 403 | 200 | 401 |

---

## 4. The route×role×ownership test matrix, as code (the actual enforcement mechanism)

Hand-listing expectations in a markdown table (§3) is the *design*; the thing that actually enforces it is a generated test that fails the build if reality drifts from this file:

```
def test_full_authz_matrix():
    routes = introspect_urlconf() + introspect_ninja_openapi()
    declared = load_expectations_from(this_file_as_yaml)   # §3, machine-readable twin
    for route in routes:
        assert route.name in declared, f"{route} has no declared authz expectation — build fails"
    for route, persona, expected_status in declared:
        response = client.get(route, headers=persona.auth_header)
        assert response.status_code == expected_status
```
**Two things make this a real check, not theater (playbook: "a test that cannot fail is not evidence"):**
1. The **first loop** — every route discovered via introspection must have a declared expectation, or the build fails. A new endpoint added at 3am without a policy decision doesn't silently ship.
2. **The control case**: a deliberately leaky test-only route, `GET /debug/_leaky_test_only/{judge_id}/scores`, wired with *no* policy check at all, added purely so the first loop's own "must be declared" assertion can be proven to fire on something real before we trust it on everything else. Removed before freeze — its only job is to prove the check can fail.

This file (§3) is kept as the human-readable source; a small YAML/JSON twin generated from it is what the test actually loads, so the design doc and the enforcement never drift apart (this doubles as one of the docs-consistency checks, PLAN V7).

---

## 5. Defense in depth (optional, only with slack time)

Postgres Row-Level Security as a second layer under the service layer (`SET LOCAL app.current_actor_id`, RLS policies on `Ballot`/`Project`) — not required, the service layer is the one that must not fail, but cheap insurance if G3 has slack. Not scheduled; noted here so it isn't forgotten if there's time.

---

## 6. Open items for G1

- Whether `404` (not `403`) is ever the right answer for hiding *existence* (e.g. a draft project's URL) rather than just its contents — leaning **403** everywhere except where hiding existence is itself the point (none of our T1/T2 routes need this; T3 anonymous ballots might, if we don't want to leak which projects exist pre-gallery-publish — low stakes, decide at G6).
- Rate limit on the authz-sensitive endpoints themselves (separate from the T3 voting rate limit) — likely unnecessary for a local single-organizer deployment, revisit only if the threat model (part of backlog item 5) says otherwise.
