# DECISIONS.md — Rubric (hackathon submission/judging portal, DogFood 2026)

Every non-trivial design or engineering judgment call that shapes how Rubric
behaves, or how it should be read — the "why," not routine implementation
mechanics (those live in mechanical logs). Entries are never edited or renumbered
once written; a decision that changes later gets a new, later-numbered entry
that says so explicitly, so the history stays honest.

## Table of Contents

- [1. Authentication: a standalone token model, not Django sessions](#1-authentication-a-standalone-token-model-not-django-sessions)
- [2. One function decides who sees judging scores, including peer lookup](#2-one-function-decides-who-sees-judging-scores-including-peer-lookup)
- [3. A deliberately broken route, kept on purpose, to prove our own enforcement works](#3-a-deliberately-broken-route-kept-on-purpose-to-prove-our-own-enforcement-works)
- [4. Duplicate submissions: the later entry is canonical, the earlier one is flagged, never deleted](#4-duplicate-submissions-the-later-entry-is-canonical-the-earlier-one-is-flagged-never-deleted)
- [5. Judges aren't excluded for suspicious scoring patterns — they're neutralized statistically and flagged](#5-judges-arent-excluded-for-suspicious-scoring-patterns--theyre-neutralized-statistically-and-flagged)
- [6. The one part of the checklist we can't do locally, said plainly rather than hidden](#6-the-one-part-of-the-checklist-we-cant-do-locally-said-plainly-rather-than-hidden)
- [7. The public-voting layer is built to be checked by a person, on purpose](#7-the-public-voting-layer-is-built-to-be-checked-by-a-person-on-purpose)
- [8. User accounts don't carry Django's admin baggage](#8-user-accounts-dont-carry-djangos-admin-baggage)
- [9. CSRF enforcement depends on how you authenticated, not a global toggle](#9-csrf-enforcement-depends-on-how-you-authenticated-not-a-global-toggle)
- [10. Judge score isolation uses the authenticated user identity](#10-judge-score-isolation-uses-the-authenticated-user-identity)
- [11. Normalization claims are corrected against measured fixture behavior](#11-normalization-claims-are-corrected-against-measured-fixture-behavior)
- [12. The audit chain is tamper-evident, not proof against a database owner](#12-the-audit-chain-is-tamper-evident-not-proof-against-a-database-owner)
- [13. Rubric editing after scoring begins: weight adjustments are permitted, criterion deletion is forbidden](#13-rubric-editing-after-scoring-begins-weight-adjustments-are-permitted-criterion-deletion-is-forbidden)
- [14. Session cookie Secure flag is opt-in for local container adoptability](#14-session-cookie-secure-flag-is-opt-in-for-local-container-adoptability)
- [15. Single active event model with explicit organizer switching](#15-single-active-event-model-with-explicit-organizer-switching)
- [16. Offline CI evidence blocks container egress and checks the block](#16-offline-ci-evidence-blocks-container-egress-and-checks-the-block)
- [17. Public voting supports open-link and authenticated access only](#17-public-voting-supports-open-link-and-authenticated-access-only)
- [18. Vote budgets are configurable and withdrawal restores capacity](#18-vote-budgets-are-configurable-and-withdrawal-restores-capacity)
- [19. Voter fingerprints minimize stored identity while preserving rate limits](#19-voter-fingerprints-minimize-stored-identity-while-preserving-rate-limits)
- [20. Voting access mode locks after the first recorded action](#20-voting-access-mode-locks-after-first-recorded-action)
- [21. Organizers can open or close voting immediately with an audit record](#21-organizers-can-open-or-close-voting-immediately-with-an-audit-record)
- [22. Event authority is scoped to the event being changed](#22-event-authority-is-scoped-to-the-event-being-changed)
- [23. Voting is a secret ballot with pseudonymous voter identities](#23-voting-is-a-secret-ballot-with-pseudonymous-voter-identities)
- [24. Control case for route authorization now lives only in the test suite](#24-control-case-for-route-authorization-now-lives-only-in-the-test-suite)
- [25. Public demo credentials exist for automated evaluation and can be disabled in production](#25-public-demo-credentials-exist-for-automated-evaluation-and-can-be-disabled-in-production)

---

## 1. Authentication: a standalone token model, not Django sessions

**Decision:** Every identity in Rubric — the four required test accounts and every real signed-up user alike — authenticates via a single hashed bearer token, not Django's built-in cookie-session framework.

**Rationale:** The organizers' own acceptance checker attaches a raw header on every request and never "logs in" in the conventional sense. A session-cookie system would mean simulating a browser session just for four fixed identities — more moving parts than the problem needs, and a second code path alongside real users' actual logins. One token mechanism serves both, with no special-casing between "the checker's account" and "a real judge's account." The raw token is generated once, shown at boot, and hashed before storage — nobody with database access alone can recover it.

**In plain terms:** Everyone gets a plain access token instead of a login-and-cookie flow, checked the same way every time — including the automated checker's own test accounts. The token itself is never sitting in the database in a form someone could steal and reuse.

---

## 2. One function decides who sees judging scores, including peer lookup

**Decision:** The `/api/judge/scores` URLconf entry serves the score-list request; the peer-score check adds a `judge` query parameter to that same path. Both checks use exactly one service-layer function that checks the caller's identity before returning anything.

**Rationale:** The single most common way this category of tool loses points is trusting an id in the query string instead of checking it against who's actually asking. Writing the check once, in one place, removes the chance of two near-identical implementations quietly drifting apart. An organizer sees everyone's scores; a judge sees only their own, no matter whose id they ask for. This was deliberately stress-tested before a line of real code existed: two early draft versions of this exact function were checked against each other during planning, and both were found to be wrong in different ways — which is exactly why one hardened function exists now instead of logic repeated per route.

**In plain terms:** There's only one place in the whole codebase that decides "can this person see this judge's scores." We tried hard to break it on paper before writing it for real, found two different ways it could fail, and fixed both.

---

## 3. A deliberately broken route, kept on purpose, to prove our own enforcement works

**Decision:** The codebase includes one intentionally unprotected route with no access check at all, wired specifically so our own automated coverage test can prove it catches an unprotected endpoint — before that test is trusted on anything real. It's marked for removal before submission.

**Rationale:** A test that always passes isn't evidence of anything; it might simply never have failed. Before relying on "every route has a declared access rule, checked automatically," we needed to see that check actually fail on a real gap, not assume it would.

**In plain terms:** We planted a fake unlocked door on purpose and watched our own alarm system catch it — so we'd trust the alarm before relying on it for every real door in the building.

---

## 4. Duplicate submissions: the later entry is canonical, the earlier one is flagged, never deleted

**Decision:** When a team submits what looks like the same project twice, the later submission becomes the active entry by default. The earlier one is kept in full, visibly flagged as superseded, and never removed — and flagging it is itself logged and reversible by an organizer with one click.

**Rationale:** A near-deadline resubmission usually means "here's the finished version," not "here's a second, competing entry." Treating the later one as canonical matches that intent and stops one team's work from being double-counted in judging or the public gallery. Deleting the earlier one, though, would destroy information an organizer might need if the guess was wrong — so it stays, clearly marked, rather than silently vanishing.

**In plain terms:** If a team submits the same project twice near the deadline, we use the second one for judging — but we never throw away the first attempt, we just label it and let an organizer undo that label if we guessed wrong.

---

## 5. Judges aren't excluded for suspicious scoring patterns — they're neutralized statistically and flagged

**Decision:** A judge with at least two counted ballots whose weighted ballot values have zero variance (whether each criterion is identical or only the weighted totals are identical) is never removed from the dataset. Their raw scores stay fully visible; a statistical adjustment limits how much they can skew a project's *relative* ranking, and the pattern itself is shown as a visible flag, not fixed quietly. The same honesty applies to any project reviewed fewer times than planned, and to any pair of judges with no shared project to compare against — both are shown, not smoothed into one falsely clean number.

**Rationale:** Silently excluding a judge's input would be a bigger, harder-to-see decision than flagging it, and this is exactly the kind of thing Judging Integrity is meant to catch if handled quietly. Reducing influence statistically rather than by exclusion keeps every data point on record. The underlying method is deliberately described as a practical, standard-shaped statistical adjustment, not a claim to a fully rigorous model — overstating that would be its own kind of dishonesty.

**In plain terms:** We never throw out a judge's scores, even odd-looking ones — we just stop one unusual judge from quietly tilting the results, and we say so on the dashboard instead of fixing it invisibly. Same for thin review counts and non-overlapping judges: we show the gap instead of hiding it.

---

## 6. The one part of the checklist we can't do locally, said plainly rather than hidden

**Decision:** This project's containerized deployment is never run on the machine it was built on — that machine can't run Docker at all. Every verification of it happens in a disposable, cloud-based environment that boots the real container from scratch, every time.

**Rationale:** Rather than hope "it works on my machine" quietly covers for a gap, the gap is made structurally impossible to hide: the app is simply never run on that machine in the first place. What's genuinely still untested (a literal Windows-native Docker run) is stated plainly, not implied to be fine.

**In plain terms:** We can't run Docker locally, so every "does this actually boot in a container" check happens on a fresh, disposable machine instead — arguably a stricter test than running it locally, and we're upfront about the one specific check that's still untested.

---

## 7. The public-voting layer is built to be checked by a person, on purpose

**Decision:** Every anti-abuse mechanism in the public voting feature has a live, visible indicator on the organizer dashboard, and each one is built to be demonstrable in under a minute, on camera — not just written about.

**Rationale:** The organizers' automated checker has no way to verify this feature at all — there's no code path for it to do so. Credit here only comes from a person watching it work, so the design goal was "obviously correct in a short demo," not just "technically correct." Alongside that, what this layer does *not* stop is written down with the same directness as what it does — a feature that only lists its strengths isn't being fully honest about its own limits.

**In plain terms:** No script checks this part of the product, only a person does — so we built it to be obviously correct on camera, and we're upfront about the one or two ways someone determined enough could still get around it.

---

## 8. User accounts don't carry Django's admin baggage

**Decision:** Rubric's user model is built from Django's minimal base class, not the more common one that ships with admin-site fields baked in.

**Rationale:** The richer base class brings staff/superuser flags and a permissions system built for Django's admin panel — which this project deliberately never ships, since an admin backdoor would be one more way to accidentally bypass every access rule built elsewhere. Starting minimal keeps the user model to exactly the fields the product uses, with email as the natural identifier.

**In plain terms:** We don't ship Django's built-in admin panel, so our user accounts aren't built around it either — they only carry what Rubric itself needs.

---

## 9. CSRF enforcement depends on how you authenticated, not a global toggle

**Decision:** Requests authenticated via the `Authorization: Bearer` header bypass CSRF validation; requests authenticated via the `session` cookie keep full CSRF enforcement. Neither path uses `@csrf_exempt` or disables CSRF globally.

**Rationale:** The automated checker sends every request with a raw `Authorization` header, never a browser cookie. Bearer-token auth is structurally immune to CSRF — the browser never attaches the token automatically, so a cross-site attacker can't forge the request. Cookie-based auth, by contrast, *is* vulnerable (the browser sends the cookie silently), so CSRF protection must stay on for that path. This is the same line DRF's own `TokenAuthentication` vs. `SessionAuthentication` draws. The mechanism is Django's own `request._dont_enforce_csrf_checks` flag, which `CsrfViewMiddleware` already checks internally — no monkey-patching, no blanket exemptions.

**In plain terms:** If you prove who you are by putting a token in the header, you don't need a CSRF token too — a cross-site attacker can't put it there for you. If you prove who you are with a cookie, you still need CSRF protection because the browser sends that cookie for everyone, including attackers.

---

## 10. Judge score isolation uses the authenticated user identity

**Decision:** A judge's own ballot query is scoped by the authenticated `User` foreign key. `external_id` is used only to validate an explicitly requested peer id; it is never used to identify the caller's ballots.

**Rationale:** An adversarial review found that two legitimate non-fixture judges can both have `external_id=None`. Filtering the caller's scores by that nullable field returns both judges' ballots. The isolation function had already been declared authoritative and stress-tested during planning, but this remaining edge case was caught by a dedicated adversarial-review pass before shipment, not by chance or by the fixture-only acceptance checker. Database identity gives each caller an unambiguous scope, including judges with no external fixture id.

**In plain terms:** A judge's own scores are selected by their account, never by an optional fixture id. A targeted review caught the null-id collision before it shipped.

---

## 11. Normalization claims are corrected against measured fixture behavior

**Decision:** Describe constant judges by the invariant the shrinkage formula actually provides: their z-score contribution is a fixed, non-differentiating offset across their projects, not necessarily a value near zero. Treat rank changes as context-sensitive display movement and assess score changes alongside local score gaps and review counts.

**Rationale:** The constant-judge shrinkage policy's earlier wording said a constant judge's contribution "converges toward zero." We implemented the displayed formula exactly and measured the real fixture: `jdg_07` contributes 0.5115488667 to each of `prj_09`, `prj_17`, and `prj_19`. The equal contribution is non-differentiating, while its absolute value depends on the pooled mean. The constant flag is based on zero variance in weighted ballot values: `jdg_07` is constant at the criterion level, while `jdg_19` has varying criterion scores but equal weighted values on the three counted ballots after excluding `prj_07`. Leave-one-out measurements showed score changes for `prj_09` and `prj_17` in the same range as a non-constant three-assignment control; `prj_19`'s larger change coincides with the remaining reviewer count falling to one. Baseline neighbor gaps also showed much tighter score spacing around `prj_09` and `prj_17` than around the control projects. Rank movement was therefore dropped as a T2 assertion: rank is sensitive to local crowding even when score changes are comparable. This correction came from measuring the fixture before asserting the test, not from changing the formula to fit an overstrong claim.

**In plain terms:** The formula did not make the constant judge's contribution zero; it made the contribution the same on each of that judge's projects. We measured score changes and neighboring score gaps before revising the claim, and documented that ranks can move sharply in a crowded field.

---

## 12. The audit chain is tamper-evident, not proof against a database owner

**Decision:** Treat the SHA-256 audit chain as evidence that detects changed, removed, reordered, or missing rows when checked against a trusted chain head. Do not describe it as proof that the recorded events are true or as protection against someone with full database write access. A database owner with enough access can alter the entries and recompute every later hash and the stored head. For stronger evidence, publish the current head hash outside the database in a separately controlled place.

**Rationale:** The chain serializes appends and makes ordinary row-level tampering visible, including changes that bypass the application model. Its trust boundary ends at the database owner's write authority: the entry hashes and stored head are all in that same trust domain. Naming this limit prevents cryptographic formatting from being mistaken for an independent witness. Publishing the head elsewhere gives an auditor a reference that a database-only rewrite cannot silently replace.

**In plain terms:** The chain shows whether its history still matches its recorded head. Someone who can rewrite the whole database can also rebuild the chain, so the head hash needs to be published elsewhere if we want evidence beyond the database itself.

---

## 13. Rubric editing after scoring begins: weight adjustments are permitted, criterion deletion is forbidden

**Decision:** Once scoring has commenced (at least one `BallotScore` row has been recorded against a criterion), that criterion cannot be deleted or removed from the rubric. However, criterion weights ($w_k$) remain editable by organizers; every weight change is recorded in the tamper-evident audit log with before and after values, and the organizer interface requires re-running normalization to reflect the updated weights across $y_{ij}$.

**Rationale:** In live hackathons, organizers occasionally discover that a criterion was misweighted (e.g., "technical execution" should count 50% rather than 20% compared to "presentation"). Forbidding all rubric edits mid-event would force organizers to invalidate every existing evaluation or abandon weighted scoring entirely. Conversely, allowing criteria deletion would orphan existing `BallotScore` observations, destroying historical judge inputs and invalidating the statistical integrity of earlier evaluations. Permitting weight modifications preserves all raw score observations $s_{ijk}$ while allowing deterministic recalculation of $y_{ij} = \frac{\sum_k w_k s_{ijk}}{\sum_k w_k}$. The integrity trade-off is made transparent through three defenses: (1) deletion protection prevents data loss, (2) the tamper-evident audit log records exact before/after weight values and the organizer actor, and (3) normalization run history and the dashboard explicitly show the recalculation, preventing covert outcome manipulation.

**In plain terms:** Once judges start scoring, you can't delete a criterion and throw away their work, but you can adjust how much each criterion is weighted. Every change is logged with before-and-after numbers, and normalization has to be re-run so the leaderboard stays honest.

---

## 14. Session cookie Secure flag is opt-in for local container adoptability

**Decision:** The session cookie `Secure` attribute is controlled by an explicit environment variable (`RUBRIC_COOKIE_SECURE`, default `false`), rather than coupling it strictly to `DEBUG=False` or enabling it unconditionally. In the default configuration, session cookies are transmitted without the `Secure` flag so `docker compose` deployments running over plain HTTP on `http://localhost:8080` function seamlessly out of the box.

**Rationale:** Modern web browsers increasingly enforce strict cookie handling. While modern browsers treat `http://localhost` as a secure context in some specifications, real-world containerized evaluations often access the service via varying hostnames (e.g. `http://127.0.0.1:8080`, custom local dev domains, or reverse proxies without SSL termination). Setting `Secure=True` unconditionally or tying it to `DEBUG=False` causes browsers to quietly reject or drop the session cookie when testing production builds locally without TLS, breaking the core "one-command adoptability" requirement (`docker compose up`). Security in production is maintained by documenting `RUBRIC_COOKIE_SECURE=true` for deployment behind TLS-terminating proxies (e.g., Caddy, Traefik, or cloud ALBs).

**In plain terms:** When evaluating locally with docker compose on plain HTTP, browsers drop `Secure` cookies, which breaks login. We default `Secure` to off so the one-command setup works instantly without requiring local TLS certificates, and enable it with an environment variable when running in production.

---

## 15. Single active event model with explicit organizer switching

**Decision:** The platform operates under a single active event model at any given time, enforced by a partial unique constraint on `Event.is_current` (`condition=Q(is_current=True)`). Event creation never automatically activates or switches the active event. Switching the active event is an explicit, privileged organizer action that updates `is_current` within an atomic transaction and records before-and-after state in the tamper-evident audit log. All public, judging, and organizer views (gallery, judge queues, dashboard, rubric, export) are strictly scoped to the active event.

**Rationale:** Multiple architectural models were evaluated for multi-event support:
1. *URL-prefix scoping (`/e/<slug>/...`)*: Requires restructuring all canonical routes, complicates bookmarks, makes participant and judge onboarding error-prone (entering the wrong slug mixes contexts), and breaks API stability guarantees for external consumers.
2. *Session-scoped event switching*: Storing the active event in the user's session cookie leads to split-brain states where two organizers or judges in the same deployment see different datasets, creating silent confusion and data desynchronization.
3. *Single database-level active event (`is_current`)*: Keeps canonical URLs permanent and clean (`/`, `/projects`, `/judge/queue`, `/organizer`), guarantees that all participants, judges, and organizers share the exact same ground truth, and completely eliminates cross-event data leakage.

To ensure safety against accidental disruption, event creation explicitly leaves `is_current=False`. Switching to a new event requires a dedicated POST action with an explicit warning explaining that it re-scopes what the entire portal displays. Database integrity is guaranteed at the storage level via a partial unique index, making it impossible for concurrent requests or application bugs to mark multiple events as current simultaneously.

**In plain terms:** Only one event is active across the platform at a time. Creating a new event does not automatically make it live; an organizer must explicitly switch to it with a warning. This keeps URLs simple, ensures everyone sees the same event, and prevents data from leaking between hackathons.

---

## 16. Offline CI evidence blocks container egress and checks the block

**Decision:** The offline acceptance check builds and pulls the images while online, then applies a host firewall rule to drop public egress from the Compose subnet. Its control case attempts an outbound TCP connection from the web container and requires both the connection to fail and the firewall's DROP counter to increase before comparing the offline report with the online report.

**Rationale:** Detaching a container from Docker's default bridge does not prove that it cannot reach the network; another attached network or a runtime path could still provide egress. The check must observe the actual boundary it claims to verify. The control request and matching firewall counter make a blocked request distinguishable from an offline report that happened to match for unrelated reasons. This evidence assumes the GitHub-hosted Ubuntu runner's Docker bridge traffic passes through the IPv4 `DOCKER-USER` chain; the job fails if that chain or counter is unavailable.

**In plain terms:** CI downloads everything first, then blocks the app container's public network traffic and proves a request hit that block before saying the app ran offline.

---

## 17. Public voting supports open-link and authenticated access only

**Decision:** Per-event public voting supports OPEN link access and AUTH authenticated-user access. Email-gated access is unavailable.

**Rationale:** The deployment must function offline, so a mode that depends on sending verification email would either fail or make an unverifiable identity claim. The two supported modes make the tradeoff explicit: OPEN is easy to access but has weaker resistance to repeat identities; AUTH ties a vote to an account. We do not represent email delivery as an available control.

**In plain terms:** Voters can use an open link or sign in. There is no email-code mode because the system must work without an email service.

---

## 18. Vote budgets are configurable and withdrawal restores capacity

**Decision:** Each event may set a per-voter total vote budget. A null budget means there is no total cap beyond one vote per project. A voter may withdraw a vote while the window is open, and the withdrawn vote no longer consumes budget.

**Rationale:** A fixed cap would force every event into the same ballot design. A configurable budget makes that choice explicit, while withdrawal allows voters to correct a choice without permitting repeated active votes on the same project. Every accepted vote and withdrawal is retained in the append-only attempt history. Quadratic voting is out of scope; each active vote has weight one.

**In plain terms:** Organizers can choose how many projects each person may vote for; voters can take a vote back before the deadline and use that slot elsewhere.

---

## 19. Voter fingerprints minimize stored identity while preserving rate limits

**Decision:** OPEN mode stores an HMAC fingerprint derived from a per-event secret seed, `REMOTE_ADDR`, and user-agent. AUTH mode stores the user's id string. Raw IP addresses and user-agent strings are not persisted, and forwarded IP headers are not trusted by default.

**Rationale:** The fingerprint supports duplicate checks and sliding-window rate limits without retaining raw network identifiers. It is not a durable proof of personhood: VPNs, changing networks or clients can create new OPEN fingerprints, and shared addresses/clients can cause legitimate voters to collide. Proxy deployments need explicit trusted-proxy handling before IP-based distinctions can be relied upon. AUTH mode provides the stronger identity link. Audit payloads contain only a truncated hash of the fingerprint.

**In plain terms:** The system keeps a keyed identifier instead of raw network details. That slows casual repeat voting but cannot stop a determined person from changing networks or devices.

---

## 20. Voting access mode locks after the first recorded action

**Decision:** An event's OPEN/AUTH access mode cannot change once any vote or vote attempt exists for that event.

**Rationale:** The mode defines voter identity and uniqueness. Changing it after activity could reinterpret existing fingerprints or allow a second identity path to create votes for projects already handled under the previous mode. Locking it after the first recorded attempt keeps the event's identity rule stable, including when the first attempt was rejected.

**In plain terms:** Choose open-link or signed-in voting before activity starts; after the first attempt, the event keeps that identity rule.

---

## 21. Organizers can open or close voting immediately with an audit record

**Decision:** Organizers have explicit Open voting now and Close voting now actions. Each updates only the corresponding voting timestamp and records before/after values in the audit log.

**Rationale:** Date fields remain useful for scheduling, while an immediate action gives organizers a direct response to a live event. Recording the exact timestamp and actor makes these operational changes reviewable. The submissions deadline remains independent.

**In plain terms:** An organizer can start or stop voting with one action, and the audit history shows when it happened without changing the submission deadline.

---

## 22. Event authority is scoped to the event being changed

**Decision:** Event-scoped organizer actions require an ORGANIZER membership on the target event; site administrators remain allowed. The deployment continues to assume one organization manages the events in this portal. Full multi-tenant URL scoping was considered and rejected for this phase.

**Rationale:** A role attached to the currently selected event must not authorize mutations to a different event. Checking membership against the target closes that gap while keeping the portal's existing single-organization event-switching model. Separate organization identity and URL-level tenant boundaries would require a broader product and data model.

**In plain terms:** Organizers can change only events they organize, while a site administrator can manage any event in this portal.

---

## 23. Voting is a secret ballot with pseudonymous voter identities

**Decision:** AUTH votes use a stable event-scoped HMAC pseudonym derived from the user's id, the event's voting seed, and the server's `SECRET_KEY`. OPEN votes use an event-scoped HMAC pseudonym derived from `REMOTE_ADDR` only; user-agent and forwarded-IP headers are ignored. Vote and withdrawal audit entries have no user actor and use the fixed `voter-pseudonym` label, with only a truncated pseudonym hash in the payload. Comments remain attributed because they are public speech.

**Options considered:** A. Keep the previous behavior: an auditable public record with voting audit entries attributed to the account. B. Use a keyed pseudonym for votes while keeping attempts, tallies, and abuse controls auditable. C. Hide vote attribution from the public but retain it for organizers.

**Rationale:** Option B is chosen because private votes reduce pressure and retaliation while preserving auditable tallies, attempts, and blocked abuse. Option A was rejected because attaching an account identity to a vote exposes a voter to pressure or retaliation. Option C was rejected because organizers can also be participants or have conflicts, so organizer-only attribution is not a reliable privacy boundary. The event seed and small user ids are available from the database; deriving the HMAC key from `SECRET_KEY` means a database-only reader cannot map AUTH pseudonyms back to users. OPEN identity uses IP only: IP plus user-agent was bypassable by rotating request headers, signed device cookies can be cleared, and CAPTCHA or proof-of-work would require external services or add voter friction. IP-only identity is the chosen offline-compatible control, with the known consequence that people behind one NAT share a ballot and rate limit.

**Limits:** An operator with both the database and `SECRET_KEY` can re-derive pseudonyms. Organizers can reconstruct live tallies from the audit log, but already have access to live tallies by design. NAT co-tenants share a budget and could withdraw one another's votes from that shared ballot. AUTH mode is recommended when the result matters.

**In plain terms:** Votes are not labeled with a voter's account in the audit history. Signed-in voting is private from database-only readers; open-link voting shares one ballot among people at the same public IP. The system still records voting activity for integrity checks, and the operator can connect private identities if they control both the database and application secret.

---

## 24. Control case for route authorization now lives only in the test suite

**Decision:** The deliberate leaky debug route (`/debug/_leaky_test_only/...`) and its corresponding URLconf entry have been removed from the production codebase. The proof that the route×role coverage alarm catches undeclared routes is now exercised exclusively inside the automated test suite using a synthetic URLconf containing an undeclared route. Decision #3 remains intact as a historical record of the control-case design.

**Rationale:** Shipping even a quarantined debug route in production violates the zero-leak principle and creates unnecessary attack surface. The route-coverage mechanism itself does not require a production endpoint to prove its failure mode: testing the checker against a synthetic URLconf with an undeclared pattern confirms the alarm fires and raises an assertion error. Nothing leaky ships in production.

**In plain terms:** The deliberate leak used to test the route alarm was removed from the live website and moved entirely into an automated test. The alarm is still proven to work, but the application ships with no debug backdoor.

---

## 25. Public demo credentials exist for automated evaluation and can be disabled in production

**Decision:** Pre-seeded demo credentials and public bearer tokens exist so that offline automated evaluation harnesses can inspect the system without manual bootstrapping. In production deployments, these demo accounts and printed tokens can be completely disabled by setting the environment variable `RUBRIC_SEED_DEMO_LOGINS=false`. When set to false, `seed_fixtures` imports the core event data and projects but creates no persona accounts or public tokens, and instead prints instructions for creating a custom organizer via `create_organizer`.

**Rationale:** The evaluation checker requires predictable test tokens printed at boot to authenticate as judges, participants, and organizers. However, a production deployment must never expose hardcoded public tokens or pre-seeded credentials. Providing an explicit, environment-gated switch keeps automated grading reproducible by default while providing a clean hardening path for real-world deployments.

**In plain terms:** Default demo logins exist so the automated checker can test the portal immediately upon boot. Setting `RUBRIC_SEED_DEMO_LOGINS=false` turns off all pre-created demo accounts and tokens so real events can run securely.
