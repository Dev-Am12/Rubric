# DogFood 2026 — Master Plan

**Rev 14 · 2026-09-26 · Status: STRESS-TESTED, kickoff is on Sun 2026-09-26 23:30 IST (RESEARCH §2) — no heavy work until building starts (DL-041)**
Companion docs: `RESEARCH.md` (facts, spec audit, domain notes) · `LOGS.md` (decisions, sessions, blockers, findings journal) · `STRESS-TEST.md` (full audit findings + fixes, 2026-09-25) · SCHEMA/AUTHZ/NORMALIZATION/ASSIGNMENT/VOTING/API/UX/DOCKER/DOCS-PLAN/PROMPTS/SCHEDULE.md (backlog items 1–11).

---

## 0. Rules for these docs

1. **Single source of truth = the owner's copy.** Claude edits only a copy the owner has just re-uploaded, and every edit bumps `Rev` and adds a line to LOGS.md "Doc changelog". (Playbook: the shared decision log collided three times from stale copies.)
2. **Keep this folder out of the submission repo until kickoff.** Any *project code* committed before the new kickoff time (Sun 2026-09-27, 18:00 UTC / 23:30 IST — postponed twice from the original Sep 25, see RESEARCH §2) disqualifies. Docs are not code, but there's no reason to test that boundary.
3. **Solo mode:** no teammates to collide with, but the chat, this folder and any coding agents are three "collaborators". The rule above covers all of them.
4. Anything not confirmed by the owner is marked PROPOSED, not DECIDED.

---

## 1. Goal and scoring model

**Targets:** top 5 overall · top 4 in the Write Up Quest · attempt Best Judging Engine. Everything else is means.

**Points arithmetic (0–5 scale, weighted average across judges) — corrected from spec.md, 2026-09-23:**
- A +1.0 improvement in one criterion moves the final score by: Tier Completion & Correctness **+0.40** · Judging Integrity **+0.25** · Adoptability **+0.20** · Code Quality & Innovation **+0.15**.
- **Bonuses do NOT add to this score.** Corrected from our earlier (wrong) assumption that a bonus was worth roughly +0.25. spec.md is explicit: *"Your score is the weighted average of the four criteria above... Bonuses break ties between projects that land on the same number, and they decide the Best Judging Engine prize."* There is no arithmetic bonus at all — see RESEARCH §7.0 for what this changes about priority.
- Margins between places at Raptors events are thin (playbook example: 0.162 separated four places), so **each verified fix is worth real placement**. A broken compose file or a role leak costs far more than any polish gains.
- **New structural fact (RESEARCH §2.2):** the official `verified` tier list is sequential-gated — a single failing T1 check zeroes T2 credit in the report even if every T2 check independently passes. T1 must never regress, at any point in the build, even during T2/T3 work (see V10).
- **New open question (RESEARCH §5, A14):** `run.py` structurally never checks T3 or T4 — there is no code path that could ever mark them "verified." Any T3/T4 credit toward the 40% has to come from a judge manually running/reading the portal. Build T1+T2 for the guaranteed, machine-proven credit; build T3 to be *trivially* human-verifiable (obvious UI, explicit in the demo video and docs) since that's the only channel available for it at all.

### 1.1 What costs points (ranked by damage) and what stops it

**S0 — score zero, disqualified, or silently capped**
| Risk | Prevention | Verifying test |
|---|---|---|
| Any project code before kickoff | Rule A11: environment checks only | Repo has zero commits until T-0 |
| T1 not cleared | T1 is the first milestone (G2), acceptance-checked | Acceptance report T1 all pass |
| **A later T1 regression silently zeroes T2 credit** (tier-gating, new) | Run the full official `run.py` on every push, in tier order; any T1 FAIL is treated as a P0 blocker regardless of what's being worked on | V10 |
| Compose fails on a clean laptop / needs network at runtime | Clean-room CI from G0; offline job; no external assets | CI: fresh clone → up → suite → egress-blocked rerun |
| Role leak reachable by `curl` | Service-layer policy; generated route×role matrix; the exact `peer_scores` trap in RESEARCH §7.5 is our named test case | Matrix test + control case |
| Hardcoded/mock frontend | Every screen reads the DB via the service layer | Suite + demo video walks a real lifecycle |
| Missing/indefensible ARCHITECTURE / DATA-MODEL / JUDGING | Docs written as-built | Docs-consistency tests; owner reads them cold at G8 |
| Non-OSI license / private repo / rewrite of existing platform | License file at T-0; public at submission | Freeze checklist |

