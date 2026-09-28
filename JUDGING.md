# JUDGING.md — System Architecture, Verification & Integrity Defense

This document describes the architectural implementation, statistical methodology, and security controls in Rubric as they exist in code today. It is written to provide a rigorous, transparent explanation of how evaluations, assignments, score normalizations, and audit trails work, noting real fixture behavior and honest operational boundaries.

---

## 1. System Overview & Architecture

Rubric is a hackathon evaluation platform engineered around judging integrity, verifiable data lineage, and defensible statistical outcomes.

### Core Architectural Principles
1. **Authoritative Domain Services**:
   - Every state transition and domain query is executed exclusively within the service layer (`services.*`).
   - Presentation layers—server-rendered HTML templates with HTMX and the JSON REST API—are thin wrappers over identical service functions. No business logic or access control is duplicated across views.
2. **Defaults-Closed Role-Based Access Control**:
   - Requests resolve to an authenticated `Actor` or an unprivileged `AnonymousActor` via `AuthMiddleware`.
   - Every route in the URLconf is registered against an explicit policy expectation in `tests/authz_expectations.yaml`. If an endpoint is added without an explicit policy declaration, the CI test suite fails immediately.
3. **Reproducible & Deterministic Evaluation**:
   - Score collapse, graph connectivity metrics, and shrinkage normalizations are strictly deterministic.
   - All collections are iterated over canonical primary or external keys, ensuring byte-identical results across independent runs on identical datasets.
4. **Append-Only Tamper-Evident Ledger**:
   - State-changing domain mutations are recorded within the same database transaction as the underlying change, chained using cryptographic SHA-256 digests.

### Key Divergences from Initial Planning Documents
- **Duplicate Flag Direction (D-02)**: Early draft mapping tables mistakenly inverted the duplicate relationship. The production implementation adheres strictly to the authoritative policy: the earlier submission (`prj_07`, submitted at 04:29 UTC) flags itself against the canonical later submission (`prj_41`, submitted at 17:57 UTC) via `prj_07.is_duplicate_of = prj_41`.
- **Field Types**: Replaced PostgreSQL-specific `ArrayField` with portable `models.JSONField` for project tags and audit payloads, preserving full functional and test parity across SQLite and PostgreSQL environments.
- **Unified Authentication**: User accounts authenticate using Django's password hasher (`create_user`, `check_password`) to generate standard `AuthToken` models, set as `session` cookies with `HttpOnly=True`, `SameSite=Lax`, and `Secure=not settings.DEBUG`. This unifies the authentication path with bearer token authentication for seeded personas rather than maintaining separate session subsystems.

---

## 2. Assignment Algorithm & Graph Health (A-01 – A-07)

### Scope
The 126 fixture scores are imported as immutable completed history (`JudgeAssignment.status = COMPLETED`). The assignment algorithm operates strictly additively on new submissions or under-reviewed projects in a live event; it never reshuffles or deletes existing evaluations.

### Policies (A-01 – A-07)
- **A-01 (Track Eligibility)**: Hard constraint. Judges are only assigned to projects belonging to tracks they are declared eligible to review (`JudgeTrackEligibility`).
- **A-02 (Conflict of Interest)**: Hard constraint. Judges who share team membership (`TeamMembership`) with a project team are strictly disqualified from evaluating that project.
- **A-03 (Balanced Reviewer Load)**: The greedy assignment algorithm prioritizes the least-loaded eligible judges at each step, actively minimizing the spread between review loads across the panel.
- **A-04 (Transparent Under-Coverage)**: If a track lacks sufficient eligible judges to meet target reviews ($k$), shortfalls are recorded explicitly in `AssignmentRun.under_coverage` and highlighted on the organizer dashboard rather than silently assigning fewer reviews.
- **A-05 (Measured Graph Connectivity)**: Connectivity across judge pools is measured via the graph Laplacian. Genuinely disconnected track components are flagged rather than artificially bridged.
- **A-06 (Idempotent & Additive Execution)**: Repeated assignment runs only fill missing coverage gaps up to target $k$. Completed assignments and in-progress ballots are never modified.
- **A-07 (Reproducible Seeded Randomness)**: Tie-breaking among equally eligible and equally loaded judges uses pseudo-random shuffling with a seed recorded in `AssignmentRun.seed` for deterministic auditability.

### Graph Health & Algebraic Connectivity
Graph connectivity is evaluated over the bipartite judge–project assignment graph:
1. Two judges share an edge if they are co-assigned to at least one project.
2. The graph Laplacian $L = D - A$ is computed across all judges.
3. The number of connected components equals the multiplicity of zero eigenvalues ($\lambda_i < 10^{-9}$) of $L$.
4. **Algebraic Connectivity (Fiedler Value $\lambda_2$)**:
   - For connected components ($n=1$), $\lambda_2 > 0$ quantifies graph robustness against bottlenecks.
   - On the real fixture (`evt_01`), the panel forms **exactly 1 connected component** spanning all 30 judges, with a global Fiedler value $\lambda_2 \approx 0.0875$.
   - Multi-track judges (such as `jdg_01`, `jdg_04`, `jdg_07`, and `jdg_29`) serve as natural structural anchors connecting different tracks.

