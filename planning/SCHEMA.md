# DogFood 2026 — Domain Model & Schema (backlog item 1)

**Rev 5 · 2026-09-25 · Status: design only, no code yet — this revision incorporates fixes from STRESS-TEST.md (F1, F2, F3, F5, F7, F8, F15)**
Companion to PLAN.md/RESEARCH.md/LOGS.md. This is our own pre-kickoff sketch — "sketch schemas" is explicitly allowed before Friday. Nothing here is committed code; it becomes the first draft of `DATA-MODEL.md` once the repo exists.

---

## 0. Design principles (decided here, feed PLAN §2 as new proposed decisions)

1. **Every mutation goes through the service layer.** No view or API handler ever calls `Model.objects.get()`/`.save()`/`.filter()` directly on a sensitive model — always through `services.<domain>.*`, which re-checks the actor's identity before reading or writing (RESEARCH §7.5, P-03). This file names the service boundary for each entity so G1 can build directly from it.
2. **Auth is a standalone token, not Django's session framework.** Because the checker "never logs in" and just attaches a raw header (RESEARCH §2.1), we implement our own `AuthToken` model + middleware rather than relying on `django.contrib.sessions`. This makes it trivial to print fixed, deterministic tokens at boot for the four required personas without fighting session serialization, and it's exactly as capable for our own real users. **New decision — P-12** (added to PLAN §2.2 below).
3. **Every fixture-derived row carries its `external_id` verbatim** (`"jdg_07"`, `"prj_19"`, `"tm_07"`, etc.). This makes import idempotent (re-running the seed script upserts instead of duplicating — a real Adoptability point), makes our own tests able to reference the *real* edge cases by name instead of a guessed internal PK, and gives DATA-MODEL.md's "way in and out" a concrete provenance story.
4. **Every state-changing action writes an `AuditLogEntry`.** Not optional, not bolted on later — the service layer writes it in the same transaction as the change it's logging.
5. **Nothing is deleted, ever, at the row level, for anything a judge or auditor might need to reconstruct.** Soft-flags (`is_duplicate_of`, `is_flagged`) instead of deletes for exactly the cases spec.md tells us to expect (RESEARCH §2B).

---

## 1. Entities, by tier

### 1.1 Identity & events (T1)

**User**
| field | type | notes |
|---|---|---|
| id | PK | |
| email | unique, citext | |
| password_hash | text, nullable | null for fixture-imported judges (SCHEMA §2) — they authenticate only via their printed seed token, never a password. Real registered users set this via `/accounts/register` (API.md §3) |
| display_name | text | |
| is_site_admin | bool, default false | the "admin" role in T1's role list; site-wide, not event-scoped |
| external_id | text, nullable, unique when set | e.g. `jdg_07` — only set for fixture-imported judges |
| created_at | timestamp | |