**S1 — large point losses**
- Overclaimed tiers in `.dogfood.toml` (spec.md names this "the one thing that actually costs you points") → generated from the actual acceptance report, never hand-typed.
- The real fixture edge cases (RESEARCH §2B: constant judge `jdg_07`, the 8 thin batches including `prj_19`, the `tm_07` duplicate `prj_07`/`prj_41`) mishandled → planted-truth tests against these *exact* IDs, not generic placeholders.
- "We averaged the scores" → documented policy + planted-truth tests.
- Django admin or ORM shortcuts bypassing policy → admin not shipped; actor-scoped querysets only.
- A CDN URL or webfont fetch anywhere → static scan + egress-blocked run.
- Deadline not holding, or seeded with our own date instead of the fixture's real `submissions_close` (`2026-03-01T18:00:00Z`) → DB time, one transaction, boundary + concurrency tests, seed from the loaded fixture verbatim.
- Docs contradict each other or the code → docs-consistency tests.
- **A critical finding left unresolved at freeze** (playbook's costliest lesson) → blockers register with explicit closure.
- Claims judges can't reproduce → each claim has a one-command check inside the standard test run.

**S2 — small but free to avoid**
Stale TODOs; leftover debug prints; alarming-looking demo secrets left unexplained; Windows line-ending breakage; unpinned dependencies; missing third-party license file.

### 1.2 What wins (ranked by expected points per unit effort)
1. **T1 + T2 flawless and suite-proven** — the only tiers `run.py` can ever verify; 40%, and the tier-gating in §1.1 makes T1 the single highest-leverage thing not to break.
2. **Judging Integrity made visible:** the isolation matrix (anchored on the real `peer_scores` trap), documented normalization with a proof table on the real edge cases, a hash-chained audit log a human can read (25%, also Best Judging Engine). Normalization Proof, Threat Model, and API First are largely *free* here — RESEARCH §7.0 shows they're the natural output of doing this criterion and the T3/Adoptability criteria well, not separate investments.
3. **Adoptability a stranger can verify in a minute:** one command, seeded (with the real fixture's own dates/entities), honest docs, import/export (20%).
4. **A T3 built for human verification**, since it can never appear in the acceptance report (A14) — obvious UI, explicit in the demo video.
5. **One idea a judge would steal** (15%, plus the write-up — the `jdg_07`/`prj_19` compounding edge case, RESEARCH §2B, is a strong, real candidate).
6. **Honest gap reporting** — spec.md rewards this explicitly ("a report with two honest FAIL lines reads better than a README claiming everything works").
7. **Pairwise Mode**, last — the one genuinely separate bonus with no base-rubric credit of its own; attempt only with slack time (RESEARCH §7.0/§7.2).

---

## 2. Decisions

### 2.1 Locked (owner decided)
| ID | Decision | Revisit only if |
|---|---|---|
| L-01 | **Django** as the framework | Something before coding starts forces a change |
| L-02 | **Solo** participation | — |
| L-03 | No questions to organizers unless a hard blocker (RESEARCH §5) | — |
| L-04 | Maintain PLAN / RESEARCH / LOGS before building | — |

### 2.2 Proposed (Claude's recommendation)
| ID | Decision | Why |
|---|---|---|
| P-01 | Django 5.2 LTS, Python 3.12. **Pin `Django>=5.2.13`** — CVE-2026-33033 (multipart-parser DoS) is fixed there | LTS = adoptable; the pin removes an open question |
| P-02 | PostgreSQL (2 containers: web + db) | Trigger-enforced append-only audit log, row locking for deadlines, CHECK constraints |
| P-03 | Service layer with explicit actor-based authorization; HTML views and API are thin wrappers | One place to prove isolation; makes the `peer_scores` trap (RESEARCH §7.5) unexploitable by construction |
| P-04 | Django Ninja for the API (OpenAPI from typed schemas) | Less boilerplate, OpenAPI for free |
| P-05 | Server-rendered templates + HTMX + hand-written CSS with design tokens; no Node in the image; all assets vendored | Offline, one toolchain, smaller image |
| P-06 | gunicorn + whitenoise; no nginx/Redis/Celery | Fewer moving parts |
| P-07 | Ed25519 via `cryptography` for signed records; reportlab for certificates | Pure wheels, no system libs |
| P-08 | Don't ship Django admin | It bypasses the policy layer |
| P-09 | License: Apache-2.0 (MIT acceptable) | Both adoptable "without a legal conversation" |
| P-10 | Repo layout exactly matches spec.md's tree (`.dogfood.toml`, `acceptance-report.txt`, `docker-compose.yml`, `README.md`, `ARCHITECTURE.md`, `DATA-MODEL.md`, `JUDGING.md`, `LICENSE`, `src/`, `tests/`) | This is now the confirmed, exact expected layout — zero reason to deviate |
| P-11 | Adopt spec.md's example route names verbatim: `gallery=/projects`, `submit=/projects/new`, `judge_scores=/api/judge/scores`, `peer_scores` = the same endpoint with `?judge=<id>`, `csv_export=/api/export.csv` | Route names are entirely our choice per spec.md, but the example is clean and well-considered — adopting it is a free decision saved |
| **P-12 (new)** | Standalone `AuthToken` model + middleware for auth, decoupled from Django's built-in session framework | The checker "never logs in," just attaches a raw header (RESEARCH §2.1) — a dedicated token table makes deterministic, printable seed credentials trivial and works identically for real users; full design in SCHEMA.md §0.2 |

### 2.3 Open decisions with defaults (nothing decided under time pressure; the default applies unless we reconsider)
| ID | Question | Default |
|---|---|---|
| D-01 | Primary normalization method | Judge-effect shrinkage model (RESEARCH §7.1) as primary; per-judge z-score with pooled-σ shrinkage as shown baseline; raw always shown |
| D-02 | Duplicate entry (real case: `tm_07`'s `prj_07`/`prj_41`) | **Refined in NORMALIZATION.md §1 (D-02)**: the later submission becomes canonical by default (matches ordinary "resubmission = fix/finalize" intent); the earlier one is flagged, excluded from ranking/gallery, never deleted, and the auto-flag is itself audit-logged and one-click reversible by the organizer |
| D-03 | Constant-score judge (real case: `jdg_07`) | Keep for offset information, exclude from scale estimation, flag on dashboard |
| D-04 | Incomplete batch (real case: the 8 projects with only 2 reviews, incl. `prj_19`) | Rank on available ballots, display review count and confidence, flag projects under the target review count |
| D-05 | Disconnected judge–project graph | Moot on the real fixture (single connected component, RESEARCH §2B) — still compute and report the Fiedler value for whatever assignment we generate ourselves |
| D-06 | Rate-limit store | Postgres-backed counters (per-process memory is bypassed by multiple workers) |
| D-07 | Email-gated voting offline | Console/file mail backend + organizer "outbox" page; SMTP optional via env |
| D-08 | Demo credentials | Documented seed accounts, printed at boot in the spec's own worked-example style ("seeded. test logins: ...") |
| D-09 | Dependency install | Pinned + hashed lockfile; hermetic wheel bundling (RESEARCH §7.6) — build-time network allowed per A4, runtime fully offline |
| D-10 | Judge invitation without email | Invite links shown to organizer + outbox entry |
| D-11 | Map the 4 required test personas onto real fixture entities | Full mapping now designed in SCHEMA.md §2: `judge_a` → `jdg_07` (constant-score judge) · `judge_b` → `jdg_29` (co-reviewer of `prj_19` with `jdg_07`) · `participant` → a member of team `tm_07` (the duplicate-submission team, so browsing "my submissions" demos duplicate-flagging live) · `organizer` → a dedicated seed account (fixtures.json has no organizer role at all) |
| **D-13 (new)** | Are draft (not-yet-submitted) projects visible in the public gallery? | No — only `SUBMITTED` projects appear. Costs nothing against the suite (all 41 real fixture projects import as already-submitted) and avoids leaking half-finished ideas to competitors (AUTHZ.md §3.1) |
| **D-14 (new)** | 403 vs. 404 default for unauthorized access | 403 everywhere by default (reveal existence, deny access) except where hiding existence is itself the point — none of our required routes need that, so 403 is the blanket default (AUTHZ.md §6) |

---

## 3. Scope strategy

**Must (non-negotiable):** T1 · all of T2 · compose one-command + offline · seeded fixtures (real dates/entities) · acceptance report · README/ARCHITECTURE/DATA-MODEL/JUDGING · demo video · audit log.
**Should:** T3 core (voting modes with hidden results, randomised ballots, comments, rate limits, duplicate detection), built for easy human verification since it's never suite-checked (A14) · CSV export at every stage · REST API + OpenAPI (parity with the UI).
**Could:** T4 items ranked by cost-effectiveness below.

**Won't (unless free time with zero risk to a Must):** a deployed live demo link. The Discord submission form asks for one "if deployed", but it's optional there and spec.md's closed-loopholes explicitly say a staging URL is not a submission — `docker compose up` is what's judged.

**Reframed bonus picks (RESEARCH §7.0 — this changed materially once we learned bonuses don't add points):** Normalization Proof, Threat Model, and API First are not really *bonus investments* — they are the literal wording of Judging Integrity (25%) and Adoptability (20%), so we build them as core rubric work regardless of whether the bonus checkbox exists. **Pairwise Mode is the one genuine, separate bonus** with no other rubric line asking for it — it stays the lowest-priority item, attempted only with real slack at G7, exactly matching spec.md's own "not because you are chasing arithmetic" framing.

**Cut order (cut first → last):** Pairwise Mode → embeddable widget → certificates → webhooks → quadratic-voting alternative → Devpost-CSV import → signed records → comments → T3 anti-abuse depth. **Never cut:** anything in "Must".

**T4 cost-effectiveness (provisional, low-stakes given A14 — T4 is never suite-verified):** API + OpenAPI (cheap given P-03/P-04, and it's core Adoptability work anyway) > bulk import/export (needed anyway) > signed records (cheap if the audit log is hash-chained) > webhooks > certificates > widget.

**Differentiator strategy (decided 2026-09-24): core rock-solid first, then attempt signature features one by one in priority order as time permits — no single "must-have" pick.** Proposed order, cheapest/most-load-bearing first (override anytime if reality looks different once we're building):
1. **Graph health (Fiedler value + connectivity report)** — first, because it's nearly free: the math is already written (RESEARCH §7.3), it falls out of the assignment/normalization work we're doing anyway, and it's direct JUDGING.md content and Best Judging Engine evidence. Treat this as part of "core," not a stretch.
2. **Rank uncertainty (bootstrap CI on normalized rankings, showing statistically tied ranks)** — second: moderate effort, directly strengthens the Normalization Proof and Best Judging Engine case, natural once the shrinkage normalization itself is done (G4–G5).
3. **Judge disagreement heatmap (visualize score divergence, before/after normalization)** — last: most visually memorable for the demo video, but the most UI-heavy of the three. Only attempt if G6/G7 have real slack.
None of these ever outrank a Must or Should — they're pulled from the same slack time as the bonus items below, and the cut order still governs.

**Cheap second differentiator, independent of the above:** hash-chained, tamper-evident audit log with a public verify command (RESEARCH §7.5) — build this regardless, it's core Judging Integrity work either way.

---

## 4. Build order and checkpoints (provisional; hours elapsed since T-0 = **Sun 2026-09-27 23:30 IST** — postponed twice from the original Fri 2026-09-25, RESEARCH §2. Elapsed-hour gates below are unaffected)

The order is riskiest-first. From G2 onward every checkpoint is a submittable state.

| Gate | Elapsed (IST) | Deliverable |
|---|---|---|
| G0 | 0–3 h (Fri 23:30 → Sat 02:30) | Walking skeleton: repo, LICENSE, compose (web+db), healthcheck, migrations, seed stub loading the **real** `fixtures.json` (verbatim `submissions_close`), clean-room CI, place `run.py`+`fixtures.json` at repo root, **first real run against the actual `run.py`** (not a guess — we have it), egress-blocked job |
| G1 | 3–10 h | Data model, auth/sessions, roles, **policy layer + route×role matrix skeleton**, events/tracks/prizes, the P-11 route names wired up |
| G2 | 10–20 h | Teams by invite, submissions with drafts and deadline, gallery + search/filter. **T1 acceptance green against the real `run.py`** |
| G3 | 20–30 h | Judges, invitation, assignment, weighted rubric, ballots, isolation tests anchored on the real `peer_scores` trap, D-11 persona mapping wired up |
| G4 | 30–42 h | Normalization (planted-truth tests on `jdg_07`/`prj_19`/the 8 thin batches), progress dashboard, CSV export at each stage |
| G5 | 42–50 h | **T2 acceptance green**; JUDGING.md complete; audit log UI; V10 (tier-gating CI rule) enforced from here on |
| G6 | 50–58 h | T3 core, built for human verifiability (A14); write-up thesis chosen from real findings |
| G7 | 58–64 h | Cheap T4 items done as core-rubric work (API parity, import/export); Pairwise Mode only if genuinely ahead |
| G8 | 64–69 h | Hardening: clean-room, Windows fresh clone, offline run, docs-consistency, TODO sweep, blockers all CLOSED |
| G9 | 69–72 h | Demo video, tag `submission-v1`, acceptance report committed, submit |

**Monday Sep 28 constraint: dev unavailable roughly 2–4 h Monday morning.** Freeze is Mon 23:30 IST (elapsed 72h); Monday 00:00 IST is elapsed ~48.5h. A ~2–4h Monday-morning gap most plausibly overlaps roughly elapsed hour 56–61 — squarely inside **G6 (T3 core)**. Since T3 is never suite-verified anyway (A14) and is the most compressible item in the cut order, treat G6 as the gate to compress or partially shift earlier if that gap is looming, rather than letting it eat into G7/G8 hardening time, which sits after the gap and is not compressible (V10, docs, clean-room checks, the demo video all live there). This is a personal scheduling note only — it does not change scope, quality, or which tiers we target; the cut order already absorbs it.

Sleep is scheduled, not hoped for — **see SCHEDULE.md (backlog item 11) for the real clock**: three blocks (~4.5h, ~6h, ~4.5h) placed at actual nights rather than rigid gate boundaries, with the Monday-morning availability gap folded in as a fourth, smaller absence. Solo fatigue is the biggest single-person risk; the cut order exists so sleep never costs a Must.

---

## 5. Workflow

### 5.1 Roles (ASSUMPTION — confirm)
Claude = planner, prompt designer, reviewer, doc partner. Implementation by coding agents, driven by prompts Claude writes. Claude does not implement unless asked.

### 5.2 Definition of done (per feature)
1. Implemented through the service layer with a policy check.
2. Route×role matrix row + negative tests (other judge, other track, other owner) — including the `peer_scores` trap specifically for anything touching judge scores.
3. Audit-log entry for every state change.
4. API parity (OpenAPI entry).
5. As-built doc line in ARCHITECTURE / DATA-MODEL / JUDGING (written now, not on Sunday).
6. Relevant acceptance step passes — **against the real `run.py`**, not an assumption of what it might check.
7. Findings-journal entry if anything surprised us.

### 5.3 Verification stack
| ID | What | Notes |
|---|---|---|
| V1 | Clean-room CI on every push | fresh clone → compose up → **the real `run.py`** → egress-blocked rerun → upload report |
| V2 | Route×role×owner matrix generated from URLconf/OpenAPI | Fails on any unclassified route; **control case** = a deliberately leaky test-only route must be caught; anchored on the real `peer_scores` endpoint shape |
| V3 | Planted-truth normalization tests | On the **real** fixture edge cases: `jdg_07` (constant), the 8 thin batches incl. `prj_19`, `tm_07`'s duplicate; plus synthetic offset/scale cases and a NaN/Inf guard |
| V4 | Oracle fixtures | Independent implementation (reference outputs generated once, committed as static files) |
| V5 | Deadline tests | ±boundary, concurrent submissions, server time only, seeded from the real `submissions_close` |
| V6 | Air-gap tests | Static scan for external URLs + egress-blocked run |
| V7 | Docs-consistency tests | tiers in `.dogfood.toml` == `acceptance-report.txt`; endpoints documented == OpenAPI; documented limits == constants; no TODO/FIXME |
| V8 | Negative-property tests | Exports don't mutate state; embargoed results really invisible; audit log rejects UPDATE/DELETE at DB level |
| V9 | Second-environment check (redefined 2026-09-25, DOCKER.md §6.6) | No local Windows machine is available at all now. Substitute: every Actions run is already a fresh ephemeral Linux VM, and the compose design never bind-mounts source (sidesteps the most common Windows-Docker friction point). Honest gap stated in README — this is not equivalent to a real Windows test |
| **V10 (new)** | **Tier-gating CI rule** | The full official `run.py` runs on every push, tiers checked in order; **any T1 FAIL is a P0 blocker regardless of what's currently being worked on**, because a single T1 regression silently zeroes T2 credit in the official report (RESEARCH §2.2). Never let a T2/T3 feature branch merge on top of a broken T1. |

### 5.3a Commit discipline — drafted by agents, executed only by the owner
The repo needs regular commits through the whole 72 h, not one large dump near the end — a sparse-then-sudden history reads as code written outside the window even when it wasn't.

**No agent — coding agent or Claude — ever runs a git write command:** no `commit`, `push`, `merge`, `rebase`, `reset`, `tag`, `checkout -b`, etc. Read-only git (`status`, `log`, `diff`, `show`, `branch --list`) is fine for any agent to inspect state. At the end of every meaningful step, the agent proposes a commit — title, short description, files covered, and the requirement/decision/V-check it satisfies — and the owner reviews and runs the actual `git commit` (and any push or tag) themselves. No squashing the whole event into a handful of commits at G9.

### 5.3b Cross-agent sync protocol
Whichever agent makes a change — implementation agent or Claude — the change isn't done until:
1. A proposed commit message (title + description, for the owner to use) references the requirement/decision/V-check it satisfies.
2. Code comments explain *why*, not just what, for anything touching the policy layer, normalization, or deadline handling.
3. LOGS.md session log gets a line before the session ends: what changed, what's next.
4. Any new/changed decision goes into the PLAN §2 decision tables or LOGS §1 decision log in the same session it was made, not retroactively.
5. PLAN/RESEARCH get updated in the same session if a change invalidates an assumption, a cut-order item, or a locked/proposed decision.
This keeps every agent picking up work mid-event able to read PLAN + RESEARCH + LOGS and know the true current state, without needing the conversation that produced it.

### 5.4 Docker/environment plan — revised 2026-09-25: no local machine can run Docker at all
Full strategy and reasoning in DOCKER.md §6 (backlog item 8, updated by STRESS-TEST.md F4). Summary:
- I write Dockerfile/compose/entrypoint/healthchecks; **I can't run Docker in my sandbox**, so nothing is trusted until it has run on a real host — and now neither can the owner, locally, at all.
- **Local dev loop**: PostgreSQL installed natively (no Docker) on the dev machine, Django run directly against it — full DB parity, fast iteration, no container needed for day-to-day work. *(Depends on being able to install it — see the open question in DOCKER.md §7.)*
- **Repo is public from kickoff**, not just at submission — unlimited GitHub Actions minutes, which matters more now that Actions carries the primary Docker-verification load.
- **GitHub Actions**: the primary, frequent clean-room + offline-check loop (DOCKER.md §5) — push after every meaningful step, not just at gates.
- **A manually-triggered SSH-into-runner debug job** (DOCKER.md §6.4) as a free, on-demand interactive Docker environment when Actions logs alone aren't enough — no Codespaces cost.
- **GitHub Codespaces**, budgeted at ~5–7 hours total across exactly two sessions: an early skeleton-boots-at-all check, and the final pre-freeze dry run. Not a continuous environment (120 free core-hours/month wouldn't support that anyway).
- `.gitattributes` forces LF; entrypoints invoked via `sh`; multi-arch base images; non-root user; `depends_on: service_healthy`.
- **V9 is redefined, not dropped** (DOCKER.md §6.6): no literal Windows test is possible now; mitigated by Actions' ephemeral-VM freshness and a no-bind-mount compose design, with the honest gap stated plainly in README.
- Pre-kickoff: **environment checks only**: confirm Actions/Codespaces work on an empty (public) repo; **dry-run the real `run.py` against nothing/a stub** to see its exact error behavior (running the organizers' own released script, not project code — explicitly allowed). No project code.

### 5.5 Findings journal → write-up
LOGS.md "Findings journal" gets an entry the moment something surprises us. Winning write-up pattern from the playbook: **one** thread chased to root cause, an honest numbers table, cheerful honesty. Strongest candidate thread, now that we have real data (RESEARCH §2B): **the `jdg_07`/`prj_19` compounding edge case** — a constant-score judge landing on one of the already-thin 2-review batches — chased through detection, the shrinkage math, and its effect on the final ranking. Other candidates: the `peer_scores` trap itself as a bug we deliberately built a test for (and the isolation-function bug the stress test itself caught before any code existed — a legitimate pre-mortem story); the `tm_07` duplicate-handling policy. Write-up closes Oct 5 23:30 IST.

### 5.6 Freeze and submission checklist
All items in LOGS.md blockers register CLOSED with evidence · fresh-clone run on a non-author environment · egress-blocked run · acceptance report (real `run.py` output) added to the repo and matching `.dogfood.toml`'s `claimed` line · docs-consistency green · TODO/debug sweep · third-party licenses file · no real secrets · owner tags `submission-v1` and README line `git diff submission-v1 --stat -- src/` · README states plainly what does NOT work · demo video (≤5 min, one full lifecycle: create → submit → judge → publish) · repo public · reachable contact for follow-up.

---

## 6. Pre-kickoff checklist (2026-09-23 → **2026-09-27**, kickoff date postponed twice — see RESEARCH §2)

- [x] ~~Sep 24: read spec.md~~ — **done early**, spec.md/run.py/fixtures.json/context.txt all in hand as of 2026-09-23. Spec-delta procedure below is complete (folded into RESEARCH Rev 4).
- [ ] **Register individually** via the form in Discord `#announcements` (required even solo).
- [ ] Skim Discord (read-only) for any errata added to spec.md since 2026-09-23 (spec.md itself says a repeated question gets a line added).
- [ ] Agree the commit discipline (§5.3a) before G0 — agents draft commit titles/descriptions, only the owner runs git.
- [x] ~~Docker check on each Windows machine~~ — **moot as of 2026-09-25: no local machine can run Docker at all.** Revised strategy in DOCKER.md §6 / PLAN §5.4 (public repo from kickoff, Actions as primary verification, Codespaces budgeted for two sessions). Native PostgreSQL install is the one action item remaining — see the open question in DOCKER.md §7.
- [ ] GitHub: empty repo reserved, Actions enabled, Codespaces available. No commits.
- [ ] Coding agents: confirm which, verify quotas, agree the role boundary (§5.1).
- [ ] Paper designs (allowed, not project code): schema draft against the **real** fixture shape (RESEARCH §2B), authorization matrix, normalization policies (D-01…D-05), planted-truth test specs against the real edge-case IDs, ballot/audit-log design.
- [ ] Prompt-library skeleton (templates, no project code).
- [ ] Demo storyboard (create → submit → judge → publish), incorporating the `jdg_07`/`prj_19` case as a visible beat.
- [ ] Dry-run the actual `run.py` against nothing/a stub server to see its real error output firsthand (allowed — it's the organizers' own script).
- [x] ~~Sleep/availability plan incl. Monday~~ — **noted: dev unavailable roughly 2–4 h Monday morning**; folded into §4's build order note (G6 is the gate to compress around it). Scheduling only — does not change scope or targets.
- [ ] Food, power, connectivity backup.

---

## 7. Risk register

| ID | Risk | Impact | Mitigation |
|---|---|---|---|
| R1 | ~~Suite's interface differs from A1~~ **RETIRED** — we have the real `run.py`, fully known | — | — |
| R2 | No local machine can run Docker at all (confirmed 2026-09-25) | High | Native local Postgres for dev parity + Actions as primary verification + budgeted Codespaces sessions (DOCKER.md §6) |
| R3 | Agent quota runs out | High | Fewer, larger, well-specified prompts; priority order = cut order |
| R4 | Solo fatigue | High | Scheduled sleep; Musts first |
| R5 | ~~spec.md invalidates assumptions~~ **RETIRED** — spec.md is in hand and folded in (RESEARCH Rev 4) | — | — |
| R6 | The real fixture edge cases (`jdg_07`, the 8 thin batches, `tm_07`'s duplicate) mishandled | High | Planted-truth tests against the exact real IDs (V3) |
| R7 | Role leak, specifically via the `peer_scores` `?judge=<id>` pattern | Critical | V2 + control case, anchored on the exact trap spec.md hands us |
| R8 | Docs drift | Med | V7 |
| R9 | Pre-kickoff rule violation | Critical | Rule A11 |
| R10 | Offline build ambiguity | Med | Hermetic as practical (D-09) |
| R11 | Scope creep | Med | Cut order; rubric-priced trade-offs |
| R12 | Windows-only build bug, now elevated — no way to test this ourselves at all | Med-High | V9 (redefined) + Linux CI + no-bind-mount design + honest README disclosure |
| R13 | Thin write-up material | Med | Findings journal from hour 0; strong real candidate thread now identified |
| R14 | Django admin/ORM bypass of policy | High | P-08, actor-scoped managers, V2 |
| **R15 (new)** | **A later T1 regression silently zeroes T2 credit** (tier-gating in `run.py`) | Critical | V10 |
| **R16 (new)** | Over-investing in Pairwise Mode, the only bonus with no base-rubric credit, at the expense of a Must/Should | Med | Cut order places it last; RESEARCH §7.0 reframing |

---

## 8. Planning backlog — CLOSED (2026-09-24, day before kickoff)

All 11 items done. Each is its own file, cross-referenced from here and from PLAN's decision tables above:

1. ~~Domain model and schema~~ — SCHEMA.md
2. ~~Authorization matrix and policy-layer design~~ — AUTHZ.md
3. ~~Normalization: policies, method, planted-truth tests~~ — NORMALIZATION.md
4. ~~Assignment algorithm and graph health~~ — ASSIGNMENT.md
5. ~~T3: voting, abuse model, threat model~~ — VOTING.md
6. ~~API/OpenAPI shape and service-layer boundaries~~ — API.md
7. ~~UI/UX: judge console, organizer dashboard, gallery~~ — UX.md
8. ~~Docker/CI design and offline verification~~ — DOCKER.md
9. ~~Docs outlines and demo storyboard~~ — DOCS-PLAN.md
10. ~~Coding-agent prompt library~~ — PROMPTS.md (kept generic — no tool names/quotas)
11. ~~Hour-by-hour schedule~~ — SCHEDULE.md (real clock, sleep at actual nights)

**Next phase, per the owner's own sequencing:** a full stress test of the whole plan — out of scope for this session, picked up separately.