---

## 3. Normalization Engine (D-01 – D-05)

### Methodology & Mathematical Specification
Raw ratings are adjusted using an empirical-Bayes shrinkage estimator ($\kappa_0 = \nu_0 = 4$). Each judge's mean rating $\bar{y}_j$ and variance $s_j^2$ are pulled toward the event-wide pooled mean $\mu_0$ and variance $\sigma_0^2$.

#### Step 0: Weighted Rubric Collapse
Each completed ballot is collapsed into a single scalar observation $y_{ij}$ using the organizer-configured rubric weights:
$$y_{ij} = \frac{\sum_k w_k s_{ijk}}{\sum_k w_k}$$
Where $s_{ijk}$ is the score assigned by judge $j$ to project $i$ on criterion $k$, and $w_k$ is the criterion weight.

#### Step 1: Empirical-Bayes Shrinkage
For judge $j$ with $n_j$ evaluations:
$$\tilde{\mu}_j = \frac{n_j \bar{y}_j + 4 \mu_0}{n_j + 4}$$
$$\tilde{s}_j^2 = \frac{n_j s_j^2 + 4 \sigma_0^2}{n_j + 4}$$
$$\tilde{z}_{ij} = \frac{y_{ij} - \tilde{\mu}_j}{\sqrt{\tilde{s}_j^2}}$$

#### Step 2: Rescaled Project Aggregation
Project $i$'s normalized score is the unweighted arithmetic mean of judge z-scores $\bar{\tilde{z}}_i = \frac{1}{M_i} \sum_{j} \tilde{z}_{ij}$, rescaled to the original $[1, 5]$ scale:
$$\text{Score}_{\text{norm}}(i) = \mu_0 + \bar{\tilde{z}}_i \cdot \sigma_0$$
Scores are clamped to $[1.0, 5.0]$. On the real fixture, event-wide parameters evaluate to pooled mean $\mu_0 = 3.6190$ and pooled variance $\sigma_0^2 = 0.6019$ ($\sigma_0 \approx 0.7759$).

### Policy Commitments (D-01 – D-05)
- **D-01 (Dual Record Display)**: The raw mean is displayed alongside the normalized score and normalized rank on all screens (dashboard, gallery, CSV exports). Normalization annotates the record; it never overwrites raw data.
- **D-02 (Duplicate Submission Handling)**:
  - `prj_07` (submitted at 04:29 UTC) and `prj_41` (submitted at 17:57 UTC) were submitted by team `tm_07` with identical titles ("Dry Harbour") and summaries.
  - `prj_41` is treated as canonical and actively ranked: raw mean = 3.8333, normalized score = 3.7912, rank = 8.
  - `prj_07` is flagged by `"duplicate-detection policy v1"` (`is_duplicate_of = prj_41`), excluded from ranking (rank = `None`), but retained in the database. Organizers can restore it with one click (`duplicate_override = True`).
- **D-03 (The Constant-Score Judge)**:
  - Judge `jdg_07` awarded identical scores (4.0 in all criteria) across all three assigned projects: `prj_09`, `prj_17`, and `prj_19`.
  - Raw variance is zero ($s_j^2 = 0$), but shrinkage variance remains strictly positive: $\tilde{s}_j^2 = \frac{0 + 4(0.6019)}{3 + 4} = 0.3440 > 0$.
  - `jdg_07`'s normalized z-score contribution is identical across all three projects: $z \approx 0.5115$. This acts as a non-differentiating offset rather than skewing relative ranks.
  - `jdg_07` is flagged prominently on the organizer dashboard (`scored 3/3 assignments identically`); their ratings are never silently discarded.
- **D-04 (Thin Review Batches & Compounding Risk)**:
  - 8 of 41 projects received only 2 reviews instead of the target 3: `prj_10, prj_15, prj_18, prj_19, prj_24, prj_29, prj_39, prj_40`.
  - Review counts are published alongside all ranks.
  - **The `prj_19` Compounding Case**: `prj_19` received only 2 reviews and one came from constant judge `jdg_07`. As a result, its only relative differentiating signal originates from judge `jdg_29`. The dashboard surfaces both warnings together (`Thin Review Count (2)` and `Constant Judge (jdg_07)`).
  - Out of 41 total projects, exactly 40 are ranked and 1 (`prj_07`) is excluded as duplicate.
- **D-05 (Component-Bounded Calibration)**: Cross-judge normalization is valid only within connected subgraphs. If disconnected components exist, ranks are calculated per component.

### Honest Limits & Statistical Clarifications
1. **Pragmatic Shrinkage Estimator, Not a Full Posterior**:
   This engine uses empirical shrinkage formulas. It is not a full hierarchical Bayesian model (such as MCMC sampling from a joint posterior). We describe it accurately as a robust empirical-Bayes point estimator.
