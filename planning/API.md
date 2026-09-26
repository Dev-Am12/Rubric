# DogFood 2026 — API Shape (backlog item 6)

**Rev 2 · 2026-09-25 · Status: design only, no code yet — incorporates fixes from STRESS-TEST.md (F1, F10)**
Depends on SCHEMA/AUTHZ/NORMALIZATION/ASSIGNMENT/VOTING.md. Core principle (RESEARCH §7.0 — "API First" is Adoptability work, not a bonus): **the HTML views and the JSON API are two thin presentation layers over one identical set of service calls.** Neither one is primary; a view and an API route for the same action call the exact same `services.*` function, so there is never a feature that exists in one and not the other.

---

## 1. URL scheme
- The five checker-facing routes stay exactly as declared in `.dogfood.toml` (P-11) — `/projects`, `/projects/new`, `/api/judge/scores`, `/api/export.csv` — no versioning churn on these, they're fixed by our own honour-system declaration.
- Everything else added for T4 completeness lives under `/api/v1/...`, documented in the OpenAPI schema Django Ninja generates automatically from the typed request/response schemas (never from raw models — the Ninja `ModelSchema` footgun, AUTHZ/RESEARCH §7.5).
- Consistent error shape on every 4xx/5xx from any API route: `{"error": "<code_string>", "detail": "<human message>"}`.
- List endpoints (gallery, assignments, audit log) take `?page=&page_size=` with sane defaults (20/page) — cheap to add now, avoids an awkward retrofit later even though the real fixture's 41 projects wouldn't strictly need it yet.

## 2. Endpoint inventory, grouped by service module

### `accounts` (new — see §3, real users need this even though the checker never logs in)
| Method + path | Service call | Auth |
|---|---|---|
| `POST /accounts/register` | `services.accounts.register(email, password)` | anon |
| `POST /accounts/login` | `services.accounts.login(email, password)` | anon |
| `POST /accounts/logout` | `services.accounts.logout(actor)` | any |

### `events` / `teams` / `submissions` (T1)
| Method + path | Service call | Auth |
|---|---|---|
| `GET /events/{slug}` | `services.events.get(slug)` | public |
| `GET /projects` | `services.submissions.gallery(actor, q=, track=, tag=)` | public (submitted only, per D-13) |
| `GET /projects/{id}` | `services.submissions.get(actor, id)` | public if submitted, else owner/organizer (AUTHZ §3.1) |
| `POST /projects/new` | `services.submissions.create(actor, team, ...)` | participant, own team, event open |
| `PATCH /projects/{id}` | `services.submissions.update(actor, id, ...)` | owner participant, before deadline |
| `POST /teams` | `services.teams.create(actor, event, name)` | any registered user |
| `POST /teams/{id}/join` | `services.teams.join(actor, id, code)` | any registered user |

### `judging` (T2)
| Method + path | Service call | Auth |
|---|---|---|
| `GET /api/judge/scores` (+ optional `?judge=`) | `services.judging.get_scores(actor, judge_external_id=None)` | the exact spec.md route — AUTHZ §3.2, corrected function per STRESS-TEST.md F1 |
| `POST /api/v1/ballots/{assignment_id}` | `services.judging.submit_ballot(actor, assignment_id, scores, comment)` | assigned judge, own assignment |
| `GET /api/v1/organizer/progress` | `services.judging.progress(actor)` | organizer |
| `POST /api/v1/organizer/assignments/run` | `services.assignment.run(actor, k, seed=None)` | organizer |
| `GET /api/v1/organizer/assignments/{run_id}` | `services.assignment.get_run(actor, run_id)` | organizer |
| `POST /api/v1/organizer/normalization/run` | `services.normalization.run(actor)` | organizer |
| `GET /api/v1/organizer/normalization/{run_id}` | `services.normalization.get_run(actor, run_id)` | organizer — the Normalization Proof artifact |
| `GET /api/export.csv` | `services.judging.export_csv(actor)` | the exact spec.md route |

### `voting` (T3 — RESEARCH A14: build the human-verification story around these, not just the routes)
| Method + path | Service call | Auth |
|---|---|---|
| `GET /vote/{event}` | `services.voting.get_ballot(actor, event)` — ordered per V-03 | mode-dependent |
| `POST /vote/{event}/{project}` | `services.voting.cast(actor, event, project)` | mode-dependent, rate-limited |
| `GET /results/{event}` | `services.voting.get_results(actor, event)` — gated per V-02 | organizer during window, everyone after close (no separate toggle — F10) |
| `POST /projects/{id}/comments` | `services.voting.comment(actor, id, body)` | mode-dependent |
| `POST /api/v1/organizer/comments/{id}/flag` | `services.voting.flag_comment(actor, id)` | organizer |

### `api` (T4 completeness)
| Method + path | Service call | Auth |
|---|---|---|
| `GET /api/openapi.json` | Ninja auto-generated | public |
| `GET /judges/{id}/record.json` | `services.records.get_signed(id)` | public — deliberately open, RESEARCH §7.8: verification happens offline against the public key, not by trusting the server |
| `POST /api/v1/organizer/webhooks` | `services.webhooks.register(actor, url, events)` | organizer |
| `GET /api/v1/organizer/audit-log` | `services.audit.list(actor)` | organizer |
| `GET /api/v1/organizer/audit-log/verify` | returns the standalone verify script + current chain head hash | organizer (script itself runs with no server, per RESEARCH §7.5) |

## 3. `accounts` — a gap the checker doesn't test but the demo video needs
Nothing so far designs how a *real* participant or judge gets an `AuthToken` outside the seeded test personas (SCHEMA §0.2/§2). Minimal, service-layer-consistent design: `User` gets a `password_hash` field (Django's own hasher); `POST /accounts/register` and `/login` create/validate and then create (or reuse) an `AuthToken`, set as a cookie — the exact same mechanism the seed script uses for the four required personas, just reached through a real form instead of a fixture import. This keeps a single auth code path for both "seeded test judge" and "real signed-up judge," rather than two parallel systems — one less thing to get subtly inconsistent. **Updates SCHEMA.md**: add `User.password_hash` (nullable — fixture-imported judges have none and can't log in with a password, only via their printed seed token, which is correct: they're test fixtures, not real accounts).

## 4. Open items for G3/G7
- Whether `PATCH /projects/{id}` supports partial field updates or requires the full object — leaning full-object (simpler validation, and Django Ninja's schema validation is cleaner against a complete shape) unless the judge-console-equivalent submit form makes partial updates clearly better once drawn.
- Webhook delivery retry policy (T4, lowest priority per the cut order) — not designed in detail now, deferred to G7 if reached at all.