**AuthToken** *(new, our own design — see §0.2)*
| field | type | notes |
|---|---|---|
| id | PK | |
| token_hash | text, unique, indexed | SHA-256 of the raw token — matches `ApiToken`'s pattern (fixed by the stress test, F5); the raw value is shown once (printed at boot / set as the cookie), never stored |
| user_id | FK → User | |
| label | text | e.g. `"seed:organizer"` — for the boot-time printout, not shown to the checker |
| created_at | timestamp | |
| expires_at | timestamp, nullable | seed tokens: null (don't expire mid-event) |

**Event**
| field | type | notes |
|---|---|---|
| id | PK | |
| slug | unique | |
| name | text | |
| external_id | text, nullable, unique | `evt_01` for the imported fixture event |
| submissions_open_at | timestamp | |
| submissions_close_at | timestamp | **loaded verbatim from the fixture's own `submissions_close`** (RESEARCH §2.2/§7.5) — never invented |
| voting_opens_at / voting_closes_at | timestamp, nullable | T3 |
| voting_access | enum: OPEN / AUTH, default OPEN | T3; email-gated mode is unavailable in offline deployments |
| votes_per_voter | non-negative integer, nullable | null means no total budget; each project remains unique per voter |
| voting_seed | random per-event secret, 64 hex chars | HMAC salt and deterministic ballot ordering; generated for existing events by data migration |
| created_by | FK → User | |

**EventMembership** — the event-scoped role model (participant/judge/organizer are per-event; admin is site-wide via `User.is_site_admin`)
| field | type | notes |
|---|---|---|
| id | PK | |
| event_id | FK → Event | |
| user_id | FK → User | |
| role | enum: PARTICIPANT / JUDGE / ORGANIZER | |
| unique(event_id, user_id, role) | | a user could plausibly be both a participant and later invited as a judge in a bigger platform; not needed for the fixture but cheap to model correctly |

**JudgeTrackEligibility** *(new — fixed by the stress test, F3: nothing previously stored this, though AUTHZ/ASSIGNMENT/VOTING all assumed it)*
| field | type | notes |
|---|---|---|
| event_membership_id | FK → EventMembership | must be a row with `role=JUDGE` |
| track_id | FK → Track | |
| unique(event_membership_id, track_id) | | the real fixture's `judges[].tracks` array imports directly into this, one row per track |

**Track**
| field | type | notes |
|---|---|---|
| id | PK | |
| event_id | FK → Event | |
| name | text | |
| external_id | text, nullable, unique | `trk_01`…`trk_08` |

**Prize**
| field | type | notes |
|---|---|---|
| id | PK | |
| event_id | FK → Event | |
| rank_label | text | "1st", "Best Judging Engine", etc. |
| description | text | |

**Team**
| field | type | notes |
|---|---|---|
| id | PK | |
| event_id | FK → Event | |
| name | text | |
| invite_code | text, unique | team formation by invite link (T1) |
| external_id | text, nullable, unique | `tm_01`…`tm_40` |
| created_by | FK → User | |

**TeamMembership**
| field | type | notes |
|---|---|---|
| team_id | FK → Team | |
| user_id | FK → User | |
| unique(team_id, user_id) | | |

**Project** (the submission)
| field | type | notes |
|---|---|---|
| id | PK | |
| event_id | FK → Event | |
| team_id | FK → Team | |
| track_id | FK → Track | |
| title | text | |
| summary | text | |
| description | text, blank ok | |
| repo_url / demo_video_url / live_url | text, blank ok | |
| tech_tags | array/M2M | |
| custom_answers | JSON | organizer-defined custom questions |
| status | enum: DRAFT / SUBMITTED | |
| submitted_at | timestamp, nullable | |
| updated_at | timestamp | |
| external_id | text, nullable, unique | `prj_01`…`prj_41` |
| is_duplicate_of | FK → Project, nullable, self | **set for `prj_07` → `prj_41`** (the earlier submission flags itself against the later, canonical one — corrected by the stress test, F2; NORMALIZATION.md D-02 is the authoritative policy) |
| duplicate_flag_reason | text, nullable | e.g. `"same team, same title, submitted 3 min apart"` |

**Draft-and-edit-until-deadline** is enforced in `services.submissions.update()`: reject the write (not just hide the form) if `now() > event.submissions_close_at`, read inside the same transaction that performs the update (RESEARCH §7.5's `select_for_update` note) — this is also literally the T1 "closed event refuses submissions" check target.

### 1.2 Judging (T2)

**Rubric** / **RubricCriterion**
| field | type | notes |
|---|---|---|
| Rubric.id, event_id, name | | one rubric per event, organizer-editable |
| RubricCriterion.id, rubric_id, name, weight, max_score, order | | seed default: `functionality`, `quality`, `innovation` at equal weight — matches the real fixture's own categories (RESEARCH §2B) as a legitimate zero-effort default; organizer can add/reweight |

**JudgeAssignment** — also the edge list for the connectivity graph (RESEARCH §7.3)
| field | type | notes |
|---|---|---|
| id | PK | |
| event_id | FK → Event | |
| judge_id | FK → User (must have an EventMembership with role=JUDGE) | |
| project_id | FK → Project | |
| status | enum: PENDING / COMPLETED | |
| assigned_at | timestamp | |
| unique(judge_id, project_id) | | |

**Ballot** — one judge's full scoring of one project
| field | type | notes |
|---|---|---|
| id | PK | |
| assignment_id | FK → JudgeAssignment, unique | one ballot per assignment — this is the anchor the policy layer checks against |
| comment | text, blank ok | ~40% empty in the real data (RESEARCH §2B) — must render/export gracefully empty |
| submitted_at | timestamp, nullable | for fixture-imported ballots, set to the import run's own timestamp (`scores[]` carries no timestamp of its own) — documented in DATA-MODEL.md as import provenance, not a real judging-time claim (fixed by the stress test, F15) |
| is_complete | bool | |

**BallotScore**
| field | type | notes |
|---|---|---|
| ballot_id | FK → Ballot | |
| criterion_id | FK → RubricCriterion | |
| value | numeric | |
| unique(ballot_id, criterion_id) | | |

**The service boundary that makes the `peer_scores` trap unexploitable — corrected by the stress test (F1: the original version here let a participant through with an empty 200 instead of a 403, which would have failed the literal T2 "participant blocked" check):**
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
401 vs. 403 is decided one layer up, not by this function: the exception handler maps `AnonymousActor` + `PermissionDenied` → 401, a resolved real `Actor` + `PermissionDenied` → 403 (AUTHZ.md §1). This one function is what both `judge_scores` and `peer_scores` route to — there is exactly one place the check can be forgotten, and it's covered by the route×role×ownership matrix (PLAN V2) plus a dedicated test named after the real check.

**AssignmentRun** (full design in ASSIGNMENT.md — backlog item 4)
| field | type | notes |
|---|---|---|
| id, event_id | | |
| run_at | timestamp | |
| target_k | int | reviews-per-project target |
| seed | int | tie-break randomness, logged for reproducibility (ASSIGNMENT.md A-07) |
| under_coverage | JSON | `[{project_id, got, wanted}]` |
| connectivity_report | JSON | component count/sizes, Fiedler value(s) — feeds both JUDGING.md and the Best Judging Engine prize criteria |
| anchor_injections | JSON | `[{judge_external_id, bridged_components: [...]}]` — makes ASSIGNMENT.md's test A6 actually provable (fixed by the stress test, F8: this field didn't exist before, though the test required it) |

**NormalizationRun** / **NormalizedScore** (computed, re-runnable, snapshotted for dashboard/export consistency)
| field | type | notes |
|---|---|---|
| NormalizationRun.id, event_id, computed_at, method_name, parameters (JSON) | | one row per computation |
| NormalizedScore.run_id, project_id, raw_mean, normalized_mean, rank | | |
| NormalizedScore.judge_graph_component_id, judge_graph_fiedler_value | | connectivity health (RESEARCH §7.3), nullable until the graph-health feature is built |
| NormalizedScore.rank_ci_low, rank_ci_high | | nullable until the rank-uncertainty feature is built (DL-019, priority #2) |

**AuditLogEntry** (append-only, hash-chained — DB trigger + `pgcrypto`, RESEARCH §7.5)
| field | type | notes |
|---|---|---|
| id | PK | |
| event_id | FK → Event, nullable | some entries are cross-event (e.g. auth) |
| actor_id | FK → User, nullable | null for system-generated (e.g. import) |
| action | text | e.g. `"ballot.submitted"`, `"project.flagged_duplicate"` |
| object_type / object_id | text / int | |
| payload | JSON | |
| created_at | timestamp | |
| previous_hash / current_hash | text | hash chain — `BEFORE UPDATE OR DELETE` trigger raises unconditionally; the `BEFORE INSERT` trigger takes `pg_advisory_xact_lock(<a fixed key>)` first so concurrent inserts can't race and corrupt the chain (fixed by the stress test, F7 — the original design had no concurrency handling at all) |

### 1.3 Public (T3 — never suite-verified, build for human verifiability, RESEARCH A14)
**Full design in VOTING.md — backlog item 5.** `VoteAttempt` (append-only, every attempt) feeds both the rate-limit check and the audit trail; `Vote` is a small derived table written only on success, for fast tallying.

**VoteAttempt** (append-only)
| field | type | notes |
|---|---|---|
| id, event_id, project_id | | |
| mode | enum: OPEN / AUTH | |
| voter_fingerprint | text | HMAC with event seed over REMOTE_ADDR + user-agent (open); user id string (auth); raw network identifiers are never stored |
| outcome | enum: ACCEPTED / REJECTED_DUPLICATE / REJECTED_RATE_LIMIT / REJECTED_CLOSED / REJECTED_BUDGET / WITHDRAWN | |
| created_at | timestamp | indexed `(fingerprint, created_at)` for the sliding-window query |

**Vote**
| field | type | notes |
|---|---|---|
| id, event_id, project_id, mode, voter_fingerprint | | |
| weight | numeric, default 1 | fixed at 1; quadratic voting is out of scope |
| attempt_id | nullable FK → VoteAttempt | linked before transaction commit; nullable only for the insert sequence |
| created_at | timestamp | |
| **unique(event_id, project_id, mode, voter_fingerprint)** | | one compound key, no partial indexes needed |

**Comment**
| field | type | notes |
|---|---|---|
| id, project_id, author_id (nullable), mode, voter_fingerprint, body, created_at, is_flagged | | flag-and-hide, never delete (VOTING.md V-05) |

### 1.4 Stretch (T4 — never suite-verified, RESEARCH A14; build as core-rubric work per §7.0, not "for the bonus")

**ApiToken** — id, user_id, token_hash, scopes, created_at, revoked_at.
**Webhook** — id, event_id, url, secret, event_types (JSON), created_at.
**SignedJudgeRecord** — id, event_id, judge_id, canonical_json, signature, public_key_ref, issued_at (RESEARCH §7.8).

### 1.5 Import bookkeeping

**FixtureImportLog** — id, imported_at, source_file, counts (JSON: projects/teams/judges/tracks/scores imported), warnings (JSON list) — records what the importer found, including the exact known edge cases (constant judge, thin batches, the duplicate) as structured warnings rather than silent handling. This is the "import report" from our original A3 assumption, now concrete.

---

## 2. Fixture → schema mapping (idempotent import, keyed on `external_id`)

| fixtures.json | Our model | Key |
|---|---|---|
| `event` | Event | `external_id = "evt_01"`, `submissions_close_at` = the literal `submissions_close` string |
| `tracks[]` | Track | `external_id = trk.id` |
| `judges[]` | User + EventMembership(role=JUDGE) + JudgeTrackEligibility per entry in `judges[].tracks` | `external_id = jdg.id`; `email` from the fixture; each track in `judges[].tracks` becomes one `JudgeTrackEligibility` row (fixed by the stress test, F3) |
| `teams[]` | Team + TeamMembership | `external_id = tm.id`; members are emails → get-or-create User + EventMembership(role=PARTICIPANT) |
| `projects[]` | Project | `external_id = prj.id`; `prj_07` gets `is_duplicate_of = prj_41` set explicitly by the importer — the earlier submission (04:29) flags itself against the later canonical one (17:57), matched by team + identical title, logged to FixtureImportLog, not silently inferred at query time (corrected G2: was backwards here, now matches §1.1 and NORMALIZATION.md D-02) |
| `scores[]` | JudgeAssignment (status=COMPLETED) + Ballot + BallotScore | one assignment+ballot per `(judge, project)` pair; `criteria` dict → BallotScore rows against the seeded default rubric |

Import is a management command (`seed_fixtures`), re-runnable (upsert by `external_id`), and ends by printing the four `.dogfood.toml` auth lines in the spec's own worked-example style (RESEARCH §7.5): `seeded. test logins: organizer ... judge_a ... judge_b ... participant ...`.

**Test persona mapping (D-11, refined here):**
| Persona | Maps to | Why |
|---|---|---|
| `judge_a` | `jdg_07` (the constant-score judge) | "own scores" returns real, non-trivial data and doubles as a live demo of constant-judge handling |
| `judge_b` | `jdg_29` (co-reviewer of `prj_19` with `jdg_07`) | isolation check has real stakes — two judges' genuinely different scores on the same project must stay apart |
| `participant` | a member of team `tm_07` (the duplicate-submission team) | browsing "my submissions" demos the duplicate-flagging feature live, for free |
| `organizer` | a dedicated seed account, not fixture-derived | fixtures.json has no organizer role at all |

---

## 3. Django app layout (maps 1:1 to the service boundaries above)

```
src/
  accounts/     User, AuthToken, EventMembership, JudgeTrackEligibility, auth middleware
  events/       Event, Track, Prize
  teams/        Team, TeamMembership, invite-link flow
  submissions/  Project, draft/deadline service
  judging/      Rubric, RubricCriterion, JudgeAssignment, AssignmentRun,
                Ballot, BallotScore, NormalizationRun, NormalizedScore — services.judging.*
  voting/       Vote, VoteAttempt, Comment — T3, services.voting.*
  api/          Django Ninja routers, OpenAPI, ApiToken, Webhook, SignedJudgeRecord — T4
  audit/        AuditLogEntry, the DB trigger migration, verify-chain script
  importer/     seed_fixtures management command, FixtureImportLog
```
Each app's `services.py` is the *only* place that touches its own models from outside the app; views/API handlers in every app call into `services`, never the ORM directly, for anything past a trivial read.

---

## 4. Open items for G1 (not blockers, just not decided yet)

- Exact numeric scale for `RubricCriterion.max_score` — default to 5 (matches the fixture's own scale ceiling), confirm no reason to deviate once T2 UI is drawn.
- Whether `Track` eligibility on `JudgeAssignment` is enforced as a DB constraint or a service-layer check only — leaning service-layer (a CHECK constraint referencing another table isn't portable in Postgres without a trigger, and the service layer already owns this logic).
- Whether `NormalizedScore` recomputation is triggered automatically on new ballots or run on-demand by the organizer — leaning on-demand (a button + the CLI command run.py-style), since silent background recomputation makes the audit trail harder to reason about (an explicit `NormalizationRun` row per computation is easier to defend in JUDGING.md than "it just updates").
