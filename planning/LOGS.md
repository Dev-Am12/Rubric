# DogFood 2026 â€” Logs

**Rev 14 Â· 2026-09-26**
Append-only during the event. Newest entries at the bottom of each section. Timestamps in IST unless noted.
Rule: edit only the owner's latest copy (PLAN Â§0).

---

## 1. Decision log
Format: `ID Â· date Â· DECIDED/PROPOSED Â· decision Â· reason Â· what would reopen it`

| ID | Date | Status | Decision | Reason | Reopen if |
|---|---|---|---|---|---|
| DL-001 | 2026-09-21 | DECIDED | Participate solo | Owner's call; freedom and no communication risk | â€” |
| DL-002 | 2026-09-21 | DECIDED | Framework: Django (locked for now) | Best fit after comparing Django / FastAPI+SPA / Next.js / Rails: fastest to a correct T2, strong test tooling for authorization, Python for the statistics | Something before coding forces a change |
| DL-003 | 2026-09-21 | DECIDED | Don't ask organizers questions unless a hard blocker | Work from best understanding; read Discord instead | Hard-blocker test in RESEARCH Â§5 is met |
| DL-004 | 2026-09-21 | DECIDED | Maintain PLAN / RESEARCH / LOGS pre-build | Keeps planning rigorous and portable across sessions | â€” |
| DL-005 | 2026-09-21 | PROPOSED | PostgreSQL, service-layer authorization, Ninja API, HTMX UI, no admin (PLAN Â§2.2) | See PLAN Â§2.2 | spec.md conflict |
| DL-006 | 2026-09-21 | PROPOSED | No domain code before kickoff; environment checks only | Disqualification risk vs tiny benefit | Owner disagrees |
| DL-007 | 2026-09-21 | PROPOSED | Keep planning docs outside the submission repo until kickoff | Same reason | Owner disagrees |
| DL-008 | 2026-09-21 | DECIDED | Treat the Discord `#announcements` pinned message as reliable for process facts (registration, submission-form timing, commit cadence) but not as replacing the site's Deliverables list, since it reads as a generic template reused across Raptors events | It lists none of DogFood's specific required docs even though the site requires them | spec.md or a DogFood-specific Discord post says otherwise |
| DL-009 | 2026-09-21 | DECIDED | Commit continuously through the 72 h (see PLAN Â§5.3a); no large late-dump commit history | Discord: "regular commits" required | â€” |
| DL-010 | 2026-09-21 | DECIDED | A deployed live demo link is optional and lowest priority â€” never at the cost of a Must/Should item | Discord form says "if deployed"; site's closed loopholes say a staging URL isn't the submission | â€” |
| DL-011 | 2026-09-21 | DECIDED | Cross-agent sync protocol (PLAN Â§5.3b): every code change carries a proposed commit message the agent drafts for the owner to use, rationale comments on sensitive code, and a same-session LOGS/PLAN/RESEARCH update | Keeps any agent picking up mid-event able to read the docs and know true current state | â€” |
| DL-012 | 2026-09-21 | DECIDED | No agent â€” coding agent or Claude â€” ever runs a git write command (`commit`, `push`, `merge`, `rebase`, `reset`, `tag`, etc.); read-only git (`status`, `log`, `diff`, `show`) is fine. Agents draft commit titles/descriptions; the owner alone executes git | Owner's explicit instruction â€” full control over the actual git history | Owner says otherwise |
| DL-013 | 2026-09-21 | DECIDED | Pin `Django>=5.2.13` explicitly in requirements | Fixes CVE-2026-33033 (multipart-parser DoS); found and verified in the second Deep Research pass (RESEARCH Â§4A/Â§7.5) | â€” |
| DL-014 | 2026-09-23 | DECIDED | `spec.md`/`run.py`/`fixtures.json`/`context.txt` are now the top of the source hierarchy, in hand, released a day early (Sep 23 vs. the planned Sep 24) | Owner supplied the actual released files | Any silent errata added to spec.md (it says a repeated Discord question gets a line added) |
| DL-015 | 2026-09-23 | DECIDED | Correct the scoring model: bonus points do NOT add to the 0â€“5 score. They only break ties and decide the $100 Best Judging Engine prize | spec.md, verbatim, quoted in RESEARCH Â§2 | â€” |
| DL-016 | 2026-09-23 | DECIDED | Treat a T1 regression as a P0 blocker at every stage of the build, even mid-T2/T3 work; enforce via CI (PLAN V10) | `run.py`'s own tier-gating logic zeroes T2 credit in the report if any T1 check fails, regardless of T2's own state (RESEARCH Â§2.2) | â€” |
| DL-017 | 2026-09-23 | DECIDED | Map the four required test personas to real fixture entities: `judge_a` â†’ `jdg_07` (the constant-score judge), `judge_b` â†’ `jdg_29` (co-reviewer of `prj_19` with `jdg_07`) | Makes the T2 own-scores/peer-scores checks exercise real, meaningful imported data instead of disconnected dummy accounts, at zero extra cost (RESEARCH Â§2B) | â€” |
| DL-018 | 2026-09-23 | DECIDED | Reframe Normalization Proof, Threat Model, and API First as core rubric work (Judging Integrity 25% / Adoptability 20%), not bonus investments; Pairwise Mode remains the one genuinely separate, lowest-priority bonus | Bonuses don't add points (DL-015), so the only reason to build the other three well is that they're literally what those two criteria ask for anyway | â€” |
| DL-019 | 2026-09-24 | DECIDED | No single signature differentiator picked; instead a priority order â€” graph health, then rank uncertainty, then judge disagreement heatmap â€” attempted one at a time only after core (T1/T2 + required T3) is solid | Owner's explicit call: build core rock-solid first, layer signature features by priority as time permits | Reality during the build looks different â€” order is a default, not a lock |
| DL-020 | 2026-09-24 | DECIDED | Dev is unavailable roughly 2â€“4 h Monday morning (personal scheduling only, no detail beyond that recorded); the build schedule treats G6 (T3 core, the most compressible gate) as the one to compress or shift around it, not G7/G8 (hardening, never suite-verified but not compressible either) | Owner confirmed the gap for scheduling purposes; owner does not want the reason recorded anywhere near the deliverable | It does not affect scope, targets, or quality â€” scheduling only |
| DL-021 | 2026-09-24 | DECIDED | Full domain model and schema designed â€” see SCHEMA.md (backlog item 1, done) | Step-by-step backlog work, no quality compromise, per owner's instruction | A structural change discovered once building starts |
| DL-022 | 2026-09-24 | DECIDED | Auth via a standalone `AuthToken` model + middleware, not Django's session framework (P-12) | Deterministic, printable seed credentials for the checker's "never logs in" model (RESEARCH Â§2.1), works identically for real users | â€” |
| DL-023 | 2026-09-24 | DECIDED | Full authorization matrix and policy-layer design â€” see AUTHZ.md (backlog item 2, done) | Step-by-step backlog work, no quality compromise, per owner's instruction | A structural change discovered once building starts |
| DL-024 | 2026-09-24 | DECIDED | Draft projects hidden from the public gallery (D-13); 403 is the blanket default over 404 (D-14) | Surfaced designing the authz matrix â€” no suite cost, avoids leaking unfinished ideas; 403 is simpler to reason about uniformly | â€” |
| DL-025 | 2026-09-24 | DECIDED | Full normalization policies, method, and planted-truth test specs â€” see NORMALIZATION.md (backlog item 3, done) | Step-by-step backlog work, no quality compromise, per owner's instruction | A structural change discovered once building starts |
| DL-026 | 2026-09-24 | DECIDED | Refined D-02: the later of two duplicate submissions becomes canonical by default, the earlier is auto-flagged/excluded (never deleted) and one-click reversible | Sharper than the original "flag, keep both, organizer resolves" â€” ordinary resubmission intent plus preventing double-counting one team's content | â€” |
| DL-027 | 2026-09-24 | DECIDED | Full assignment algorithm and graph-health design â€” see ASSIGNMENT.md (backlog item 4, done); adds `AssignmentRun` to SCHEMA.md | Step-by-step backlog work, no quality compromise; also delivers the priority-#1 signature feature (DL-019) as core work | A structural change discovered once building starts |
| DL-028 | 2026-09-24 | DECIDED | Full T3 design (voting, abuse model, threat model) â€” see VOTING.md (backlog item 5, done); refines SCHEMA.md's Vote model into `VoteAttempt`+`Vote` | Step-by-step backlog work, no quality compromise; single append-only log replaces the earlier separate rate-limit table, simpler | A structural change discovered once building starts |
| DL-029 | 2026-09-24 | DECIDED | Full API/OpenAPI shape â€” see API.md (backlog item 6, done); adds `User.password_hash` and a real register/login flow to SCHEMA.md, since the checker's seeded personas don't cover how a real user gets an `AuthToken` | The HTML views and JSON API call the same service functions â€” one code path, not two | â€” |
| DL-030 | 2026-09-24 | DECIDED | Full UI/UX screen inventory + the judge-ballot and organizer-dashboard wireframes â€” see UX.md (backlog item 7, done) | Two screens (ballot, dashboard) are where Judging Integrity actually becomes visible to a human, so they got full detail; the rest is a route map for now | Real layout once building starts may deviate |
| DL-031 | 2026-09-24 | DECIDED | Full Docker/CI design incl. a draft compose file, Dockerfile, entrypoint, and CI workflow with a real offline-verification job â€” see DOCKER.md (backlog item 8, done) | None of it is trusted until it runs on a real host (Claude can't run Docker) â€” this is the design to hand to an implementation agent, not final code | Whatever a real run reveals |
| DL-032 | 2026-09-24 | DECIDED | Required-doc outlines (README/ARCHITECTURE/DATA-MODEL/JUDGING) and the full 5-minute demo storyboard â€” see DOCS-PLAN.md (backlog item 9, done) | Turns doc-writing into transcription from files that already exist, not a Sunday-night scramble | â€” |
| DL-033 | 2026-09-24 | DECIDED | Generic (no tool names/quotas) prompt-template library for implementation work, split by cost-of-error into Tier A/Tier B â€” see PROMPTS.md (backlog item 10, done) | Owner's instruction: keep agent/quota specifics out of the docs | â€” |
| DL-034 | 2026-09-24 | DECIDED | Real hour-by-hour schedule with sleep placed at actual nights (not rigid gate boundaries) â€” see SCHEDULE.md (backlog item 11, done); supersedes PLAN's earlier vague sleep placeholder | More realistic than tying sleep to elastic gate boundaries; the Monday-morning gap detail stays here, not in PLAN, per the earlier instruction | Reality on the day |
| DL-035 | 2026-09-24 | DECIDED | Backlog CLOSED â€” all 11 items done. Next phase is a full stress test of the whole plan, explicitly out of scope for this session | Owner's own stated sequencing | Stress test findings may reopen specific decisions above |
| DL-036 | 2026-09-25 | DECIDED | Full stress test performed â€” see STRESS-TEST.md. 15 real findings (1 critical, 3 high, 7 medium, 5 low, IDs F1â€“F15), all fixed directly in SCHEMA/AUTHZ/NORMALIZATION/ASSIGNMENT/VOTING/API.md | Owner's explicit request: "clear any remaining doubts... so we don't guess and hallucinate anywhere" | Further review may surface more |
| DL-037 | 2026-09-25 | DECIDED | No local machine can run Docker at all (owner's news). Revised strategy: native local Postgres for dev parity, repo public from kickoff for unlimited Actions minutes, Actions as the primary verification loop, a manually-triggered SSH-into-runner debug job, Codespaces budgeted to ~5â€“7h across two sessions only. V9 redefined, not dropped â€” see DOCKER.md Â§6 | Real, load-bearing change to the environment plan | If a local machine somehow becomes available again |
| DL-038 | 2026-09-25 | DECIDED | Frontend/UX philosophy: clean, simple, professional, quietly sophisticated â€” usability over visual flourish; no heavy/flashy design. Color scheme deliberately deferred to frontend-coding time, when Claude presents live options | Owner's explicit direction; also serves as genuine differentiation per RESEARCH Â§7.0 (a calm, well-organized UI is rare in a rushed 72h field) | Owner's own call at frontend-coding time |
| DL-039 | 2026-09-25 | **RESOLVED 2026-09-26** | Native PostgreSQL install (no Docker) â€” resolved: Windows, pgAdmin 4, already installed. Owner independently confirmed understanding the split correctly: local Postgres for dev, Docker for packaging, tested exclusively via cloud (Actions/Codespaces), never locally | Owner confirmed | â€” |
| DL-040 | 2026-09-26 | DECIDED | Kickoff postponed twice: Fri 2026-09-25 â†’ Sun 2026-09-27, 23:30 IST / 18:00 UTC. Freeze accordingly Wed 2026-09-30, 23:30 IST. All downstream dates (judging window, write-up quest, winners) shifted +2 days â€” see RESEARCH Â§2 | Organizers' own announcement, relayed by owner | Another postponement, if it happens |
| DL-041 | 2026-09-26 | DECIDED | No more heavy work (deep scans, large fixes, new design docs) until building actually starts, unless absolutely necessary â€” small, already-known fixes are still fine | Owner: cannot risk hitting a usage limit right before kickoff | Owner lifts this once building starts |
| DL-042 | 2026-09-26 | DECIDED | Remaining "extras of planning and research" (the phase after the stress test) will happen during the build itself, as needed, rather than as a separate pre-kickoff phase | Owner's own call, given the time remaining | â€” |

---

## 2. Session log
Format: `date Â· what we did Â· what changed Â· what's next`

- **2026-09-21 (S1)** Read the site brief and FAQ; audited the Gemini dossier against primary sources (see RESEARCH Â§4); compared stacks; discussed Docker on Windows; locked Django; created PLAN / RESEARCH / LOGS. Next: confirm assumptions in PLAN Â§5.1, check Docker on Windows machines, start the planning backlog (PLAN Â§8) with the domain model.
- **2026-09-21 (S2)** Set the implementation-agent/planner split (kept out of docs per owner's instruction â€” quota/tool details live in the project's memory file, not here). Owner supplied a Discord `#announcements` digest; audited it against the site (RESEARCH Â§2.1): confirmed registration/submission-form/commit-cadence process facts, flagged and resolved two apparent conflicts (demo video vs. "presentation", optional deploy link vs. "staging URL isn't a submission"). Added the commit-cadence rule and a cross-agent sync protocol to PLAN Â§5.3a/5.3b. Next: proof-check the current plan, then start the planning backlog (PLAN Â§8) with the domain model.
- **2026-09-21 (S3)** Owner instruction: no agent (coding agent or Claude) ever executes a git write command â€” draft-only, owner runs git. Reworded PLAN Â§5.3a/Â§5.3b and the freeze checklist accordingly (DL-012). Sent a Gemini Deep Research prompt (pass 2) to fill gaps and pressure-test the plan.
- **2026-09-21 (S4)** Received and audited the second Deep Research report (RESEARCH Â§4A). Its math/security/Docker content (Parts Bâ€“D, F, G) checked out against primary sources and is folded into RESEARCH Â§7 (concrete normalization shrinkage formulas, Crowd-BT detail, auth-pattern comparison, HTMX+Ninja footguns, audit-log SQL, Docker hermetic-build technique, voting-integrity SQL, Ed25519 signed-record schema, judge-console UX). Its "competitive intelligence" (Part E â€” named past-event judges/winners/scores/quote) did not verify on direct search and is excluded/flagged as likely fabricated â€” never to be cited, including in the write-up. Corrected one wrong figure (Codespaces is 120 core-hours/month, not 60 â€” our original number was already right). Found and verified a real, current Django vulnerability, CVE-2026-33033, sharper than what the report vaguely gestured at; pinned `Django>=5.2.13` (DL-013).
- **2026-09-23 (S5)** Owner supplied the actual released spec.md, run.py, fixtures.json, and context.txt (a day earlier than the planned Sep 24). Full audit and integration: rewrote RESEARCH Â§2 with exact confirmed facts (repo layout, `.dogfood.toml` schema, all 7 acceptance checks verbatim, the tier-gating logic, the fact T3/T4 are structurally never suite-checked â€” new open question A14); added RESEARCH Â§2B from parsing the real `fixtures.json` ourselves (41 projects/40 teams/30 judges/8 tracks/126 scores; identified the exact duplicate `tm_07`/`prj_07`+`prj_41`, the exact constant-score judge `jdg_07` and its compounding overlap with thin-batch `prj_19`, the real review-count distribution, and confirmed the judgeâ€“project graph is a single connected component). **Corrected a significant error in our own prior model**: bonus points do not add to the score at all (DL-015) â€” reframed Normalization Proof/Threat Model/API First as core rubric work rather than bonus investments, demoted Pairwise Mode further (DL-018). Added the T1-regression-zeroes-T2-credit CI rule (DL-016, PLAN V10). Decided the test-persona-to-real-judge mapping (DL-017). Rewrote PLAN Â§1/Â§3/Â§4/Â§5.3/Â§7 accordingly. Next: begin the domain model/schema against the real fixture shape (PLAN Â§8, item 1).
- **2026-09-24 (S6)** Status check the day before kickoff: reviewed how much of PLAN Â§8's backlog remains (all 11 items still undone in detail â€” only meta-planning is complete) and raised the AI-convergence/uniqueness question the owner flagged (many competitors will also be AI-assisted, likely including Claude itself, so architectural convergence is expected and not itself a differentiator). Owner decided: no single signature feature â€” build core rock-solid first, then attempt graph health â†’ rank uncertainty â†’ disagreement heatmap in that order as time permits (DL-019). Owner flagged a personal ~2â€“4h Monday-morning availability gap for scheduling only, asked that no more specific reason be recorded anywhere near the docs/deliverable; folded into the build schedule around G6 (DL-020) with no effect on scope or targets. Next: the actual backlog work (domain model/schema first), plus the owner's planned "extras of planning and research + full stress test" phase.
- **2026-09-24 (S7)** Started backlog work step by step per owner's instruction (no quality compromise). Completed backlog item 1: full domain model and schema, written to a new file SCHEMA.md â€” entities for all four tiers, the service-layer boundary for each, a standalone `AuthToken` design (DL-022, P-12) instead of Django sessions, the fixtureâ†’schema import mapping keyed on `external_id` for idempotent re-seeding, and the refined D-11 persona table (`participant` now specifically tied to team `tm_07`, the duplicate-submission team, so browsing "my submissions" demos the duplicate-flagging feature live). Next: backlog item 2, the authorization matrix and policy-layer design.
- **2026-09-24 (S8)** Completed backlog item 2: full authorization matrix and policy-layer design, written to a new file AUTHZ.md â€” actor resolution middleware, a fixed 8-persona test set, the complete routeÃ—persona matrix across all four tiers (anchored on the real `peer_scores` trap using `jdg_07`/`jdg_29`), the generated-test enforcement mechanism with its control case, and two new decisions surfaced along the way (D-13 drafts hidden from gallery, D-14 403-over-404 default). Next: backlog item 3, normalization policies written first (D-01â€¦D-05, now against the real fixture IDs), then the method, then planted-truth test specs.
- **2026-09-24 (S9)** Completed backlog item 3: normalization policies/method/tests, written to a new file NORMALIZATION.md â€” the D-01â€¦D-05 policies stated as commitments before results (playbook discipline), the empirical-Bayes shrinkage formula with parameters chosen and defended (Îºâ‚€=Î½â‚€=4), the full computation pipeline, a determinism requirement, and 9 planted-truth test specs against the real fixture IDs (`jdg_07`, `prj_19`, the 8 thin batches, `tm_07`'s duplicate). Refined D-02 to a concrete keep-latest-canonical policy (DL-026), sharper than the original placeholder. Next: backlog item 4, the assignment algorithm and graph health.
- **2026-09-24 (S10)** Completed backlog item 4: assignment algorithm and graph health, written to a new file ASSIGNMENT.md â€” A-01â€¦A-07 policies (track eligibility and COI as hard constraints, active load balancing, honest under-coverage reporting, connectivity measured every run, multi-track judges as the only legitimate anchor mechanism, additive/idempotent re-runs, seeded randomness), the per-track greedy algorithm, the Fiedler-value graph-health computation (the priority-#1 signature feature from DL-019, built as core work), and 8 planted-truth tests including a cross-check against RESEARCH Â§2B's own hand-computed BFS result on the real fixture. Added `AssignmentRun` to SCHEMA.md (now Rev 2). Explicitly scoped: this algorithm is for new/live assignment only â€” the real fixture's 126 scores import as completed history, never reassigned. Next: backlog item 5, T3 design (voting modes, abuse model, threat model outline).
- **2026-09-24 (S11)** Completed backlog item 5: T3 design, written to a new file VOTING.md â€” V-01â€¦V-07 policies (uniform compound-unique-constraint vote dedup across all three modes, query-layer-gated results, per-voter-deterministic ballot order, an append-only `VoteAttempt` log that unifies rate-limiting/audit-trail/dashboard-indicator into one mechanism, flag-and-hide comments, the human-verifiability-in-under-a-minute design principle since T3 has no automated credit path, and never-votable flagged duplicates), a full "stopped vs. explicitly not stopped" threat model table (the honest-gap content spec.md itself rewards), and 7 planted-truth tests. Refined SCHEMA.md's T3 section (now Rev 3): `VoteRateLimit` replaced by the single `VoteAttempt` log, `Vote`'s partial indexes simplified to one compound unique constraint. Next: backlog item 6, API/OpenAPI shape and service-layer boundaries.
- **2026-09-25 (S13)** ~8h before kickoff. Owner reported two changes and requested a full stress test. **Stress test** (STRESS-TEST.md, new): re-read every design file against every other one and against spec.md, found 15 real issues, fixed all of them directly. Most serious (F1, critical): `services.judging.get_scores` was actually broken in two different ways in two different files â€” SCHEMA.md's version would have let a participant through with an empty 200 instead of the required 403 (failing the literal T2 "participant blocked" check), and AUTHZ.md's own attempted fix instead wrongly blocked organizers who aren't judges. Replaced with one corrected function in both files. Also found and fixed: SCHEMA.md had the duplicate-submission direction backwards relative to the later-refined D-02 policy (F2); no model anywhere actually stored judge-track eligibility despite three files assuming one existed, added `JudgeTrackEligibility` (F3); `AuthToken` stored raw tokens while the near-identical `ApiToken` correctly hashed them, fixed for consistency (F5); the normalization pipeline never connected the organizer's weighted rubric to the math, added the missing collapse step (F6); the audit-log hash chain had no concurrency handling, added an advisory lock (F7); `AssignmentRun` couldn't prove what its own test required, added a field (F8); the graph-health Fiedler computation was undefined for single-judge components, fixed (F9); a phantom "results public (config)" appeared in two files backing nothing, simplified (F10); a stray reference to a `THREAT-MODEL.md` file that was explicitly decided not to exist (F11); plus four lower-severity precision fixes (F12â€“F15). **Docker strategy pivot** (DL-037): the owner's alternative machines are now completely unavailable for Docker â€” full revision of the environment plan (DOCKER.md Â§6, PLAN Â§5.4): native local Postgres for dev parity, repo public from kickoff for unlimited Actions minutes, Actions as the primary verification loop, a manually-triggered SSH-into-runner debug job as a free interactive fallback, Codespaces budgeted to two short sessions (~5â€“7h total) instead of continuous use, V9 redefined rather than dropped. **UX philosophy** (DL-038): clean/simple/professional/quietly sophisticated, usability over visual flourish, no heavy or flashy design â€” recorded as a real design principle in UX.md Â§4; color scheme deliberately deferred to frontend-coding time. One genuinely open item remains (DL-039): whether native PostgreSQL can actually be installed on the dev machine, and its OS â€” everything else in this session was resolved or is a defensible design call, not a guess.
- **2026-09-26 (S14)** Owner: kickoff postponed twice (now Sun 2026-09-27, 23:30 IST â€” DL-040), no more heavy work until building starts unless truly necessary (DL-041), remaining "extras" folded into the build itself as needed (DL-042), and confirmed native PostgreSQL is already installed (Windows, pgAdmin 4 â€” DL-039 resolved), matching the exact local-dev/cloud-packaging split already designed. Made only small, targeted fixes per the owner's explicit instruction not to scan for or fix anything large right now: updated the small set of absolute kickoff/freeze-date references in RESEARCH Â§2 (kept the original dates struck through for the record), PLAN (Â§0, Â§4, Â§6), and flagged (not recomputed) SCHEDULE.md's clock table as off by +2 days, since it's built on elapsed hours that don't themselves change. Created CONTEXT-PACK.md â€” a single self-contained orientation document (separate from all prior docs) so this project can be picked up from scratch, in a fresh conversation or any other tool, without re-deriving anything already settled.

---

## 3. Blockers and critical findings register
The playbook's costliest lesson: flagging a critical issue is not fixing it. **Nothing is "final" while any row is OPEN.**
Format: `ID Â· raised Â· severity Â· finding Â· owner Â· status Â· closure evidence (command + output)`

| ID | Raised | Severity | Finding | Owner | Status | Closure evidence |
|---|---|---|---|---|---|---|
| â€” | â€” | â€” | (none yet) | â€” | â€” | â€” |

Closure needs explicit yes/no from the owner, plus evidence. Silence is not closure.

---

## 4. Findings journal (raw material for the write-up)
Log a line the moment something surprises us. Do not wait until Sunday.
Format: `date/time Â· hour-of-event Â· what happened Â· root cause (if known) Â· numbers Â· what we'd do differently`

Scorecard to fill as we go (the playbook's strongest write-up device):
| Bug / issue | Found by our own tests | Found by an external check (suite / oracle / CI / second machine) |
|---|---|---|
| (fill during the event) | | |

Candidate write-up threads (pick one at G6, now anchored on real data â€” RESEARCH Â§2B): the `jdg_07`/`prj_19` compounding edge case (a constant-score judge landing on an already-thin 2-review batch) Â· the `peer_scores` trap as a bug we deliberately built a test for Â· the `tm_07` duplicate-submission policy Â· statistical ties in the ranking.

Entries:
- **2026-09-27 16:38 IST Â· G0 (elapsed ~0h)** Â· Running `run.py` against local dev `runserver`: Django with `DEBUG=True` and an empty `urlpatterns` serves its default debug landing page (HTTP 200) for every route, causing `gallery is public` and `judge sees own scores` to coincidentally PASS on an unrouted skeleton instead of returning 404, while all other checks failed (overall: claimed nothing, verified nothing); in Docker/CI with `DEBUG=False`, all unrouted endpoints return 404.
- **2026-09-27 17:07 IST Â· G1 (elapsed ~1.5h)** Â· The local `rubric` PostgreSQL role lacks the `CREATEDB` privilege, so Django's test runner (`python manage.py test`) cannot create the ephemeral `test_rubric_dev` database. Worked around with a `settings_test.py` that overrides `DATABASES` to use SQLite in-memory for tests â€” acceptable since the auth/policy layer tests don't exercise any Postgres-specific features. The real CI (Docker on GitHub Actions) will use Postgres. If future tests need Postgres-specific features (triggers, `pgcrypto`), we'll need to either grant `CREATEDB` to the role or create the test database manually.
- **2026-09-27 17:16 IST Â· G1 Step 2 (elapsed ~1.8h)** Â· Registering the five P-11 routes in `urls.py` immediately caused `AuthzCoverageTest.test_every_route_has_declared_expectation` from Step 1 to fail until entries were added to `authz_expectations.yaml` â€” proving the declared-expectations mechanism catches new routes immediately. Also verified that registering both `judge_scores` and `peer_scores` against the same path (`api/judge/scores`) allows Django's `reverse()` to uniquely resolve both route names while incoming requests route to the shared handler.
- **2026-09-27 22:35 IST Â· G2 Step 1 (elapsed ~5h)** Â· (1) SCHEMA.md Â§2's fixture-mapping table had the duplicate direction backwards (`prj_41.is_duplicate_of = prj_07`), contradicting Â§1.1's own field definition and NORMALIZATION.md D-02. Corrected in-place to match: `prj_07.is_duplicate_of = prj_41` (earlier flags itself against later canonical). A test pins this exact direction by external_id. (2) Chose `JSONField` over Postgres's `ArrayField` for `Project.tech_tags`: `ArrayField` is Postgres-only and breaks the SQLite in-memory test backend (`settings_test.py`). `JSONField` works identically on both backends, stores the exact same list of strings, supports `__contains` filtering, and costs nothing since no fixture project carries tech_tags. If Postgres indexing is desired later, a `GinIndex` on `JSONField` works just as well as on `ArrayField`. (3) CSRF split: requests authenticated via `Authorization` header set `request._dont_enforce_csrf_checks = True`; cookie-authenticated requests keep full CSRF enforcement. Both halves tested. (4) AuditLogEntry model doesn't exist yet (G5 scope) â€” duplicate flagging logged via Python's `logging` module for now, noted as a gap to close at G5.
- **2026-09-27 23:00 IST Â· G2 Step 2 (elapsed ~5.5h)** Â· (1) Replaced G1 placeholder views with real server-rendered templates + HTMX views for `/projects` (gallery, showing all 41 submitted projects un-paginated), `/projects/{id}` (detail, public for submitted, draft restricted to owner/organizer via `services.submissions.get()`), `/projects/new` and `/projects/{id}/edit` (HTMX submission forms with honest "submissions are closed" state), and `/my/submissions` (participant's team submissions with duplicate-flag banner pointing earlier `prj_07` to canonical `prj_41`). (2) Added `process_exception(request, exception)` to `AuthMiddleware` so `PermissionDenied` raised inside views/service calls is converted to 401 (anonymous) or 403 (forbidden) rather than being treated by Django's exception handler as an unhandled 500 error in test client runners. (3) Added `services.submissions.create()` deadline check to reject submissions when `now() > event.submissions_close_at`. (4) Vendored HTMX 1.9.12 into `src/static/js/` and hand-crafted `src/static/css/rubric.css` design system with CSS custom properties (light/dark mode, minimal typography, clean cards, banners) per UX.md Â§4. (5) `run.py` acceptance checker passes all T1 checks ("gallery is public", "project from fixtures shown", "closed event refuses submissions"). Total tests: 86 passing.
- **2026-09-27 Â· G3 Step 1** Â· Added the five judging models and migrations, including the one-rubric-per-event constraint, default three-criterion rubric seeding, and idempotent import of all 126 fixture score records. Imported ballot `submitted_at` is explicitly documented as importer provenance in DATA-MODEL.md. Implemented the schema's `get_scores` policy verbatim, owned-assignment ballot submission, and organizer progress count. The score endpoint is now one URL pattern and view; `.dogfood.toml`'s peer probe targets `?judge=jdg_07` so `run.py` checks judge_b against judge_a. Added named isolation, participant-denial, import/idempotency, constant-score, organizer-scope, and submission tests. All 94 Django tests passed; migration check found no model drift; local persistent DB migration and seed succeeded; live `run.py .dogfood.toml` passed T1 and T2. No decision changes.
- **2026-09-27 23:55 IST Â· G3 Step 2 (elapsed ~7h)** Â· (1) Added judge-facing UI and services: `services.judging.get_my_assignments(actor)`, `services.judging.get_assignment_for_judge(actor, assignment_id)`, `services.judging.save_ballot_draft(actor, assignment_id, scores, comment)`, and `services.judging.get_next_pending_assignment(actor, current_assignment_id)`. (2) Implemented `/judge/queue` view and template showing a judge's own assigned projects partitioned into pending and completed with live progress tracking. (3) Implemented `/judge/ballots/{assignment_id}` view and template with the two-pane layout from UX.md Â§2: fixed left pane for submission material (title, summary, description, links, tech tags, track, queue progress) and independently scrolling right pane for rubric criteria scoring (1â€“5 scale buttons with dynamic behavioral anchor descriptions per NORMALIZATION.md), comment box, and submit-and-advance button. (4) Added partial autosave via `hx-trigger="change, keyup delay:1s"` targeting `#autosave-indicator` posting to `/judge/ballots/{assignment_id}/autosave`, preserving in-progress work without completing the ballot or assignment status. Added keyboard shortcuts (`j`/`k` navigation, `1`â€“`5` scoring, `Ctrl+Enter` submit). (5) Enforced strict zero-leak principle: zero code path displaying or fetching peer scores; any unassigned judge or peer judge attempting to open a ballot or post to autosave receives HTTP 403 Forbidden. (6) Implemented minimal `/organizer/progress` view showing raw evaluation progress numbers, accessible only to organizers. (7) Updated `tests/authz_expectations.yaml` for `judge_queue`, `judge_ballot`, `judge_ballot_autosave`, and `organizer_progress_page`. (8) Added 12 new comprehensive tests in `tests/test_g3_step2.py` exercising end-to-end queue viewing, ballot scoring, autosave persistence, submit-and-advance flow, peer isolation, and organizer progress. Total tests: 106 passing.
- **2026-09-29 | Phase 1 Step 1.1** | A production-mode Django test client returned 404 for both `/static/css/rubric.css` and `/static/js/htmx.min.js` (`DEBUG=False`); the container uses gunicorn with debug disabled, and neither `run.py` nor its status-only route checks inspect those asset requests or rendered page resources. Added pinned WhiteNoise, `STATIC_ROOT`, and Docker build-time `collectstatic`; the regression test now gets 200 with CSS/JavaScript content types and non-empty JS. This explains how the portal could pass route acceptance while a human saw an unstyled UI with broken HTMX.


---

## 5. Assumption tracker
Each A-row from RESEARCH Â§5 gets a status here after spec.md and the suite are read.

| ID | Status | Note |
|---|---|---|
| A1 | RESOLVED (spec.md) | Plain HTTP via `urllib`; no numbered check IDs â€” RESEARCH Â§2.2 |
| A2 | RESOLVED (spec.md) | Exact `.dogfood.toml` schema â€” RESEARCH Â§2.1 |
| A3 | RESOLVED (spec.md + our own parse) | Real fixture shape and data mined â€” RESEARCH Â§2B |
| A4 | Still an inference, strongest available reading | Runtime-only offline, per the "five things" wording â€” RESEARCH Â§5 |
| A5 | RESOLVED â€” our prior model was WRONG | Bonuses don't add points at all (DL-015) |
| A6 | RESOLVED â€” moot | Suite never touches normalization output; that's 100% human-judged (25%) |
| A7â€“A10 | Unresolved design choices, now known to be low-stakes | T3/T4 are never suite-verified at all (see A14) |
| A11 | RECONFIRMED (spec.md verbatim) | "Not before kickoff: project code... Friday 18:00 UTC" |
| A12 | RESOLVED (Discord digest) | Demo-video vs. presentation â€” one video satisfies both |
| A13 | RESOLVED (Discord digest) | Optional deploy link â€” lowest priority, never over a Must |
| A14 (new) | OPEN â€” genuinely unresolved | `run.py` structurally never checks T3/T4; unclear how much manual credit judges give beyond the machine-verified T1/T2 â€” RESEARCH Â§5 |

---

## 6. Doc changelog
- **Rev 1 (2026-09-21)** Created PLAN.md, RESEARCH.md, LOGS.md.
- **Rev 2 (2026-09-21)** RESEARCH: added Â§2.1 Discord digest + source-hierarchy caveat on the generic Discord template. PLAN: added Â§5.3a commit cadence, Â§5.3b cross-agent sync protocol, optional-deploy-link scope note, registration + cadence items in pre-kickoff checklist. LOGS: DL-008â€¦DL-011, S2, A12â€“A13.
- **Rev 3 (2026-09-21)** PLAN: reworded Â§5.3a/Â§5.3b and the freeze checklist so agents only draft commit titles/descriptions and never execute git write commands; read-only git is fine. LOGS: DL-012, S3.
- **Rev 4 (2026-09-21)** RESEARCH: added Â§4A (audit of Deep Research pass 2 â€” confirmed vs. excluded-as-unverified), expanded Â§7.1/7.2/7.3/7.4/7.5/7.6 with concrete formulas/SQL/patterns, added Â§7.8 (signed judge records) and Â§7.9 (judge console UX). PLAN: pinned `Django>=5.2.13` (P-01). LOGS: DL-013, S4.
- **Rev 5 (2026-09-23)** Full integration of the released spec.md/run.py/fixtures.json/context.txt. RESEARCH rewritten (Rev 4): exact confirmed mechanics (Â§2, Â§2.1, Â§2.2), real fixture analysis (Â§2B, new), most of Â§5's assumptions resolved, Â§7.0 (new) reframing bonuses vs. core rubric work. PLAN rewritten (Rev 5): corrected scoring model (bonuses don't add points), new V10 tier-gating CI rule, P-11/D-11 new decisions, retired R1/R5, added R15/R16, build order and checklists updated for the real files. LOGS: DL-014â€¦DL-018, S5, assumption tracker rewritten, findings-journal candidate threads updated.
- **Rev 6 (2026-09-24)** PLAN: replaced the differentiator "pick one" with a priority-ordered sequence (graph health â†’ rank uncertainty â†’ disagreement heatmap, attempted only once core is solid); added a personal ~2â€“4h Monday-morning availability gap (scheduling only, no further detail) to the build order (G6 is the compressible gate) and closed out the sleep/availability checklist item. LOGS: DL-019, DL-020, S6.
- **Rev 7 (2026-09-24)** New file SCHEMA.md: full domain model, service-layer boundaries, `AuthToken` auth design (P-12), fixtureâ†’schema import mapping, refined D-11 persona table, Django app layout. PLAN: backlog item 1 marked done, P-12/D-11 updated. LOGS: DL-021, DL-022, S7.
- **Rev 8 (2026-09-24)** New file AUTHZ.md: actor resolution, persona set, full routeÃ—persona matrix, generated-test mechanism + control case. PLAN: backlog item 2 marked done, D-13/D-14 added. LOGS: DL-023, DL-024, S8.
- **Rev 9 (2026-09-24)** New file NORMALIZATION.md: D-01â€¦D-05 as policies-before-results, the shrinkage method with defended parameters, the pipeline, determinism requirement, 9 planted-truth test specs. PLAN: backlog item 3 marked done, D-02 refined. LOGS: DL-025, DL-026, S9.
- **Rev 10 (2026-09-24)** New file ASSIGNMENT.md: A-01â€¦A-07 policies, the per-track load-balanced algorithm, `AssignmentRun`/graph-health (Fiedler value) design, 8 planted-truth tests. SCHEMA.md (Rev 2): added `AssignmentRun`. PLAN: backlog item 4 marked done. LOGS: DL-027, S10.
- **Rev 11 (2026-09-24)** New file VOTING.md: V-01â€¦V-07 policies, the `VoteAttempt`/`Vote` schema refinement, the full stopped/not-stopped threat model, 7 planted-truth tests. SCHEMA.md (Rev 3): T3 section refined. PLAN: backlog item 5 marked done. LOGS: DL-028, S11.
- **Rev 12 (2026-09-24)** New files: API.md, UX.md, DOCKER.md, DOCS-PLAN.md, PROMPTS.md, SCHEDULE.md â€” backlog items 6â€“11, closing PLAN Â§8 entirely. SCHEMA.md (Rev 4): added `password_hash`. PLAN (Rev 12): backlog section marked CLOSED, sleep note points to SCHEDULE.md. LOGS: DL-029â€¦DL-035, S12.
- **Rev 13 (2026-09-25)** New file STRESS-TEST.md: 15 findings (F1â€“F15) across every design file, all fixed. SCHEMA.md (Rev 5), AUTHZ.md (Rev 2), NORMALIZATION.md (Rev 2), ASSIGNMENT.md (Rev 2), VOTING.md (Rev 2), API.md (Rev 2) updated with the fixes. DOCKER.md (Rev 2) Â§6 fully rewritten for no-local-Docker. UX.md (Rev 2) Â§4 adds the owner's design philosophy. PLAN (Rev 13): Â§5.4, V9, R2, R12, pre-kickoff checklist all updated for the environment pivot. LOGS: DL-036â€¦DL-039, S13.
- **Rev 14 (2026-09-26)** Kickoff postponement (+2 days) reflected in RESEARCH Â§2 (struck-through originals kept), PLAN Â§0/Â§4/Â§6; SCHEDULE.md's clock table flagged as stale rather than recomputed (owner: no heavy work right now). DOCKER.md/LOGS: native Postgres question resolved (Windows, pgAdmin 4). New file CONTEXT-PACK.md: a standalone orientation document for a fresh start. LOGS: DL-039 (resolved), DL-040â€¦DL-042, S14.
- **2026-09-28 · G3 adversarial review fixes** · Changed judge self-score filtering to the authenticated user FK and documented the null-`external_id` collision in SCHEMA.md §1.2 and AUTHZ.md §3.2; clarified the unassigned-judge row. Added rubric-specific numeric bounds validation before any score upsert and ignored a late draft autosave once a ballot is complete. Added regressions for two null-id judges, out-of-range values, and trailing autosaves. DECISIONS.md records the judge-facing isolation finding; no CSV export changes.

## 2026-09-28 - G5 audit-chain core

- Added append-only audit models, the transactional Python hash-chain service, organizer list/verify services, portable export, a stdlib offline verifier, and the concurrency self-check command. The PostgreSQL migration installs immutable-row and truncate triggers only on PostgreSQL; SQLite tests exercise service-level verification and raw-SQL tampering.
- Full test suite: 148 tests passed. Local PostgreSQL `audit_selfcheck --threads 8 --entries 50` output: `audit_selfcheck: threads=8 entries_per_thread=50 added=400 total_entries=400 valid=True first_bad_seq=None gapless=True no_duplicates=True head_hash=9a0b695ef50968224c657fa6cee79508ba0ad9b10b325c6d86c1408507fdf0a`.
- PostgreSQL raw SQL UPDATE, DELETE, and TRUNCATE were each rejected by the immutability triggers; chain verification remained valid afterward.

## 2026-09-28 — G4 live assignment and graph health

- Added NumPy, AssignmentRun, its migration, and the additive per-track assignment service with seeded tie-breaking, eligibility and conflict checks, under-coverage reporting, graph-health reports, and genuine multi-track anchor injection.
- Added synthetic tests A1–A7 plus the explicit singleton-Fiedler F9 check, and fixture test A8. The fixture safety check snapshots all 126 completed assignments before and after a k=2 live assignment run; it adds no rows and preserves the snapshot exactly.

## 2026-09-28 — G4 normalization audit and completion

- Added the normalization models, migration, deterministic shrinkage service, organizer read, normalized-score payload, and offline proof-artifact export.
- Added fixture and synthetic tests for T1–T9, including the corrected T2 equal-offset and leave-one-out score checks; all 119 tests passed in the final full-suite run.
- The expanded T6 check found that active duplicate prj_07 still appeared in the public gallery. Filtered projects with is_duplicate_of set and added coverage that keeps prj_41 visible while excluding prj_07.
- A fresh local SQLite-backed server passed every live 
un.py T1/T2 check. Temporary database and server log files were removed afterward.
- T6's automatic audit-log record and organizer reversal remain unimplemented: the repository has no AuditLogEntry model or duplicate-restoration action; SCHEMA.md assigns the audit log to G5.

## 2026-09-28 — G4 Step 3: Organizer dashboard and real CSV export

- Built organizer dashboard screen (/organizer) per UX.md §3 displaying live progress (33/41 projects meeting target reviews), under-coverage breakdown across tracks, graph health status (1 connected component spanning 30/30 judges with Fiedler λ₂ ≈ 0.0875), and integrity flags (constant-score judge jdg_07, thin review count projects with prj_19 compound flag, and duplicate submission prj_07 superseded by prj_41 with one-click restore).
- Implemented /organizer/assignments: supports triggering additive runs via services.assignment.run(), displays latest connectivity report, and lists historical AssignmentRun records.
- Implemented /organizer/normalization: supports triggering normalization runs via services.normalization.run(), renders the Normalization Proof table with rank changes (Δ Rank), and supports downloading proof CSV.
- Closed G1/G3 placeholder gap on /api/export.csv: guarded endpoint to organizer-only access (anonymous returns 401, participant/judge return 403) and exports real per-project CSV rows containing project_id,raw_mean,normalized_mean,rank,review_count,flags with proper duplicate exclusion and flag tokens.
- Declared all three new organizer routes in tests/authz_expectations.yaml.
- Added 9 new tests in tests/test_g4_step3.py covering route access control, fixture fact parity, duplicate restoration, assignment/normalization triggers, and CSV export denial and data validation. Full test suite passing (139 tests).

## 2026-09-28 — G5 Step 2: Audit log wiring, sticky duplicate restore, and T6 completion

- Consolidated project logging: merged stray root `LOGS.md` entries verbatim in chronological order into `planning/LOGS.md` and deleted root `LOGS.md`. `planning/LOGS.md` is now the sole project log.
- Wired transactional `audit.record()` calls across all state-changing domain services:
  - `events.services`: `create_event` (`event.create`), `create_track` (`track.create`), `create_prize` (`prize.create`).
  - `teams.services`: `create_team` (`team.create`), `join_team` (`team.join`). Sensitive invite codes and credentials are strictly excluded from payloads.
  - `submissions.services`: `create` (`submission.create`), `update` (`submission.update`), `submit` (`submission.submit`).
  - `judging.services`: `submit_ballot` (`ballot.submit`). Autosave drafts intentionally bypass audit recording: logging in-progress keystroke saves would bloat the hash chain with unverified partial drafts; only final submitted ballots represent immutable state transitions.
  - `assignment.services`: `run` (`assignment.run`) recording target review count, seed, under-coverage, and anchor injection counts.
  - `normalization.services`: `run` (`normalization.run`) recording target review count, pooling parameters, component counts, and normalized score rows count.
  - `submissions.services.detect_and_flag_duplicates`: `duplicate.flag` attributed to system actor label `"duplicate-detection policy v1"`.
  - `submissions.services.restore_duplicate`: `duplicate.restore` recording organizer-authorized overrides.
  - `importer.management.commands.seed_fixtures`: records one summary entry for `fixture.import` inside the atomic import transaction, plus one entry per detected duplicate flag.
- Implemented sticky duplicate restore:
  - Added `duplicate_override = models.BooleanField(default=False)` on `Project` model with database migration (`0003_project_duplicate_override.py`).
  - `submissions.services.restore_duplicate` clears `is_duplicate_of`, sets `duplicate_override=True`, logs the audit entry, and preserves override state.
  - `detect_and_flag_duplicates` checks `duplicate_override` on candidate and earlier projects, ensuring that neither subsequent `submit()` calls nor `seed_fixtures` re-runs re-flag restored submissions.
- Completed T6 verification per `NORMALIZATION.md §3`:
  - Verified `prj_07` auto-flag audit entry exists with actor `"duplicate-detection policy v1"` and points to canonical `prj_41`.
  - Verified organizer restore action un-excludes `prj_07` from rankings and gallery, sets `duplicate_override=True`, and records an audit log entry with `action="duplicate.restore"`.
- Added organizer audit log routes and viewer:
  - `GET /api/v1/organizer/audit-log`: paginated audit entries, restricted to organizers.
  - `GET /api/v1/organizer/audit-log/verify`: cryptographic chain verification result and `?download=1` export download, restricted to organizers.
  - `GET /organizer/audit-log`: HTML viewer interface displaying chain verification status badge, current head sequence and hash, entry table, and Verify / Export buttons.
  - Registered all three routes in `tests/authz_expectations.yaml`.
- Added test suite in `tests/test_g5_step2.py` verifying:
  - Every service writes exactly one audit entry in its active transaction.
  - Transactional rollback: service failures after mutation roll back all model mutations and audit log rows cleanly.
  - Sticky restore idempotency against detector and fixture importer re-runs.
  - Route authorization denying anonymous (401), participants (403), judges (403), and permitting organizers (200).
- Full test suite passing: 158 tests passing across the repository.

## 2026-09-28 — G5 Step 3: Real user accounts and organizer-configurable weighted rubric

- Real user accounts domain service & presentation (`src/accounts/services.py`, `src/services/accounts.py`, `src/accounts/views.py`):
  - Added user registration (`/accounts/register`), login (`/login`, `/accounts/login`), and logout (`/logout`, `/accounts/logout`) with clean server-rendered HTMX forms.
  - Password management: uses Django's password hasher (`create_user`, `check_password`, `set_unusable_password`); fixture-seeded accounts remain password-less and authenticate exclusively via seed tokens.
  - Session cookie handling: sets session token in `session` cookie with `HttpOnly=True`, `SameSite='Lax'`, and `Secure=not settings.DEBUG` (matches bearer token mechanism for persona logins, unifying authentication logic).
  - CSRF protection: enforced on cookie-authenticated requests (`request._dont_enforce_csrf_checks` remains False for cookies; requests without CSRF tokens return 403 Forbidden).
  - Enumeration and timing attack protection: unknown emails and incorrect passwords return identical 401 status with generic error message (`"Invalid email or password."`) and dummy password check against `User().set_password(password)` for uniform execution time.
  - Server-side logout: invalidates `AuthToken` rows in the database upon logout and removes the session cookie.
  - Audit logging: records `user.register` and `user.login` events inside atomic transactions; raw passwords and tokens are never included in audit payloads.
- Organizer-configurable weighted rubric service & UI (`src/services/judging.py`, `src/judging/views_organizer.py`, `src/templates/organizer/rubric.html`):
  - Implemented `services.judging.configure_rubric(actor, criteria)` (organizer only).
  - Validations: enforces at least one criterion, non-empty unique criterion names, finite positive weights ($w_k > 0$), and positive max scores ($> 0$).
  - Post-scoring rubric edit policy: criteria with existing `BallotScore` rows cannot be deleted, preserving raw observation integrity. Weight modifications are permitted and audit-logged with exact before/after values (`rubric.configure`).
  - Added `/organizer/rubric` view and template: displays criterion table with status badges (`Scored • Locked` vs `Unscored`), disabled delete buttons for scored criteria, dynamic row addition for new criteria, and an explicit normalization notice warning that normalization must be re-run following weight adjustments.
  - Documented post-scoring rubric edit trade-off in `DECISIONS.md` (Decision 13).
- Route authorization declarations:
  - Registered `register`, `login`, `accounts_login`, `logout`, `accounts_logout`, and `organizer_rubric` in `src/rubric/urls.py` and declared authorization policies in `tests/authz_expectations.yaml`.
  - Updated `src/templates/base.html` navigation to expose Login/Register/Logout and the organizer Rubric link.
- Test coverage (`tests/test_g5_step3.py`):
  - Verified weight adjustments measurably and deterministically alter normalized score outputs on the real fixture dataset.
  - Verified deleting a scored criterion raises `ValueError` and prevents deletion.
  - Verified register, login, and logout lifecycle round-trip with audit logging.
  - Verified indistinguishable 401 responses for unknown email and incorrect password.
  - Verified cookie security flags (`HttpOnly`, `SameSite=Lax`, `Secure` in production).
  - Verified cookie-authenticated POSTs without CSRF token are rejected with 403 Forbidden.
  - Verified Definition of Done: brand-new registered user registers, logs in, and successfully accesses a session-protected endpoint (`/my/submissions`).
- Full test suite passes cleanly: 170 tests passing across the repository.

## 2026-09-28 — G5 Step 4: Tier-gating CI, Postgres test parity, and JUDGING.md draft

- CI workflow enhancements (`.github/workflows/ci.yml`):
  - Added V10 tier-gating check to the `clean-room` job: fails the build immediately if any `T1.*FAIL` line appears in `acceptance-report.txt` (`! grep -qE "^T1.*FAIL" acceptance-report.txt`).
  - Added overclaim guard: fails the build if `run.py` outputs `note: claimed but not verified:` (`! grep -q "note: claimed but not verified:" acceptance-report.txt`).
  - Added `test-postgres` job: runs the full Django test suite against a containerized `services: postgres` service on the GitHub runner with `DATABASE_URL` configured.
- Test database configuration & Postgres parity (`src/rubric/settings_test.py`):
  - Captures `_explicit_db_url` prior to loading settings, ensuring local test runs default to fast in-memory SQLite without requiring PostgreSQL credentials or `CREATEDB` privileges, while reading `DATABASE_URL` whenever explicitly provided (e.g. in CI or configured test environments).
  - PostgreSQL test parity analysis:
    - On PostgreSQL, `audit.0001_audit_chain` installs stored procedure triggers `audit_log_entry_no_row_mutation` and `audit_log_entry_no_truncate`.
    - In `tests/test_g5_audit.py`, `test_raw_sql_tamper_detects_each_entry_at_its_sequence` executes raw SQL `UPDATE audit_auditlogentry SET payload = ...`.
    - On SQLite, this mutation succeeds at the SQL level, allowing the test to verify that `verify_chain()` detects the resulting hash discrepancy.
    - On PostgreSQL, this mutation is rejected at the database level by the trigger (`psycopg.errors.RaiseException: audit log entries are immutable`). Per instructions, the test is preserved without weakening to document this defense-in-depth distinction.
- Authored initial draft of `JUDGING.md`:
  - System Overview: architectural principles, domain service primacy, defaults-closed authz, and planning divergences (corrected D-02 duplicate direction, JSONField portability, unified token model).
  - Assignment (A-01..A-07): track eligibility, conflict of interest, load balancing, under-coverage reporting, graph Laplacian algebraic connectivity (Fiedler value $\lambda_2 \approx 0.0875$ across 1 component of size 30), additive idempotence, and seeded reproducibility.
  - Normalization (D-01..D-05): weighted rubric collapse, empirical-Bayes shrinkage ($\kappa_0=\nu_0=4$, $\mu_0=3.6190$, $\sigma_0^2=0.6019$), duplicate handling (`prj_07` excluded, canonical `prj_41` ranked #8), constant judge handling (`jdg_07` constant z-score $0.5115$), thin review batches (8 projects with 2 reviews), compounding risk on `prj_19`, and honest limits (pragmatic estimator, rank sensitivity in crowded distributions).
  - Score Isolation: single-function enforcement (`services.judging.get_scores`), role checks, and the null-`external_id` finding (Decision 10).
  - Audit Log: cryptographic ledger mechanics, tamper-evidence capabilities, offline verifiability, and clear boundaries regarding database administrator threat models (Decision 12).
  - Outlined clearly marked TODO section for the T3 public voting threat model to be implemented in G6.
- Full local test suite passes cleanly: 170 tests passing across the repository.

## 2026-09-28 — G5 close-out: verification fixes, Postgres test parity, and cookie security

- Resolved red PostgreSQL CI job causes:
  - Immutability trigger test separation: split raw SQL tamper test into:
    1. A PostgreSQL-only test (`test_postgres_immutability_trigger_rejects_raw_mutations`, decorated with `unittest.skipUnless(connection.vendor == 'postgresql')`) asserting that the database trigger actively rejects raw `UPDATE`, `DELETE`, and `TRUNCATE` statements with `'audit log entries are immutable'`.
    2. A privileged attacker tamper-detection test (`test_raw_sql_tamper_detects_each_entry_at_its_sequence`): on PostgreSQL, executes `ALTER TABLE audit_auditlogentry DISABLE TRIGGER USER`, tampers with payloads via raw SQL, asserts `verify_chain` fails at the exact tampered sequence, and safely re-enables triggers in a `finally` block (`ENABLE TRIGGER USER`), skipping cleanly if database privileges are insufficient; on SQLite, tampers directly. Neither assertion was weakened.
  - TransactionTestCase teardown flush resolution: added `AuditTransactionTestCase(TransactionTestCase)` as a shared base class for transaction test cases touching audit tables. On PostgreSQL, its `_fixture_teardown()` disables `audit_log_entry_no_truncate` before running `flush` and re-enables it in a `finally` block, preventing teardown flush aborts while keeping the production database trigger intact.
- Open redirect validation (`src/accounts/views.py`):
  - Sanitized `next` parameter in `register_view` and `login_view` using `django.utils.http.url_has_allowed_host_and_scheme(url=raw_next, allowed_hosts={request.get_host()}, require_https=request.is_secure())`, falling back to `/projects` for untrusted destinations.
  - Added test coverage in `tests/test_g5_step3.py` verifying that malicious targets (`https://evil.com`, `//evil.com`, `javascript:alert(1)`) are rejected and redirected to `/projects`, while legitimate relative paths (`/my/submissions`) are honored for both login and registration.
- Session cookie Secure flag configuration (`src/rubric/settings.py`, `src/accounts/views.py`):
  - Replaced hard-coded `secure=not settings.DEBUG` with `RUBRIC_COOKIE_SECURE` environment setting (default `false`) so `docker compose` deployments running over plain HTTP on `http://localhost:8080` work out of the box without browsers rejecting session cookies.
  - Documented the adoptability-vs-security trade-off in `DECISIONS.md` (Decision 14).
  - Added tests in `tests/test_g5_step3.py` verifying `Secure=True` when `RUBRIC_COOKIE_SECURE=True` and `Secure=False` when `RUBRIC_COOKIE_SECURE=False`.
- Audit pagination hardening (`src/api/views.py`, `src/judging/views_organizer.py`):
  - Ensured `page` and `page_size` parameters `< 1` or non-numeric never trigger HTTP 500 errors.
  - API endpoint (`/api/v1/organizer/audit-log`) returns HTTP 400 `{"error":"invalid_parameters","detail":...}` on invalid values.
  - HTML viewer (`/organizer/audit-log`) clamps values to safe bounds (`page >= 1`, `1 <= page_size <= 200`, defaulting to `page=1, page_size=25`).
  - Added boundary tests in `tests/test_g5_audit.py` covering `0`, negative values (`-5`, `-10`), non-numeric strings (`abc`, `xyz`), and huge integers (`999999999`).
- Dogfood configuration (`.dogfood.toml`):
  - Added pitch sentence under `[tiers]`: `"Rubric delivers an auditable hackathon evaluation portal featuring cryptographic append-only audit logging, empirical-Bayes shrinkage normalization, and provable judge score isolation."`.
  - Maintained `claimed = []` unchanged per instructions.
- Full test suite results:
  - SQLite (default): 173 tests passed, 0 failures, 0 errors (1 skipped).
  - PostgreSQL (`postgresql://rubric:rubric_dev_only@localhost:5432/rubric_dev`): 173 tests passed, 0 failures, 0 errors (0 skipped).

## 2026-09-28 — G5.7: Event management, safe current-event model, landing page, and organizer bootstrap

- Single active current event model (`src/events/models.py`, `src/events/migrations/0003_event_is_current.py`, `src/events/services.py`, `src/services/events.py`):
  - Added `Event.is_current = models.BooleanField(default=False)`.
  - Added partial unique constraint `models.UniqueConstraint(fields=['is_current'], condition=models.Q(is_current=True), name='unique_current_event')`, guaranteeing at most one active event at the database level across SQLite and PostgreSQL.
  - Authored migration `0003_event_is_current` containing schema change and data migration marking the existing fixture event (`external_id='evt_01'`) current.
  - Implemented `events.services.current_event()` with safe fallback for synthetic unit tests.
  - Replaced all five `Event.objects.first()` sites (`src/accounts/middleware.py`, `src/services/judging.py` [x2], `src/submissions/views.py`, `src/accounts/services.py`) with `current_event()`.
  - Updated `src/importer/management/commands/seed_fixtures.py` to clear any existing active flag and explicitly mark the fixture event current.
  - Enforced that event creation (`create_event`) NEVER auto-switches `is_current`.
  - Documented architectural rationale and trade-offs in `DECISIONS.md` (Decision 15).
- Organizer event management routes & services (`src/events/views_organizer.py`, `src/events/services.py`, `src/rubric/urls.py`):
  - Added organizer-only routes:
    - `GET, POST /organizer/events`: list events, statuses, tracks/prizes counts, and event creation form.
    - `GET, POST /organizer/events/<id>/dates`: edit event name, slug, and submission/voting open/close dates.
    - `GET, POST /organizer/events/<id>/tracks`: list tracks and add tracks.
    - `POST /organizer/events/<id>/tracks/<track_id>`: edit track name and external ID.
    - `GET, POST /organizer/events/<id>/prizes`: list prizes and add prizes.
    - `POST /organizer/events/<id>/prizes/<prize_id>`: edit prize rank label and description.
    - `POST /organizer/events/<id>/make-current`: explicit event activation with confirmation warning explaining portal-wide re-scoping.
  - Added service mutators with before/after audit recording: `update_event`, `set_current_event`, `update_track`, `update_prize`.
  - Date validation: enforces `submissions_close_at > submissions_open_at` and `voting_closes_at > voting_opens_at`; rejects naive datetimes (`ValueError`).
- Public landing page (`src/events/views.py`, `src/templates/landing.html`, `src/rubric/urls.py`):
  - Route `GET /`: displays current event name, date schedule, submission status badge (`Open`, `Closed`, `Opens Soon`), voting status badge, list of tracks and prizes, and navigation links to the public project gallery (`/projects`), registration (`/accounts/register`), and login (`/login`).
  - Updated `src/templates/base.html` navigation to link brand to `/`, and added `Events` and `Audit Log` links for organizers.
- Organizer bootstrap management command (`src/accounts/management/commands/create_organizer.py`):
  - Implemented `manage.py create_organizer --email <email> --password <password> --name <name>` to bootstrap site administrators in clean deployments.
  - Creates user, sets password via Django hasher, grants `is_site_admin=True`, creates `EventMembership(role=ORGANIZER)` on the current event, and logs audit event `organizer.bootstrap`.
- Test suite & verification (`tests/test_g5_step7.py`):
  - Verified event isolation: creating a second event without switching leaves gallery, judge queue, dashboard, and CSV export for the fixture event identical; switching cleanly scopes all surfaces to the new event with zero cross-event leakage; switching back restores fixture scope.
  - Verified partial unique constraint: attempting to persist multiple `is_current=True` events raises `IntegrityError`.
  - Verified deadline enforcement: moving `submissions_close_at` into the past causes real submit path (`POST /projects/new` via HTML and JSON) to refuse with 403 Forbidden.
  - Verified date validation: rejects naive datetimes and backwards dates with `ValueError`.
  - Verified bootstrap command: user creation, password verification, permissions, audit entry, and credential login.
  - Verified authz expectations: all new routes registered in `tests/authz_expectations.yaml` and verified with all six personas (anon, participant, judge_a, judge_b, judge_unassigned, organizer).
- Acceptance checker:
  - Executed `run.py .dogfood.toml` against live local server: all checks PASS (gallery public, fixture projects shown, closed event refuses submissions, judge score isolation, CSV export).
- Full test suite results:
  - SQLite: 189 tests passed, 0 failures, 0 errors (1 skipped).
  - PostgreSQL: 189 tests passed, 0 failures, 0 errors (0 skipped).

## 2026-09-28 — G5.8: Team invite links (T1) and judge invitation (T2)

- Team invite links and join flow (`src/teams/services.py`, `src/services/teams.py`, `src/teams/views.py`, `src/templates/teams/`):
  - Added team creation view (`/teams/new`) rendering team creation form; on submission, creates team and redirects to `/teams/<id>?created=1` displaying the invite link (`/teams/join/<code>`).
  - Added team join by code view (`/teams/join/<code>`): anonymous visitors are redirected to `/login?next=/teams/join/<code>` with safe next validation; authenticated users call `services.teams.join_by_code(actor, code)`, enroll as `EventMembership(PARTICIPANT)` on the event if needed, record `team.join` in the audit log, and redirect to `/teams/<id>?joined=1`.
  - Duplicate membership rejection & idempotency: `services.teams.join_team` and `join_by_code` verify `TeamMembership.objects.filter(team=team, user=actor.user).exists()` and raise `ValueError("User is already a member of this team.")`. The HTTP join view handles repeat visits idempotently by catching the condition and redirecting existing members to `/teams/<id>?already_member=1` without duplicating DB records or audit entries.
  - Team detail view (`/teams/<id>`): displays team name, event, created timestamp, and member roster with roles (`Creator` / `Member`). Invite link banner and copy box are rendered conditionally: visible ONLY to team members and event organizers; non-member participants and anonymous visitors cannot see the invite code or join URL.
  - Identified schema gap (max team size): Inspected `Event` model; `Event` currently has no `max_team_size` field. Per instructions ("Enforce a max team size of 4 only if the Event model already has such a field; otherwise log the gap in LOGS, don't add one"), no field was added to `Event`, and this gap is logged here.
- Offline judge invitation system (`src/judging/models.py`, `src/services/judging.py`, `src/judging/views_organizer.py`, `src/templates/organizer/judges.html`, `src/templates/judging/invite_error.html`):
  - Added `JudgeInvite` model (`judging.0005_judge_invite` migration): fields `event`, `email`, `token_hash`, `tracks` (ManyToMany to `Track`), `created_at`, `expires_at` (14 days), `accepted_at`, `created_by`.
  - Token generation & cryptographic verification: tokens are generated as 32-byte URL-safe strings (`secrets.token_urlsafe(32)`), stored hashed via SHA-256 (`token_hash`), never stored in plaintext, and verified using constant-time comparison (`hmac.compare_digest`).
  - Organizer judge management (`/organizer/judges`): lists pending and accepted judge invitations for the current event with assigned tracks; provides form to invite a judge by email with track selection; displays the single-use invite link (`/invite/judge/<token>`) ONCE upon creation with a copy-to-clipboard button.
  - Judge acceptance flow (`/invite/judge/<token>`): requires a logged-in user; redirects anonymous users to login with safe `next`; validates token validity, 14-day expiration, and single-use status; enforces strict email matching (`actor.user.email.lower() == invite.email.lower()`, rejecting mismatches with HTTP 403 Forbidden).
  - Role & track eligibility provisioning: upon valid acceptance, creates or updates `EventMembership(event=event, user=user, role=EventRole.JUDGE)`, creates `JudgeTrackEligibility` records for each track attached to the invite, marks `accepted_at=timezone.now()`, and redirects to `/judge/queue?accepted=1`.
  - Audit logging: records `judge.invite_created` and `judge.invite_accepted` in active atomic transactions; raw tokens and token hashes are never exposed in audit payloads.
- Route authorization declarations:
  - Registered `team_create`, `team_join`, `team_detail`, `organizer_judges`, `judge_invite_accept` in `src/rubric/urls.py`.
  - Declared all 5 routes in `tests/authz_expectations.yaml`.
  - Updated `src/templates/base.html` navigation to link `Create Team` (authenticated participants) and `Judges` (organizers).
  - `tests/test_auth_policy.py`: 30/30 tests pass.
- Test coverage (`tests/test_g5_step8.py`):
  - 16 comprehensive tests verifying:
    - Token generation, hashing, 14-day expiry, and token-free audit logging.
    - Rejection of expired tokens (HTTP 400 & `ValueError`).
    - Rejection of already-accepted tokens (HTTP 400 & `ValueError`).
    - Rejection of wrong-email users (HTTP 403 & `PermissionDenied`).
    - Rejection of tampered tokens (HTTP 404).
    - Rejection of cross-event tokens (HTTP 404).
    - Self-promotion prevention: non-invited user cannot self-promote.
    - Role-based access control: anonymous (401), participants (403), and judges (403) blocked from `/organizer/judges`; organizers allowed (200).
    - Full end-to-end judge onboarding path: organizer invite -> link shown once -> anon redirected to login/register -> registration with matching email -> acceptance -> `EventMembership(JUDGE)` and `JudgeTrackEligibility` created -> access to `/judge/queue`.
    - Team creation, members/organizers-only link visibility, anonymous redirect with safe next, authenticated join, and idempotency / duplicate rejection.
- Live acceptance report:
  - `run.py .dogfood.toml` executed live against local server: all checks PASS (T1 and T2 verified).
- Full test suite results:
- SQLite (default): 205 tests passed, 0 failures, 0 errors (1 skipped).
- PostgreSQL (`postgresql://rubric:rubric_dev_only@localhost:5432/rubric_dev`): 205 tests passed, 0 failures, 0 errors (0 skipped).

## 2026-09-29 — Phase 2.1: T3 voting backend

- Added per-event OPEN/AUTH voting settings, random per-event fingerprint/order seed (including a data migration), nullable vote budget, vote withdrawal, append-only attempt outcomes, unique vote constraint, comments with flag-and-hide moderation, service-layer result gating, and the requested ballot/cast/withdraw/results/comment/organizer routes.
- Public OPEN fingerprints are HMACs of the event seed, `REMOTE_ADDR`, and user-agent. The service receives only those request values; it does not trust `X-Forwarded-For`. Raw IP and user-agent values are not written to vote, attempt, comment, or audit rows. This is not strong identity proof: network/client changes can evade duplicate limits, while shared network/client details can collide.
- Organizer event settings now audit before/after access mode and vote budget. The fixture event's voting dates and `submissions_close_at` were not changed.
- Bare anonymous `curl -X POST` requests without a CSRF cookie/token receive HTTP 403 from Django CSRF middleware before the voting service runs. This is expected for browser-style anonymous POSTs; a browser must first fetch a page and submit its CSRF token. A bearer-authenticated request follows the existing CSRF bypass path.
- Focused SQLite voting suite: 18 tests passed. Initial concurrency assertions showed the shared 5-attempt/minute limit correctly classifying some race losers as rate-limited before duplicate/budget checks; tests now assert the exact number of surviving votes and permit the applicable rejection outcomes.
- T3 dashboard response is implemented as the organizer summary API; the polished dashboard surface remains Phase 2.2.
- Full suite verification: SQLite — `Ran 224 tests in 40.157s`, `OK (skipped=1)`; PostgreSQL — `Ran 224 tests in 165.086s`, `OK`. The Postgres concurrency tests use `AuditTransactionTestCase` so the production audit TRUNCATE trigger is disabled only during test flush and re-enabled immediately afterward.
- The first live `run.py` attempt returned 500s because the configured local `rubric_dev` Postgres schema had not yet applied `events.0004_voting_settings` / `voting.0001_initial`; applied those migrations, then reran successfully: T1 gallery public, fixture project shown, closed submissions, T2 own scores, peer-score denial, participant denial, and CSV export all PASS. Portal was `http://localhost:8080`; `claimed = []` stayed unchanged. No fixture voting dates were seeded or altered.

## 2026-09-29 — Phase 1.2: offline-check network lookup

- Finding: created-not-started containers have no NetworkID.

## 2026-09-29 — Phase 2.2: T3 voting UI and review follow-ups

- Comment service now rejects draft and duplicate projects; voting access mode becomes immutable after any vote or attempt, with the event row locked to serialize setting changes against voting actions.
- Organizer open-now and close-now actions update only the relevant voting timestamp and append before/after audit entries. `submissions_close_at` remains unchanged.
- Added server-rendered ballot cards with HTMX Vote/Withdraw, budget display, and inline duplicate/rate-limit/budget outcomes; public results stay hidden until close; project comments honor voting mode and show organizer moderation controls; organizer dashboard polls integrity outcomes and blocked project counts every 10 seconds. Settings include voting mode, budget, window, and immediate open/close actions.
- Anonymous browser voting uses the existing CSRF split: ballot response supplies the HTMX `X-CSRFToken` header, while a bare anonymous POST without a token receives 403 before the service. Existing login comparison test now normalizes the additional masked token in the HTMX header too.
## 2026-09-29 — Phase 2, Step 2.3: Adversarial review of T3 voting and authorization

- Conducted exhaustive adversarial audit across all 10 target threat vectors; verified findings via targeted probe script on SQLite and PostgreSQL.
- Findings summary:
  1. Results leakage: Public results are strictly hidden from anonymous/participant/judge personas prior to voting close (HTTP 200 with generic hidden template, 401/403 on JSON). Organizers can view live tallies before close via `/results/<slug>` and `/api/v1/organizer/voting/summary` (`active_votes`), as well as reconstruct tallies from the immutable audit log export (`voting.vote_cast` / `voting.vote_withdrawn`). (P2)
  2. Vote budget & race conditions: PostgreSQL serializes casts and withdrawals by locking the single `Event` row (`SELECT FOR UPDATE`), preventing budget bypass at the expense of an event-wide concurrency bottleneck. On SQLite, in-memory `_sqlite_locks` mutex is ineffective across multi-process workers, permitting budget race condition bypass under multi-process deployment. (P1)
  3. OPEN-mode fingerprint spoofing: Fingerprint is HMAC of `REMOTE_ADDR` and `HTTP_USER_AGENT`. An attacker from a single IP can cast unlimited votes by rotating the `User-Agent` header (bypassing per-fingerprint rate and budget limits). Conversely, users sharing NAT IP and browser headers collide on the same fingerprint, blocking votes or enabling mutual vote withdrawal. (P1)
  4. Ineligible project voting: Cast and comment services strictly enforce `status=SUBMITTED`, `is_duplicate_of__isnull=True`, and `event=event`. Attempts to vote/comment on `prj_07` (duplicate), draft projects, or cross-event submissions raise `PermissionDenied`. (P2 - secure)
  5. Stored XSS in submission links: Project `repo_url`, `demo_video_url`, and `live_url` are stored without URL scheme validation and rendered in `href="{{ ... }}"` in `project_detail.html` and `ballot.html`. Attackers can inject `javascript:...` URIs, leading to Stored XSS when judges or organizers click project links. Comments and titles are properly escaped. (P0/P1)
  6. Route declaration coverage: Introspected URL resolver; all 48 route patterns are registered in `tests/authz_expectations.yaml`. Zero undeclared routes exist. (P2 - secure)
  7. IDOR / peer score isolation: Single-function score isolation (`get_scores`), assignment judge scoping (`JudgeAssignment.objects.get(judge=actor.user)`), and team membership checks prevent peer score or ballot hijacking. (P2 - secure)
  8. Event-management cross-tenant check: `update_event`, `create_track`, `update_track`, `create_prize`, `update_prize`, and `set_current_event` check `actor.is_organizer` (scoped to `current_event()`) rather than checking membership in the target event being modified. An organizer of the current event can modify any other event, while organizers of non-current events cannot edit their own event. (P1)
  9. Secret ballot loss in AUTH mode: In AUTH mode, `voter_fingerprint` is stored as plaintext `str(user.pk)` in `Vote` and `VoteAttempt`. Furthermore, `audit.record` records `actor_user_id = actor.user.pk` on `voting.vote_cast` alongside `payload.project_id`, irrevocably binding voter identity to vote choice in the permanent cryptographic ledger. (P1)
  10. Setting mutations after votes exist: `voting_access` mode changes after votes exist are rejected with `ValueError`. However, `voting_closes_at` and `votes_per_voter` can be modified after votes exist, potentially granting early voters asymmetrical extra votes. Additionally, `open_voting_now` does not clear past `voting_closes_at`, leaving voting closed. (P2)

## 2026-09-29 — Phase 3, Step 3.1: Make JUDGING.md true and surface normalization evidence

- Fixed all incorrect statistical parameters in `JUDGING.md`:
  - Recomputed event parameters from a real run on fixture `evt_01` (121 active ballots across 29 judges, excluding duplicate `prj_07`'s 5 ballots):
    - Pooled mean $\mu_0 = 3.5758$ (corrected from 3.6190).
    - Pooled variance $\sigma_0^2 = 0.3930$ (corrected from 0.6019).
    - Pooled standard deviation $\sigma_0 \approx 0.6269$ (corrected from 0.7759).
    - Constant judge `jdg_07` shrinkage variance $\tilde{s}_j^2 = \frac{0 + 4(0.3930)}{3 + 4} = 0.2246$ (corrected from 0.3440).
    - Constant judge `jdg_07` z-score contribution confirmed at $0.5115$.
  - Corrected multi-track judge citations: `jdg_02`, `jdg_03`, `jdg_11`, and `jdg_29` (previously cited `jdg_01`, `jdg_04`, and `jdg_07` were verified to each have only 1 track in fixtures).
  - Audited all other numbers in `JUDGING.md`: verified project ranks and scores (`prj_41` raw 3.8333 / norm 3.7912 / rank 8; `prj_07` duplicate / rank None; `prj_09` norm 3.6128 / rank 16; `prj_17` norm 3.5741 / rank 19; `prj_19` norm 3.6022 / rank 18; `prj_13` norm 3.3116 / rank 31; `prj_26` norm 3.2631 / rank 32; thin projects list of 8 projects; 40 of 41 projects ranked).
- Normalization evidence and synthetic validation:
  - Added `services.normalization.synthetic_validation(seed=2026)`: fixed-seed planted-truth setup (20 projects, 10 biased judges $\in [-1.5, +1.5]$, Gaussian noise, 3 reviews/project) returning `SyntheticValidationResult` supporting attribute, dict, and tuple unpacking access. Produces raw-mean ranking Spearman correlation 0.7308 vs normalized ranking Spearman correlation 0.8917 (gain of +0.1609).
  - Added `services.normalization.compute_judge_calibration_evidence(run_record)`: computes inter-judge spread across judges before and after empirical-Bayes shrinkage on real fixture data: raw judge means stdev 0.3235 (sample stdev 0.3292) vs mean normalized ballot values stdev 0.2023 (sample stdev 0.2059), demonstrating a 0.1212 (37.5%) reduction in cross-judge rating scale dispersion toward event consensus.
  - Surfaced both evidence sections on `/organizer/normalization` (real fixture evidence first, synthetic clearly labeled SYNTHETIC) and quoted both in `JUDGING.md` with method notes.
- Ballot anchors graceful degradation:
  - Updated `src/judging/views.py` (`judge_ballot_view`) to fall back to an empty dictionary and empty string for unmapped criterion names, ensuring organizer-added or renamed criteria degrade gracefully with no anchor text and no crash while standard criteria retain their anchor text.
- Consistency and regression test suite:
  - Added `tests/test_docs_consistency.py` testing:
    - Recomputation of fixture normalization parameters and assertion that formatted strings appear in `JUDGING.md`.
    - Verification that every numbered `## N.` heading in `DECISIONS.md` has a corresponding Table of Contents entry.
    - Graceful degradation of ballot anchors for custom or renamed criteria.
    - Reproducibility and interface compliance of `services.normalization.synthetic_validation`.
    - Computation and UI rendering of real and synthetic evidence on `/organizer/normalization`.
- Full suite verification:
  - SQLite: Ran 241 tests in 42.949s, OK (skipped=1).
  - PostgreSQL: Ran 241 tests in 168.664s, OK.
  - Acceptance runner (`python run.py .dogfood.toml` against live server): all checks PASS (T1 gallery public, fixture projects shown, closed submissions refused; T2 judge sees own scores, peer scores denied, participant blocked, CSV export works). Verified T1 and T2.

## 2026-09-29 — Phase 3.2A: adversarial review fixes

- Findings journal: submission services accepted raw external URLs, allowing unsafe schemes to reach rendered links when writes bypassed forms. Added shared service validation for stripped HTTP/HTTPS URLs and a defensive render filter at every project-link output. Direct ORM corruption now produces no external link.
- Findings journal: the judge ballot referenced `live_site_url`, which is not a model field. It now renders the `live_url` value.
- Event-scoped organizer mutations now authorize against the target event membership. Added named tests for event A/B organizer isolation, event switching, judge access isolation, event-bound judge invitations, and team invite codes.
- Verification: focused and adjacent coverage `Ran 97 tests in 16.427s`, `OK`; full SQLite `Ran 252 tests in 47.691s`, `OK (skipped=1)`; full PostgreSQL `Ran 252 tests in 122.385s`, `OK`; docs consistency and auth policy `Ran 35 tests in 1.477s`, `OK`.
- Django checks reported no issues, `makemigrations --check --dry-run` reported no changes, and `git diff --check` was clean.
- Live `run.py .dogfood.toml` against local `runserver 8080` and PostgreSQL: T1 gallery, fixture project, and closed-submission checks PASS; T2 own judge scores, peer-score denial, participant denial, and CSV export PASS. `claimed` remains empty.





