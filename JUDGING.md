# JUDGING.md — How Rubric assigns, scores, normalizes and protects judging

This is the judging-integrity document for Rubric. It explains, in the order a
reviewer would probe them: how judges are assigned, how a ballot becomes a
number, how differences between judges are corrected, how role isolation is
enforced, how public voting resists abuse, and what the audit log does and does
not prove. Every claim below describes behavior that exists in the code today,
and each section says how to check it.

**Two ground rules for reading it.**

1. Numbers in this file were measured on the published fixture data
   (`fixtures.json`, event `evt_01`: 41 projects, 40 teams, 30 judges, 8 tracks,
   126 scores). A test (`tests/test_docs_consistency.py`) recomputes the headline
   values from a real run and fails if this document drifts from the code.
2. Limits are stated next to the feature they limit, not in a footnote. The
   sections on normalization (§4) and voting (§6) each end with what the
   mechanism does **not** do.

## Contents

1. [What the acceptance checker proves, and what it cannot](#1-what-the-acceptance-checker-proves-and-what-it-cannot)
2. [Judge assignment and graph health](#2-judge-assignment-and-graph-health)
3. [From ballot to number: the weighted rubric](#3-from-ballot-to-number-the-weighted-rubric)
4. [Cross-judge normalization](#4-cross-judge-normalization)
5. [Role isolation and authorization](#5-role-isolation-and-authorization)
6. [Public voting, abuse model and threat model](#6-public-voting-abuse-model-and-threat-model)
7. [The audit ledger](#7-the-audit-ledger)
8. [Bonus challenges: what is claimed](#8-bonus-challenges-what-is-claimed)
9. [Known limitations, in one place](#9-known-limitations-in-one-place)

---

## 1. What the acceptance checker proves, and what it cannot

The organizers' checker (`run.py`) makes seven HTTP requests. Six of them cover
tiers T1 and T2 and one covers the closed-event rule; it has no check for T3 or
T4. Rubric therefore treats the tiers differently:

| Tier | How it is evidenced |
|---|---|
| T1 Core, T2 Judging | Machine-verified by `run.py` on every push (CI job `clean-room`, output committed as `acceptance-report.txt`), plus the test suite. |
| T3 Public voting | Built to be verified **by a person in under a minute** (§6.8), plus the test suite. The checker cannot see it. |
| T4 Stretch | Not claimed. Rubric ships a JSON/HTML action parity and a CSV export, but no webhooks, certificates, embeddable widget or published OpenAPI document. |

Because a single failing T1 check would zero out T2 credit in the checker's own
gating, CI fails the build on any `T1 … FAIL` line and on any claimed-but-
unverified tier.

---

## 2. Judge assignment and graph health

### 2.1 Scope

The 126 fixture scores are imported as completed history (assignment status
`COMPLETED`, ballot marked complete). The assignment algorithm was **not** what
produced them and it never rewrites them. It runs on new or under-reviewed
projects in a live event, and it only adds assignments.

### 2.2 Policies

| Code | Policy |
|---|---|
| A-01 | **Track eligibility is a hard constraint.** A judge is only assigned to projects in tracks they are declared eligible for (`JudgeTrackEligibility`). |
| A-02 | **Conflict of interest is a hard constraint.** A judge who is a member of a project's team is never assigned to it, even if that leaves the project short. |
| A-03 | **Load is balanced.** At every step the least-loaded eligible judge is chosen first, so the spread between busiest and quietest judge stays small. |
| A-04 | **Under-coverage is reported, never hidden.** If a track lacks enough eligible judges to reach *k* reviews, each short project is recorded by name in `AssignmentRun.under_coverage` and shown on the organizer dashboard. |
| A-05 | **Connectivity is measured on every run.** Disconnected groups of judges are reported, not silently merged. |
| A-06 | **Assignment is additive and idempotent.** Re-running fills gaps only. An assignment that already has a ballot is never touched. |
| A-07 | **Randomness is seeded and recorded.** Ties between equally loaded judges are broken with a shuffle whose seed is stored on the run, so a run can be reproduced exactly. |

### 2.3 Algorithm

For each track, the projects (submitted, not flagged duplicate) are shuffled with
the seeded generator. For each project, the judges eligible for that track and not
in conflict are sorted by current load (ties broken by the seeded generator) and
the first `k − existing` are assigned. A shortfall goes to `under_coverage`.
Every run stores its target `k`, seed, shortfalls, connectivity report and any
anchor injections in an `AssignmentRun` row.

### 2.4 Graph health

Normalization (§4) can only compare judges who are linked by shared projects, so
Rubric measures that link explicitly. Two judges are adjacent if they reviewed at
least one common project. From that graph:

- the graph Laplacian `L = D − A` is built and its eigenvalues computed;
- the number of connected components is the number of eigenvalues equal to zero
  (below `1e-9`), cross-checked against a plain breadth-first search;
- the second-smallest eigenvalue, the Fiedler value, measures how robustly
  connected a component is. A component of one judge has no Fiedler value and is
  reported as `null`, not `0`.

**On the real fixture:** one connected component containing all 30 judges, global
Fiedler value ≈ 0.0875. Four judges are eligible for more than one track
(`jdg_02`, `jdg_03`, `jdg_11`, `jdg_29`) and act as natural bridges. If a live
event has two groups with no shared judge, Rubric will bridge them only through a
judge who is *genuinely* eligible for both; it never invents eligibility. If no
such judge exists the disconnection is reported and normalization is done inside
each component (D-05).

---

## 3. From ballot to number: the weighted rubric

The organizer configures a rubric per event: named criteria, each with a weight
and a maximum score (`/organizer/rubric`). Weights can be changed after scoring
begins (each change is audit-logged with before and after values, and normalization
must be re-run to reflect it); deleting a criterion that already has scores is
refused, because that would silently rewrite history.

A judge fills one score per criterion. Before any cross-judge correction, each
completed ballot is collapsed to a single number using the organizer's weights:

```
y[i,j] = sum_k( w[k] * score[i,j,k] ) / sum_k( w[k] )
```

`i` is the project, `j` the judge, `k` the criterion. The fixture rubric has three
equally weighted criteria (functionality, quality, innovation). Scores must be
between 0 and the criterion's maximum, and the service rejects non-numeric and
non-finite values. The judge console is a two-pane screen (submission on the left,
rubric on the right) with keyboard scoring and autosave; a ballot is counted only
when it is explicitly submitted.

---

## 4. Cross-judge normalization

### 4.1 The problem, shown on real data

Judges do not use the scale the same way. Two of the fixture's three deliberate
edge cases are exactly this problem:

- **`jdg_07` scored every one of their three assignments identically**
  (functionality 4, quality 4, innovation 4 on `prj_09`, `prj_17` and `prj_19`).
  A judge who never differentiates tells us their *level*, not the relative
  quality of the projects.
- **Eight of 41 projects have only two reviews instead of three**
  (`prj_10, prj_15, prj_18, prj_19, prj_24, prj_29, prj_39, prj_40`).

`prj_19` is both: it is thin (two reviews) *and* one of its two reviews comes from
`jdg_07`. Its only genuinely relative signal is the other reviewer, `jdg_29`.
Rubric was designed so this case is visible rather than smoothed over (D-04).

### 4.2 Method

Rubric uses a **pragmatic shrinkage estimator inspired by empirical-Bayes
methods**. It is not a full hierarchical Bayesian model and does not compute a
posterior; it is a transparent point estimator whose every step is inspectable.

For judge *j* with *n* ballots, raw mean `ybar`, raw variance `s²`, and the
event-wide pooled mean `mu0` and variance `var0` (computed over all counted
ballots):

```
mu_j  = ( n * ybar + 4 * mu0  ) / ( n + 4 )     # judge mean, pulled toward the pool
s2_j  = ( n * s2   + 4 * var0 ) / ( n + 4 )     # judge variance, pulled toward the pool
z[i,j] = ( y[i,j] - mu_j ) / sqrt( s2_j )       # this judge's standardized rating
```

A project's normalized score is the plain average of its judges' `z` values, mapped
back onto the familiar scale:

```
normalized(i) = mu0 + mean_j( z[i,j] ) * sigma0        (sigma0 = sqrt(var0), clipped to [1, 5])
```

The prior strength is 4 for both mean and variance (`kappa0 = nu0 = 4`), a fixed,
documented constant rather than a tunable knob. At `n = 3` a judge's own data gets
weight 3/7 and the pool 4/7; at `n = 10` the judge's own data gets 10/14. Each
judge contributes equally to a project's mean; contributions are not weighted by
inverse variance.

**On the fixture** (121 counted ballots from 29 judges; the 5 ballots on the
superseded duplicate `prj_07` are excluded, and `jdg_01` reviewed only that
project): pooled mean `mu0 = 3.5758`, pooled variance `var0 = 0.3930`,
`sigma0 = 0.6269`.

**Worked example: the constant judge.** For `jdg_07`: `n = 3`, `ybar = 4`, `s² = 0`.

```
mu_j = (3*4 + 4*3.5758) / 7 = 3.7576
s2_j = (3*0 + 4*0.3930) / 7 = 0.2246      # strictly positive, so no division by zero
z    = (4 - 3.7576) / sqrt(0.2246) = 0.5115
```

Every one of `jdg_07`'s ballots yields the same `z = 0.5115`. Their zero variance
cannot distort the ranking, and their rating still contributes their *level*. The
same shrinkage is what keeps a one-ballot judge from swinging a project.

### 4.3 Policies

| Code | Policy |
|---|---|
| D-01 | **Annotate, never replace.** Raw mean, normalized score and rank are shown together everywhere (dashboard, proof page, CSV). Normalization never overwrites the record. |
| D-02 | **Duplicates: the later submission is canonical.** Team `tm_07` submitted "Dry Harbour" twice: `prj_07` at 04:29 and `prj_41` at 17:57, three minutes before the deadline. A near-deadline resubmission reads as a fix, so `prj_41` is the entry (raw mean 3.8333, normalized 3.7912, rank 8) and `prj_07` is flagged `is_duplicate_of = prj_41`, excluded from ranking and from voting, but kept in full. The flag is audit-logged, attributed to "duplicate-detection policy v1", and an organizer can reverse it in one click. |
| D-03 | **Nobody is silently excluded.** A constant-score judge is neutralized statistically (above) and flagged on the dashboard ("scored 3/3 assignments identically"). Removing a judge is a human, audit-logged decision. |
| D-04 | **Thin evidence stays visible.** The review count travels with every rank (gallery, dashboard, CSV). Thin-batch and constant-judge warnings are reported together, so `prj_19` shows both instead of one innocuous number. |
| D-05 | **Calibrate only within connected judge groups.** If the judge graph is disconnected, each component is normalized separately and a single cross-component ranking is refused without an explicit organizer override. |

### 4.4 Evidence: what it shows and what it does not

There are three separate pieces of evidence. They answer different questions and
should not be read as one.

**(a) The method behaves as designed on the real fixture.** The standard deviation
across judges of their *raw* mean ballot value is **0.3235**; after normalization,
the standard deviation across judges of their mean normalized ballot value (on the
same 1–5 scale) is **0.2023**, a reduction of about 37.5%. *This is largely by
construction:* shrinkage pulls every judge toward the pool, so the spread of judge
means must shrink. It shows the mechanism is doing what its formula says. It does
**not** show the ranking got closer to the truth, and Rubric does not claim it does.

**(b) Recovery of a known truth, in simulation (labelled SYNTHETIC on the proof
page).** The only way to test "closer to the truth" is to plant a truth. The
validation generates 20 projects with known quality, 10 judges with systematic
leniency or harshness offsets from −1.5 to +1.5, noise with standard deviation
0.2, and three judges per project. It then compares each ranking to the planted
truth using Spearman rank correlation:

| Ranking | Spearman ρ vs. planted truth (seed 2026) |
|---|---|
| Raw mean | 0.7308 |
| Normalized | 0.8917 |

A single seed can flatter a method, so the same experiment is repeated over 100
seeds (0–99): mean ρ rises from 0.7347 (raw) to 0.8949 (normalized), and
normalization beat the raw ranking in **100 of 100** seeds. Nothing was tuned to
produce these numbers; they are what the code returns and both are shown on
`/organizer/normalization`.

**(c) Limits of the simulation.** The simulated judges follow the same additive
"offset plus noise" story the estimator assumes, so this validates the
implementation and the direction of the effect under that assumption. It cannot
prove that real judges behave this way.

### 4.5 Rank sensitivity, stated plainly

Rank is an ordinal display of a continuous score, so in crowded parts of the
distribution a tiny score change moves several places. In the fixture, `prj_09`
(normalized 3.6128, rank 16), `prj_19` (3.6022, rank 18) and `prj_17` (3.5741, rank
19) sit in a tight cluster: gaps of roughly 0.002 to 0.03 move several ranks. In a
sparse region, `prj_13` (3.3116, rank 31) and `prj_26` (3.2631, rank 32) are about
0.05 apart and stay stable. Read rank movement together with the score change and
the review count; a rank shift is not by itself a defect.

### 4.6 What normalization does not do

- It is not a full Bayesian posterior and states no credible intervals. (The
  `NormalizedScore` table reserves rank-interval columns; nothing populates them.)
- It cannot detect collusion or a judge who is *consistently* biased toward a
  particular project; it corrects a judge's overall lean, not their favorites.
- With a judge who reviewed a single project, calibration comes almost entirely from
  the pool; the review count flag is the signal that this happened.
- It depends on judges being connected through shared projects (§2.4).

### 4.7 Determinism and reproducibility

Judges and projects are always iterated in a stable order (by external id or primary
key), never by dictionary or set order, so two runs on the same data produce
byte-identical output (tested). The raw-versus-normalized-versus-rank-change table
can be exported without a running server:
`python manage.py export_normalization_proof <run_id> --output proof.csv`,
or downloaded from `/organizer/normalization`.

---

## 5. Role isolation and authorization

### 5.1 One function decides who sees judging scores

The two routes the checker names, `GET /api/judge/scores` and
`GET /api/judge/scores?judge=<id>`, are served by a single function,
`services.judging.get_scores(actor, judge_external_id=None)`. There is exactly one
place where the check can be forgotten, and it is not forgotten:

- an **organizer** may read any judge's scores or all scores for the event;
- a **judge** may read only their own; naming another judge is refused (403);
- everyone else is refused (401 if not signed in, 403 if signed in).

The check lives in the backend. Hiding a link in a template would not survive
`curl`, which is what the checker uses, so it is not relied on.

### 5.2 The bug an adversarial review found, and the fix

Judges outside the fixture have no `external_id`. An early version selected a
judge's "own" ballots by matching `external_id`, so every non-fixture judge (whose
`external_id` is null) matched every other one: a cross-judge leak with no
error. The fix binds identity to the authenticated user row
(`assignment.judge == actor.user`) and uses `external_id` only to resolve an
organizer's explicit lookup.

### 5.3 Every route is declared, and the declaration is enforced

`tests/authz_expectations.yaml` lists the expected response for every route and
persona (anonymous, participant, judge, organizer, site admin). The current
URLconf has 48 named routes and 48 declarations. A test walks the URLconf and fails
the build if any route has no declaration, so an endpoint added without a policy
decision cannot ship. To prove that alarm can actually fail, a second test points
it at a temporary URLconf containing an undeclared route and asserts that it
fires. No deliberately leaky route exists in the shipped application.

Requests resolve to an `Actor` (event-scoped, with independent
`is_participant`/`is_judge`/`is_organizer` flags, since one user may hold several
roles) or an anonymous actor whose every flag is false. Service functions take the
actor and nothing else, so a view cannot reach for `request.user` and skip the
check.

### 5.4 Organizer authority is scoped to the event being changed

An adversarial review found that event-management functions checked the
organizer's role on the *current* event rather than the event being edited, so an
organizer of event A could edit event B. Every mutating event, track, prize,
rubric, invite and voting-window action now checks membership in the **target**
event (site administrators excepted), and named tests cover it: an organizer of A
cannot edit B, switch the portal to B, or add tracks to B; a judge whose only membership
is in A gets a 403 or an empty result on B's judge queue, ballot, score and ballot-
submission routes; switching the current event back restores access; creating or
switching events never copies memberships; a judge invite or a team invite code for
A cannot be used while B is current.

### 5.5 Other request-level protections

- **Authentication.** Passwords use Django's hasher. Session and bearer tokens are
  stored only as SHA-256 hashes; the raw value is shown once.
- **CSRF depends on how you authenticated.** Requests authenticated by an
  `Authorization` header skip CSRF (they are not ambient-credential requests);
  cookie-authenticated and anonymous browser POSTs are protected.
- **Login and registration are rate limited:** 10 attempts per 5 minutes per client,
  stored as a keyed hash of the IP, not the IP itself, shared across all worker
  processes.
- **Stored XSS defense.** Project links (repository, demo video, live site) must be
  absolute `http(s)` URLs, validated when saved, and a template filter refuses to
  render any other scheme even if bad data were written directly to the database.
  Comments and titles are escaped by the template engine.

### 5.6 How to check it yourself

With the stack running, using the printed demo tokens (see `README.md`):

```
# judge_b asking for judge_a's (jdg_07's) scores: expect 403
curl -i -H "Authorization: Bearer rubric_seed_judge_b_tok_7a8b9c0d1e2f" \
     "http://localhost:8080/api/judge/scores?judge=jdg_07"
# a participant asking for judge scores: expect 403
curl -i -H "Authorization: Bearer rubric_seed_participant_tok_3f4e5d6c7b8a" \
     http://localhost:8080/api/judge/scores
```

---

## 6. Public voting, abuse model and threat model

Public voting is tier T3. It has no automated credit path, so it is designed so a
reviewer can watch each defense work (§6.8). Voting is configured per event by an
organizer: access mode, optional vote budget, and an open/close window.

### 6.1 Policies

| Code | Policy |
|---|---|
| V-01 | **Uniqueness by database constraint.** A vote is unique on `(event, project, mode, voter pseudonym)`. Duplicate voting is refused by the database, not just by application code. |
| V-02 | **Results are gated on every request.** Organizers can see live results at any time; everyone else only after the voting window has closed. If no close time is set, results are never public to non-organizers. There is no cached public tally that could leak early. |
| V-03 | **Ballot order is per voter and stable.** Projects are ordered by an HMAC of the project and the voter's pseudonym, so refreshing never re-rolls a favorable position and different voters see different orders. This removes position bias without letting a voter shop for a better slot. |
| V-04 | **Rate limiting is server-side.** Five attempts per minute per voter pseudonym. |
| V-05 | **Comments are flag-and-hide, never delete.** A flagged comment leaves the public view but stays in the database and in the organizer's view. |
| V-06 | **Every mechanism is demonstrable in under a minute.** Refusals show up as a live counter on the organizer dashboard, not as a log file. |
| V-07 | **Superseded and unfinished projects are not votable or commentable.** Drafts and flagged duplicates (`prj_07`) are excluded structurally, as are other events' projects. |

### 6.2 Access modes and budgets

- **Open link** (default): anyone with the link can vote; the voter is identified by a
  keyed hash of their network address.
- **Authenticated:** the voter is identified by a keyed hash of their account.
- **Vote budget** (`votes_per_voter`): empty means one vote per project with no cap;
  a number *N* gives each voter *N* votes in total. A voter may **withdraw** a vote
  while the window is open, which frees budget. Lowering the budget below what any
  voter already holds is refused.
- The access mode **cannot be changed once any vote or attempt is recorded**;
  otherwise a voter could vote once per mode.
- Email-gated voting is deliberately not offered: it needs outbound email, which
  breaks the run-offline rule.

### 6.3 Every attempt is recorded

Each cast, withdrawal or refusal writes an append-only `VoteAttempt` row with its
outcome: `ACCEPTED`, `REJECTED_DUPLICATE`, `REJECTED_RATE_LIMIT`, `REJECTED_CLOSED`,
`REJECTED_BUDGET` or `WITHDRAWN`. That single log drives the rate limit, the abuse
counters and the dashboard. On top of it, a small `Vote` table holds the current
valid votes for fast tallying. Votes and attempts are written in one transaction,
serialized per event (a row lock on PostgreSQL), so racing requests cannot exceed a
budget; a concurrency test with parallel threads asserts that exactly the allowed
number of votes survives.

### 6.4 Secret ballot

Vote identities are pseudonyms: `HMAC-SHA256(key, mode | identity)` where the key is
derived from the application `SECRET_KEY` and the event's voting seed, the identity
is the user id (authenticated mode) or network address (open mode), and no raw
address, user agent or account id is stored on a vote. Vote and withdrawal entries
in the audit log carry no user actor. They use a fixed `voter-pseudonym` label and
a truncated pseudonym hash. Comments stay attributed because they are public speech.

The alternatives were an auditable public record (votes attributed to accounts),
and attribution visible only to organizers. Attribution exposes voters to pressure
and retaliation, and organizer-only attribution is not a reliable boundary because
organizers can be participants or have conflicts. See `DECISIONS.md` entry 23.

### 6.5 Threat model: what is stopped

| Threat | Defense |
|---|---|
| Repeat voting by one identity | V-01 database constraint, plus the per-voter budget. |
| Rapid scripted voting from one source | V-04 rate limit; every refused attempt is logged and counted. |
| Racing parallel requests to exceed a budget | Serialized transaction; concurrency-tested. |
| Peeking at results early | V-02; the tally is only reachable through the gated service on every request. |
| Position gaming by refreshing | V-03 stable per-voter order. |
| Voting for a superseded duplicate, a draft or another event's project | V-07; refused (403). |
| Changing the rules mid-vote to gain votes | Access mode locks after the first action; budget cannot drop below what voters hold; window changes are audit-logged before/after. |
| Voter identity exposed by the database or audit export | §6.4 pseudonyms; no account id on vote records. |
| Comment spam and abuse | Length cap, rate limit through the same mechanism, flag-and-hide moderation, escaped output. |
| Account-creation and password guessing | 10 attempts per 5 minutes per client on login and registration. |
| Silent tampering with vote or moderation history | Hash-chained audit log (§7). |

### 6.6 Threat model: what is not stopped

Stating these plainly is part of the design.

- **Open-link mode is best-effort.** The identity is the client's IP address as seen
  by the server (`REMOTE_ADDR`; forwarding headers are ignored on purpose because a
  client can forge them). Anyone with many IP addresses (a VPN, a botnet) can cast
  many votes. Conversely, people behind one shared address (an office, a university,
  Docker's gateway) share one ballot and one rate limit, and one of them could
  withdraw another's vote. **Use authenticated mode when the result matters.**
  Alternatives considered and rejected: IP plus user agent (bypassed by rotating one
  header, reproduced during review), a signed device cookie (clearable in one
  click), and CAPTCHA or proof-of-work (needs external services or adds friction).
- **Authenticated mode trusts account creation.** Registration is open and there is
  no email verification (it needs outbound mail). A determined person can create
  many accounts; the registration rate limit slows this and does not stop it.
- **The operator can re-link pseudonyms.** Someone who holds both the database and
  the `SECRET_KEY` can recompute pseudonyms from user ids. A database-only reader
  cannot. This is a secret ballot against organizers using the application, not
  against the host operator.
- **Organizers see live tallies and can reconstruct them from the audit log.** This
  is by design (they monitor integrity); it means a curious organizer knows the score
  during voting.
- **Organizers can change the window and budget after votes exist.** Increasing the
  budget or moving the close time is possible, always audit-logged, and visible to
  anyone verifying the chain. It is not prevented.
- **Vote-attempt rows are append-only in application code (the ORM refuses updates
  and deletes), but not by database trigger.** The audit log has database-level
  immutability on PostgreSQL; `VoteAttempt` does not.
- **Judge collusion and organizer misconduct are not preventable by software.** The
  answer is detectability: every override is audit-logged and the chain can be
  verified offline.
- **Scraping the public gallery is not defended.** The gallery is public by
  requirement.
- **SQLite is not a supported production database.** The in-process lock that
  stands in for a row lock does not span processes. The shipped stack uses
  PostgreSQL.

### 6.7 Concurrency and DoS note

Serializing votes on the event row keeps budgets correct. It also means every voting
action in one event queues behind one lock. That is fine for hackathon-scale
traffic (hundreds of voters); a very large public vote would want per-voter locking.

### 6.8 Verify each defense in under a minute

1. Sign in as the organizer; open the event dates page and press **Open voting now**.
2. In a private window, open `/vote/<event-slug>` and vote for a project. Vote for
   it again: the ballot reports a duplicate and the organizer dashboard's
   **Voting integrity** card ticks up its blocked-attempt counter within its
   10-second refresh.
3. Set a vote budget of 1 (dates page) and try a second project: refused for budget;
   **Withdraw** the first vote and the second works.
4. While voting is open, `/results/<event-slug>` shows "hidden" to a visitor and the
   tally to the organizer. Press **Close voting now**: the visitor now sees results.
5. Try to vote on `prj_07` (a flagged duplicate): refused.

---

## 7. The audit ledger

State changes are recorded in the same database transaction as the change, in a
hash-chained, append-only log.

- Each entry stores a sequence number, the previous entry's hash, a UTC timestamp,
  actor, action, target and payload. Its hash is the SHA-256 of the canonical JSON
  (sorted keys, compact separators, no non-finite numbers) of exactly those fields.
- Sequence numbers are assigned under an exclusive lock on a single chain-head row
  (plus a PostgreSQL advisory lock), so concurrent writers cannot fork the chain.
  A concurrency self-check command exists (`manage.py audit_selfcheck`).
- On PostgreSQL, database triggers reject any `UPDATE`, `DELETE` or `TRUNCATE` of
  the log.

**What the chain proves.** Editing, deleting or back-dating any entry breaks the
chain, and the break is detectable by the in-app verifier or, offline and without a
running server, by `scripts/verify_audit_chain.py` against an exported chain
(`/api/v1/organizer/audit-log/verify?download=1`), which uses only the Python
standard library.

**What it does not prove.**

- That a logged event was *true*. It proves an organizer recorded an override at
  position N, not that the override was justified.
- Anything against a database superuser, who can drop the triggers, rewrite rows and
  recompute the hashes. Real immutability against the operator requires publishing
  the head hash to a place the operator does not control (a public commit, a
  transparency log or a signed timestamp).

---

## 8. Bonus challenges: what is claimed

| Challenge | Status |
|---|---|
| **Normalization Proof** | Claimed. Method specified in §4.2, run on the fixture, raw/normalized/rank-change table exportable with no server (§4.7), with the honest reading of the evidence in §4.4. |
| **Threat Model** | Claimed. §6.5 and §6.6 name what is stopped and what is not. |
| **API First** | Not claimed. Views and JSON endpoints share one service layer, so most actions have a JSON form, but there is no published OpenAPI document. |
| **Pairwise Mode** | Not built. |

---

## 9. Known limitations, in one place

- Open-link voting is best-effort; authenticated voting relies on open registration
  (§6.6).
- The operator holding the database and `SECRET_KEY` can re-link vote pseudonyms.
- Organizers can see live vote tallies and can change the voting window and budget
  (audit-logged).
- Normalization is a shrinkage estimator, not a Bayesian posterior; the synthetic
  evidence assumes the model it validates (§4.4).
- Rank moves a lot for small score changes in crowded regions (§4.5).
- The audit log is tamper-evident, not proof against a database owner (§7).
- One event is active at a time; concurrent events are a deliberate non-goal.
- The containerized stack has been verified on Linux (CI); it has not been run on
  Windows Docker Desktop. The design avoids bind mounts, the most common source of
  Windows-specific trouble, but that is not a substitute for testing.