2. **Rank Sensitivity vs. Score Movement**:
   Ordinal rankings are highly sensitive in crowded regions of the score distribution. In the fixture, `prj_09` (norm = 3.6128, rank = 16) and `prj_17` (norm = 3.5741, rank = 19) sit within a dense cluster where tiny score shifts of ~0.002 to ~0.017 move several ranks. In sparser regions (such as `prj_13`/`prj_26`, separated by ~0.05), ranks remain stable. Rank movement must always be evaluated in conjunction with absolute score changes and review counts.

---

## 4. Score Isolation & Endpoint Security

### Single-Function Enforcement
To prevent subtle access control drift, judge score inspection across the portal is enforced by a single service function:
`services.judging.get_scores(actor, judge_external_id=None)`

Both P-11 routes map to this single handler:
1. `GET /api/judge/scores`: Requests own scores.
2. `GET /api/judge/scores?judge=jdg_07`: Requests scores for a specific judge ID.

### Role Authorization Logic
- **Organizers**: May view all scores or query any specific judge's ballots.
- **Judges**: May only view their own ballots. If a judge passes `?judge=other`, the request is rejected with `403 Forbidden`.
- **Participants & Anonymous Users**: Denied access with `403 Forbidden` or `401 Unauthorized`.

### The Null-`external_id` Vulnerability & Resolution
During early development, a judge's own ballots were queried by matching `judge.external_id`. A dedicated adversarial review identified a critical flaw: legitimate registered judges outside the initial test fixtures have `external_id = None`. Querying own ballots by `external_id = None` matched all other non-fixture judges simultaneously, causing cross-judge score leakage.

**Resolution (Decision 10)**:
Caller identity is strictly bound to the authenticated user foreign key:
`JudgeAssignment.objects.filter(judge=actor.user)`
The nullable `external_id` is used solely to resolve explicit organizer lookups.

---

## 5. Audit Log Ledger (What the Chain Does and Does Not Prove)

### Ledger Mechanics
The audit log records state transitions using an append-only SHA-256 hash chain:
1. **Atomic Sequence & Locking**:
   - Every entry is assigned a strictly monotonic sequence number (`seq`) serialized through an exclusive lock on the singleton `AuditChainHead` table (`id=1`).
2. **Deterministic Payload Digest**:
   - Entries bind: `seq`, `prev_hash`, UTC timestamp, `actor`, `action`, `target`, and `payload`.
   - Payloads are serialized using canonical JSON (sorted keys, compact delimiters, rejection of non-finite numbers).
   - Entry hash: `SHA256(prev_hash + canonical_json)`.
3. **Database-Level Immutability**:
   - On PostgreSQL, database triggers (`audit_log_entry_no_row_mutation`, `audit_log_entry_no_truncate`) execute `RAISE EXCEPTION 'audit log entries are immutable'` on any raw SQL `UPDATE`, `DELETE`, or `TRUNCATE`.

### What the Chain DOES Prove
- **Tamper Evidence**: Any alteration of past payloads, timestamps, or actor identifiers breaks the hash chain, detected by `services.audit.verify()` and the standalone offline verifier (`scripts/verify_audit_chain.py`).
- **Completeness & Ordering**: Deleting rows or inserting backdated events creates an unbridgeable hash mismatch.
- **Offline Verifiability**: Chain exports (`GET /api/v1/organizer/audit-log/verify?download=1`) can be verified offline with zero dependencies.

### What the Chain DOES NOT Prove (Decision 12)
- **Truth of Logged Events**: The hash chain proves that an event was recorded at sequence $N$ with a specific payload. It does not prove that the real-world event was truthful (e.g., an organizer recording a fraudulent override).
- **Defense Against Database Superusers**: A database owner with raw root privileges can drop triggers, modify historical rows, recompute SHA-256 hashes sequentially, and update the singleton head.
- **Evidentiary Boundary**: True immutability against database administrators requires publishing the head hash periodically to an external, independently controlled anchor (such as a public git commit, transparency log, or signed timestamp).

---

## 6. Public Voting & Anti-Abuse Threat Model — [TODO: G6]

*This section is an outline of the threat model and defense mechanisms scheduled for implementation and verification in Milestone G6 (Task T3).*

### Target Threat Vectors
1. **Automated Sybil Attacks**: High-volume voting scripts attempting to inflate public vote totals.
2. **Account Creation Rings**: Disposable email address spamming to circumvent one-vote-per-user constraints.
3. **Ballot Comment Brigading**: Coordinated harassment or review bombing within project comments.
4. **Race Conditions**: Parallel HTTP POST requests attempting to double-cast votes before database lock acquisition.

### Planned Defenses & Controls
- **Rate Limiting & Velocity Tracking**: Per-IP and per-account burst controls.
- **Verified Voter Identity**: Age restrictions and participant validation on voting eligibility.
- **Organizer Moderation & Telemetry**: Visible abuse telemetry, comment flagging, and vote velocity charts on the organizer dashboard.
- **Idempotent Transaction Locks**: Row-level database locks preventing race condition double-voting.
