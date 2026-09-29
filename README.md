# Rubric

> **Auditable, isolated, defensible hackathon judging.**  
> Self-hostable hackathon submission and evaluation platform featuring backend-enforced score isolation, empirical-Bayes shrinkage normalization, and PostgreSQL-backed cryptographic audit logging.

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/django-5.2-green.svg)](https://www.djangoproject.com/)
[![PostgreSQL](https://img.shields.io/badge/postgresql-16-blue.svg)](https://www.postgresql.org/)
[![CI](https://img.shields.io/badge/CI-passing-brightgreen.svg)](.github/workflows/ci.yml)

---

### DogFood 2026 Submission Metadata

- **Project:** Rubric
- **Hackathon:** DogFood 2026
- **Team:** Team AM
- **Repository:** [https://github.com/Dev-Am12/Rubric](https://github.com/Dev-Am12/Rubric)
- **Demo Video:** [▶ Demo Video (Placeholder)](https://example.com/replace-with-demo-video)
- **Slide Deck:** [📊 Slide Deck (Placeholder)](https://example.com/replace-with-slide-deck)

---

## Table of Contents

1. [Quick Start](#1-quick-start)
2. [What Rubric Actually Is](#2-what-rubric-actually-is)
3. [Design Philosophy](#3-design-philosophy)
4. [Feature & Tier Status](#4-feature--tier-status)
5. [System Architecture](#5-system-architecture)
6. [The Judging Engine](#6-the-judging-engine)
   - [Weighted Rubric](#weighted-rubric)
   - [Judge Assignment & Graph Health](#judge-assignment--graph-health)
   - [Cross-Judge Normalization (Empirical-Bayes)](#cross-judge-normalization-empirical-bayes)
   - [Evidence: Real Fixtures vs. Synthetic Simulation](#evidence-real-fixtures-vs-synthetic-simulation)
7. [Judging Integrity & Role Isolation](#7-judging-integrity--role-isolation)
8. [Cryptographic Auditability](#8-cryptographic-auditability)
9. [Public Voting (Tier T3)](#9-public-voting-tier-t3)
   - [What It Stops](#what-it-stops)
   - [What It Does Not Stop](#what-it-does-not-stop)
10. [Real Fixture Data & Deliberate Edge Cases](#10-real-fixture-data--deliberate-edge-cases)
11. [Verification & Test Parity](#11-verification--test-parity)
12. [Submission Acceptance (`.dogfood.toml`)](#12-submission-acceptance-dogfoodtoml)
13. [Repository Layout](#13-repository-layout)
14. [Running Your Own Event](#14-running-your-own-event)
15. [Honest Limitations](#15-honest-limitations)
16. [Documentation Map](#16-documentation-map)
17. [License](#17-license)

---

## 1. Quick Start

### The One-Command Evaluation Path (Docker Compose)

Rubric is packaged to boot self-contained with no external dependencies or cloud calls:

```bash
git clone https://github.com/Dev-Am12/Rubric.git
cd Rubric
docker compose up
```

#### What happens on startup:
1. **PostgreSQL 16** starts and passes health checks.
2. The **web service** runs migrations (`manage.py migrate --noinput`), populates the database from `fixtures.json` (`manage.py seed_fixtures`), and binds **Gunicorn (3 workers)** with WhiteNoise on port `8080`.
3. The portal is immediately available at `http://localhost:8080`.

#### Deterministic Evaluation Credentials:
`seed_fixtures` prints pre-configured bearer tokens matching `.dogfood.toml`:

```text
seeded. test logins:
  organizer:   Authorization: Bearer rubric_seed_organizer_tok_9f8e7d6c5b4a
  judge_a:     Authorization: Bearer rubric_seed_judge_a_tok_1a2b3c4d5e6f
  judge_b:     Authorization: Bearer rubric_seed_judge_b_tok_7a8b9c0d1e2f
  participant: Authorization: Bearer rubric_seed_participant_tok_3f4e5d6c7b8a
```

*Web Browser Login:* An organizer account is seeded at `superorganizer@example.com` with password `organizer123`.

### Running the Official Acceptance Checker

In a separate terminal (with Python 3 standard library only):

```bash
python run.py .dogfood.toml
```

Expected output:
```text
DOGFOOD 2026 acceptance report
portal: http://localhost:8080
claimed: nothing
fixtures: fixtures.json

T1  gallery is public ................. PASS
T1  project from fixtures shown ....... PASS
T1  closed event refuses submissions .. PASS
T2  judge sees own scores ............. PASS
T2  judge cannot see peer scores ...... PASS
T2  participant blocked ............... PASS
T2  csv export works .................. PASS

claimed nothing, verified T1 T2
```

### Local Development Workflow (Native Python & PostgreSQL)

If you develop locally without Docker:

```bash
# 1. Activate your virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate  # Or .venv\Scripts\activate on Windows
pip install -r requirements.txt

# 2. Point to local PostgreSQL and run tests
export DATABASE_URL="postgresql://rubric:rubric_dev_only@localhost:5432/rubric_dev"
export PYTHONPATH="src;."
python src/manage.py test tests --settings=rubric.settings_test

# 3. Start local development server
python src/manage.py migrate
python src/manage.py seed_fixtures
python src/manage.py runserver 8080
```

---

## 2. What Rubric Actually Is

Rubric is a complete, self-hostable hackathon platform designed for high-stakes collegiate and industry hackathons. Rather than treating an event as merely a submission form with a public gallery, Rubric treats evaluation as an auditable pipeline requiring cryptographic provenance, mathematical calibration across subjective judges, and backend-enforced privacy boundaries.

```mermaid
flowchart TD
    EV[1. Event Definition<br/>Dates, Tracks, Prizes, Rubric] --> TM[2. Team Roster<br/>Invite links & Codes]
    TM --> SUB[3. Submissions<br/>Repo, Video, Live URLs]
    SUB --> DUP[4. Integrity Screening<br/>Near-deadline duplicates flagged]
    DUP --> ASSIGN[5. Balanced Assignment<br/>Track eligibility, conflict checks, graph health]
    ASSIGN --> JUDGE[6. Independent Judging<br/>Two-pane console, autosave, isolated scores]
    JUDGE --> NORM[7. Empirical-Bayes Normalization<br/>Cross-judge shrinkage & calibration proof]
    NORM --> RES[8. Ranked Results<br/>Raw mean, normalized score, review counts]
    RES --> VOTE[9. Public Voting (T3)<br/>OPEN or AUTH mode, pseudonymous ballot]
    VOTE --> AUDIT[10. Audit Ledger & CSV Export<br/>SHA-256 hash chain & trigger-enforced immutability]
```

---

## 3. Design Philosophy

1. **Correctness Before Feature Breadth:** We stopped after T3 to ensure T1, T2, and T3 were provably solid, concurrency-tested, and audited against adversarial attacks rather than shipping half-working stretch features.
2. **Backend-Enforced Authorization:** Security never depends on hidden template links. Route authorization is checked at the service layer via explicit `Actor` resolution and audited with strict test alarms.
3. **Service-Layer Business Logic:** Django views are thin controllers that parse parameters and invoke pure service functions (`services.*`). Domain rules and database mutations live in transactions with audit records.
4. **Explicit Provenance & Immutability:** Nothing important is deleted. Duplicate submissions are flagged, comments are hidden rather than pruned, and all configuration changes are recorded in an append-only SHA-256 hash chain.
5. **Self-Hostable & Offline-First:** Zero reliance on CDNs, cloud authentication providers, or third-party APIs. CSS is written from scratch, HTMX is vendored locally, and CI includes an egress-blocking firewall test.
6. **Defensible Statistics:** Normalization uses an inspectable empirical-Bayes shrinkage formula rather than an opaque black box.

---

## 4. Feature & Tier Status

| Tier | Area | Implementation Status | Evidence / Verification Method |
|---|---|---|---|
| **T1** | **Core Portal** | **Fully Implemented** | Machine-verified by `run.py` (`gallery is public`, `project from fixtures shown`, `closed event refuses submissions`). |
| **T1** | **Events & Teams** | **Fully Implemented** | Multi-event management, current-event isolation, team invite codes, and membership rosters verified by `tests/test_g5_step7.py` and `tests/test_g5_step8.py`. |
| **T2** | **Judging Engine** | **Fully Implemented** | Machine-verified by `run.py` (`judge sees own scores`, `judge cannot see peer scores`, `participant blocked`, `csv export works`). |
| **T2** | **Normalization** | **Fully Implemented** | Empirical-Bayes shrinkage, constant-judge handling, graph Laplacian connectivity analysis, and 100-seed synthetic sweep verified by `tests/test_docs_consistency.py`. |
| **T3** | **Public Voting** | **Substantially Implemented** | OPEN and AUTH access modes, voter budgets, withdrawal, per-voter deterministic shuffle, live result gating, and comment moderation verified by `tests/test_g6_step*.py` (human-verifiable in under 60s). |
| **T4** | **Stretch Features** | **Incomplete / Not Claimed** | We ship JSON action parity and CSV exports, but **no** webhooks, certificates, embeddable widgets, or published OpenAPI schemas. |

> [!IMPORTANT]
> The official acceptance checker (`run.py`) machine-verifies **T1 and T2 only**. Passing `run.py` does not prove T3 or T4.

---

## 5. System Architecture

```mermaid
flowchart TB
    subgraph Client_Layer ["Client Layer"]
        Browser["Web Browser (Participant / Judge / Organizer)"]
        Curl["curl / Acceptance Checker (Bearer Token)"]
    end

    subgraph Web_Container ["Web Container (Gunicorn x3 + WhiteNoise)"]
        AuthMW["AuthMiddleware<br/>Token Hash → Actor Resolution"]
        
        subgraph View_Controllers ["View Layer (47 URLconf Routes)"]
            HTMLViews["Django Template Views<br/>(Server-rendered + HTMX)"]
            JSONViews["API Endpoints<br/>(/api/judge/scores, /api/export.csv)"]
        end

        subgraph Service_Boundary ["Core Service Layer (services.*)"]
            S_Accounts["services.accounts"]
            S_Events["services.events"]
            S_Teams["services.teams"]
            S_Submissions["services.submissions"]
            S_Judging["services.judging"]
            S_Assign["services.assignment"]
            S_Norm["services.normalization"]
            S_Voting["services.voting"]
            S_Audit["services.audit"]
        end
    end

    subgraph Data_Layer ["Data Layer (PostgreSQL 16)"]
        DomainDB[(Relational Models<br/>Events, Teams, Submissions, Rubrics, Ballots)]
        AuditLog[(Audit Log Ledger<br/>SHA-256 Hash Chain)]
        PG_Triggers["PostgreSQL Immutability Triggers<br/>(BLOCK UPDATE/DELETE/TRUNCATE)"]
    end

    Browser -->|Session / Cookie| AuthMW
    Curl -->|Authorization: Bearer| AuthMW
    AuthMW --> HTMLViews & JSONViews
    HTMLViews & JSONViews --> Service_Boundary
    Service_Boundary --> DomainDB
    Service_Boundary --> AuditLog
    AuditLog --- PG_Triggers
```

### Application Breakdown:
- **`accounts`**: Custom `User`, `AuthToken` (stored as SHA-256 hashes), rate-limiting `AuthAttempt`, `EventMembership` (ORGANIZER, JUDGE, PARTICIPANT), and request-scoped `Actor` models.
- **`events`**: Multi-event management, `Event.is_current` partial unique constraint, tracks, prizes, and voting configuration.
- **`teams`**: Team creation, member rosters, and secure join codes (`/teams/join/<code>`).
- **`submissions`**: Project submissions, sanitized repository/video/live URLs, and duplicate submission flags (`is_duplicate_of`).
- **`judging`**: Rubric criteria, weights, `JudgeAssignment`, `Ballot`, criterion scores, and judge track eligibility.
- **`services.assignment`**: Balanced load distribution and graph Laplacian connectivity analysis.
- **`services.normalization`**: Empirical-Bayes shrinkage calibration, 100-seed synthetic sweep, and calibration evidence.
- **`voting`**: Secret pseudonymous voting, per-voter budgets, append-only `VoteAttempt` log, and flag-and-hide comment moderation.
- **`audit`**: SHA-256 chained transaction logging with PostgreSQL trigger-enforced immutability.
- **`importer`**: Management commands for idempotent data loading (`seed_fixtures`).
- **`api`**: JSON and CSV endpoints fulfilling the `.dogfood.toml` specification.

*Note on URLconf:* There are **47 actual `path()` declarations** in `src/rubric/urls.py`. The `peer_scores` entry in `.dogfood.toml` (`/api/judge/scores?judge=jdg_07`) is a query-parameterized variant of `judge_scores`, not a separate route.

---

## 6. The Judging Engine

### Weighted Rubric
Organizers configure rubric criteria per event with custom weights and point maximums (`/organizer/rubric`). When a judge scores a project, criterion scores are collapsed into a weighted ballot value $y_{i,j}$:

$$y_{i,j} = \frac{\sum_{k} w_k \cdot \text{score}_{i,j,k}}{\sum_{k} w_k}$$

- Criteria cannot be deleted once scored (preventing historical rewriting).
- Score inputs are validated against criterion bounds $[0, \text{max\_points}]$.
- Autosaving (`/judge/ballots/<id>/autosave`) caches drafts; ballots are only finalized when submitted.

### Judge Assignment & Graph Health
To evaluate hackathons with specialized tracks, judges are assigned using a deterministic, constrained load-balancing algorithm:
1. **Hard Track Eligibility:** Judges are only assigned to projects in tracks they are declared eligible for (`JudgeTrackEligibility`).
2. **Conflict of Interest:** Team members are strictly prohibited from evaluating their own projects.
3. **Load Balancing:** At each assignment step, the least-loaded eligible judge is prioritized.
4. **Graph Health Analysis:** Cross-judge normalization relies on judge overlap. Rubric builds the judge adjacency graph, computes the graph Laplacian $L = D - A$, and derives the algebraic connectivity (Fiedler value $\lambda_2$). In the fixture data, all 30 judges form a single connected component with global Fiedler value $\lambda_2 \approx 0.0875$, bridged by four multi-track judges (`jdg_02`, `jdg_03`, `jdg_11`, `jdg_29`).

### Cross-Judge Normalization (Empirical-Bayes)
Judges exhibit systematic bias: some score harsh, some lenient, and some never differentiate. Rubric applies an **empirical-Bayes shrinkage estimator**:

For judge $j$ with $n_j$ completed ballots, raw mean $\bar{y}_j$, raw variance $s_j^2$, and event-wide pooled mean $\mu_0$ and variance $\sigma_0^2$:

$$\mu_j = \frac{n_j \bar{y}_j + 4 \mu_0}{n_j + 4}$$

$$s_j^2 = \frac{n_j s_j^2 + 4 \sigma_0^2}{n_j + 4}$$

$$z_{i,j} = \frac{y_{i,j} - \mu_j}{\sqrt{s_j^2}}$$

A project's final score is the mean of its judges' standardized ratings mapped back to the 1–5 scale:

$$\text{normalized}(i) = \mu_0 + \left( \frac{1}{M_i} \sum_{j} z_{i,j} \right) \sigma_0 \quad (\text{clipped to } [1, 5])$$

Prior strength is set to $\kappa_0 = \nu_0 = 4$. At $n=3$, a judge's own variance receives $3/7$ weight and the pool receives $4/7$. This prevents low-variance judges from causing division by zero.

### Evidence: Real Fixtures vs. Synthetic Simulation

#### 1. Real Fixture Calibration
Measured on fixture `evt_01` (121 counted ballots from 29 judges; duplicate `prj_07` excluded):
- Pooled parameters: $\mu_0 = 3.5758$, $\sigma_0^2 = 0.3930$, $\sigma_0 = 0.6269$.
- The inter-judge standard deviation of raw mean scores across judges is **0.3235**. After empirical-Bayes shrinkage, the standard deviation of normalized judge means is **0.2023**—a **37.5% reduction** in cross-judge scale dispersion.

#### 2. Synthetic Ground-Truth Simulation (100 Seeds)
To evaluate ranking recovery against planted ground truth, `services.normalization.synthetic_validation_sweep(range(100))` runs 100 simulations (20 projects, 10 judges with leniency bias $\in [-1.5, +1.5]$, Gaussian noise):

| Metric | Raw Mean Spearman $\rho$ | Normalized Score Spearman $\rho$ |
|---|---|---|
| **Mean** | 0.7347 | **0.8949** |
| **Median** | 0.7451 | **0.9060** |
| **Min** | 0.3158 | **0.7293** |
| **Max** | 0.9023 | **0.9759** |

- **Win Rate:** Normalization outperformed raw mean ranking in **100 out of 100 seeds (100.0%)**.
- Displayed live under `/organizer/normalization` with the explicit label **SYNTHETIC**.

> [!NOTE]
> Normalization is a practical shrinkage calibration, not a claim of recovering an absolute "objective" truth. In crowded ranking regions, small score shifts can move ordinal ranks significantly.

---

## 7. Judging Integrity & Role Isolation

The central security boundary required by DogFood 2026 is:
> *A judge may retrieve their own scores, but cannot retrieve another judge's scores merely by changing a query parameter.*

```mermaid
sequenceDiagram
    autonumber
    participant C as HTTP Client (Bearer Token)
    participant MW as AuthMiddleware
    participant API as api.views.judge_scores_view
    participant S as services.judging.get_scores
    participant DB as PostgreSQL

    C->>MW: GET /api/judge/scores?judge=jdg_07
    MW->>MW: Hash token, resolve Actor (role, current_event)
    MW->>API: request.actor
    API->>S: get_scores(actor, judge_external_id="jdg_07")
    
    alt Actor is Organizer
        S->>DB: Fetch requested judge's scores
        S-->>C: 200 OK + Scores JSON
    else Actor is Judge (jdg_08) requesting jdg_07
        S->>S: Assert actor.user matches target judge
        S-->>C: 403 Forbidden ("Judges may only access their own scores.")
    else Actor is Participant or Anonymous
        S-->>C: 401 Unauthorized / 403 Forbidden
    end
```

### Defense-in-Depth Mechanisms:
1. **Single Backend Chokepoint:** Both `/api/judge/scores` and `/api/judge/scores?judge=<id>` are routed through `services.judging.get_scores()`. Authorization is enforced on the database record (`JudgeAssignment.judge == actor.user`), never relying on URL parameters or client-side filtering.
2. **Route Authorization Policy Matrix:** Every single route in Rubric is declared in `tests/authz_expectations.yaml` across six distinct personas (anonymous, participant, judge A, judge B, unassigned judge, organizer).
3. **Route Coverage Alarm:** `tests/test_auth_policy.py` inspects the live Django URL resolver and asserts that **zero** undeclared routes exist. A regression test (`test_coverage_alarm_fails_on_undeclared_route`) exercises a synthetic URLconf with an undeclared route to prove that the alarm fails if any un-quarantined endpoint is introduced.
4. **Target-Event Scoping:** An adversarial review identified that mutations could leak across events if checked against `current_event()`. Every mutation now explicitly verifies membership in the **target event being edited**.

---

## 8. Cryptographic Auditability

Rubric records all sensitive state transitions (ballot submissions, rubric changes, duplicate flags, event settings, and organizer overrides) in a cryptographic append-only ledger:

```mermaid
flowchart LR
    E1["Entry 1 (Genesis)<br/>prev_hash: 000...000<br/>hash: e3b0c44..."] --> E2["Entry 2<br/>prev_hash: e3b0c44...<br/>hash: 8f4b2a1..."]
    E2 --> E3["Entry 3<br/>prev_hash: 8f4b2a1...<br/>hash: 2c7d9e0..."]
```

### Audit Properties:
- **Canonical Serialization:** Entries store `seq`, `prev_hash`, UTC `created_at`, `actor`, `action`, `target`, and `payload`. Entries are hashed via SHA-256 over compact, sorted-key JSON bytes.
- **Concurrency Locking:** Sequence allocation is serialized under a PostgreSQL row lock and advisory lock (`SELECT FOR UPDATE`), preventing chain forks.
- **Database-Level Immutability:** On PostgreSQL, database triggers strictly abort any `UPDATE`, `DELETE`, or `TRUNCATE` operations on the `audit_auditlogentry` table:
  ```sql
  CREATE OR REPLACE FUNCTION audit_immutable_trigger() RETURNS trigger AS $$
  BEGIN
      RAISE EXCEPTION 'AuditLogEntry rows are immutable and cannot be updated or deleted';
  END;
  $$ LANGUAGE plpgsql;
  ```
- **Offline Independent Verification:** An organizer can download the full ledger (`/api/v1/organizer/audit-log/verify?download=1`) and verify the chain using a standalone standard-library script:
  ```bash
  python scripts/verify_audit_chain.py audit_export.json
  # audit chain valid; head_hash=8f4b2a1...
  ```

> [!WARNING]
> **Trust Boundary:** The audit log is *tamper-evident*, not cryptographic proof against a database superuser who can drop triggers and rewrite database storage.

---

## 9. Public Voting (Tier T3)

Public voting enables community voting alongside official judging. Voting is configured per event by the organizer:
- **Access Modes:**
  - **`OPEN`** (Default): Anyone with the link can vote. The voter is identified by a keyed HMAC of their IP address (`REMOTE_ADDR`).
  - **`AUTH`**: Voters must register and log in. The voter is identified by a keyed HMAC of their user account.
- **Vote Budgets:** Organizers can enforce an integer budget $N$ (`votes_per_voter`). Voters can withdraw a vote while the window is open to recover budget.
- **Secret Ballot:** Votes are recorded under pseudonyms: $\text{HMAC}(\text{SECRET\_KEY}, \text{event\_seed} \parallel \text{identity})$. No account IDs or raw IPs are stored on vote rows or in audit entries.
- **Deterministic Shuffling:** Projects on the public ballot are ordered by an HMAC of the project ID and the voter's pseudonym, eliminating position bias without allowing voters to refresh for favorable positioning.
- **Gated Results:** Results remain strictly inaccessible to non-organizers until the organizer explicitly closes the voting window.

### What It Stops
- **Double Voting:** Database unique constraint on `(event, project, mode, voter_pseudonym)`.
- **Budget Exploits:** Database transactions are serialized per event (`SELECT FOR UPDATE`), preventing parallel race conditions.
- **Early Tally Leakage:** Result views and API endpoints reject non-organizers with HTTP 200 (hidden template) or HTTP 403 before closing.
- **Ineligible Project Voting:** Drafts, superseded duplicates (`prj_07`), and cross-event projects cannot receive votes or comments.
- **Comment Abuse:** Comments require registration, are rate-limited, and feature organizer flag-and-hide moderation.
- **Brute Force & Account Spam:** Authentication (login/register) is rate-limited via a database-backed sliding window (10 attempts / 5 minutes per HMAC-hashed IP).

### What It Does Not Stop
- **OPEN Mode IP Rotation:** In `OPEN` mode, an attacker using multiple IP addresses (VPNs/proxies) receives multiple ballots.
- **OPEN Mode NAT Collisions:** Users on a shared network (such as university Wi-Fi or Docker gateway) share a single IP and budget. *Authenticated mode should be used when voting integrity matters.*
- **Open Registration Farming:** In `AUTH` mode, registration is open; determined attackers can create accounts (slowed, but not halted, by the rate limiter).
- **Email-Gated Mode is Not Available:** Email-gated magic links are deliberately omitted to honor the strict offline runtime requirement.

---

## 10. Real Fixture Data & Deliberate Edge Cases

The fixture dataset (`fixtures.json`, event `evt_01`) imports:
- **41 Projects**
- **40 Teams**
- **30 Judges**
- **8 Tracks**
- **126 Score Records**

The dataset includes deliberate real-world testing anomalies:

### 1. Duplicate Submission (`prj_07` vs `prj_41`)
Team `tm_07` submitted "Dry Harbour" twice: `prj_07` at 04:29 and `prj_41` at 17:57 (3 minutes before the deadline). Rubric's policy treats near-deadline submissions as intentional updates:
- `prj_41` is designated **canonical** (Raw Mean 3.8333, Normalized 3.7912, Rank 8).
- `prj_07` is flagged `is_duplicate_of = prj_41`, excluded from rankings, ballots, and voting, but preserved for auditability.

### 2. Constant Criterion Scorer (`jdg_07`)
`jdg_07` scored 4 in all criteria across all 3 assignments (`prj_09`, `prj_17`, `prj_19`). Raw variance is 0.0. The empirical-Bayes formula shrinks the variance to $\tilde{s}_j^2 = 0.2246$, assigning a non-zero, standardized score contribution of $z = 0.5115$ to each project without dividing by zero.

### 3. Constant Weighted Ballot Scorer (`jdg_19`)
`jdg_19` scored four projects in the fixture: `prj_03` (3, 5, 3), `prj_07` (2, 3, 2), `prj_24` (3, 4, 4), and `prj_41` (5, 4, 2). When the duplicate submission `prj_07` is excluded, its three counted ballots each average exactly $11/3 \approx 3.6667$ under equal weights. The normalization engine correctly flags `jdg_19` as constant at the **weighted-ballot-value level**, even though its individual criterion scores vary.

### 4. Thin Review Projects
Eight projects received only two reviews instead of the target three:
`prj_10`, `prj_15`, `prj_18`, `prj_19`, `prj_24`, `prj_29`, `prj_39`, `prj_40`.

### 5. Compounding Edge Case (`prj_19`)
`prj_19` compounded both anomalies: it received only two reviews, and one came from constant judge `jdg_07`. Rather than smoothing this over, the dashboard flags both conditions (`thin_batch` + `constant_judge`).

---

## 11. Verification & Test Parity

Rubric enforces rigorous automated and offline verification:

### Test Suite Execution
Tests run against both SQLite (fast development) and local PostgreSQL (concurrency & trigger parity):

```bash
# Full test suite against PostgreSQL
python src/manage.py test tests --settings=rubric.settings_test
```

#### Actual Observed Test Results:
- **SQLite Test Suite:** Ran **270 tests** in 61.4s, **269 passed, 1 skipped** (PostgreSQL-specific trigger flush), **0 failures, 0 errors**.
- **PostgreSQL Test Suite:** Ran **270 tests** in 137.9s, **270 passed, 0 skipped, 0 failures, 0 errors**.
- **Official Acceptance Checker:** **7/7 PASS** (`claimed nothing, verified T1 T2`).

### Automated vs. Human Verification

| Feature / Invariant | Verified By | Nature of Proof |
|---|---|---|
| **T1: Public gallery & submission rules** | `run.py` & Django Tests | Automated HTTP assertions |
| **T2: Judge score & peer isolation** | `run.py` & Django Tests | Automated HTTP role checks |
| **T2: CSV Export** | `run.py` & Django Tests | Header & MIME type validation |
| **T2: Normalization mathematics** | `tests/test_docs_consistency.py` | Exact float & string matching |
| **Route Authorization Matrix** | `tests/test_auth_policy.py` | Full URLconf traversal vs. YAML |
| **No Dangling Planning References** | `tests/test_no_dangling_refs.py` | Static code & markdown scanner |
| **Complete Offline Network Isolation** | CI `offline-check` job | Container egress blocked by iptables |
| **T3: Public Voting & Ballot Shuffling** | `tests/test_g6_step*.py` + Human Review | Concurrency test & manual walkthrough |

---

## 12. Submission Acceptance (`.dogfood.toml`)

Rubric ships with `.dogfood.toml` configured for the official DogFood 2026 checker:

```toml
[portal]
base_url = "http://localhost:8080"

[auth]
organizer = "Authorization: Bearer rubric_seed_organizer_tok_9f8e7d6c5b4a"
judge_a = "Authorization: Bearer rubric_seed_judge_a_tok_1a2b3c4d5e6f"
judge_b = "Authorization: Bearer rubric_seed_judge_b_tok_7a8b9c0d1e2f"
participant = "Authorization: Bearer rubric_seed_participant_tok_3f4e5d6c7b8a"

[routes]
gallery = "/projects"
submit = "/projects/new"
judge_scores = "/api/judge/scores"
peer_scores = "/api/judge/scores?judge=jdg_07"
csv_export = "/api/export.csv"

[tiers]
claimed = []
pitch = "Rubric delivers an auditable hackathon evaluation portal featuring cryptographic append-only audit logging, empirical-Bayes shrinkage normalization, and provable judge score isolation."
```

*Sequential Gating:* The checker evaluates sequentially ($T1 \rightarrow T2$). A failure in any T1 assertion immediately prevents credit for T2.

---

## 13. Repository Layout

```text
Rubric/
├── .github/workflows/ci.yml       # CI pipeline (clean-room, test-postgres, static-scan, offline-check)
├── Dockerfile                     # Multi-stage build with pre-compiled wheels & static assets
├── docker-compose.yml             # Web + PostgreSQL 16 composition
├── entrypoint.sh                  # Migration, fixture seeding, and gunicorn startup
├── fixtures.json                  # DogFood 2026 official fixture dataset
├── run.py                         # Official acceptance checker
├── .dogfood.toml                  # Acceptance checker configuration
├── requirements.txt               # Pinned dependencies (Django 5.2, psycopg3, numpy, whitenoise)
├── ARCHITECTURE.md                # System design & layering documentation
├── DATA-MODEL.md                  # Schema definitions & database constraints
├── JUDGING.md                     # Judging integrity, normalization proofs, & threat models
├── DECISIONS.md                   # 25 numbered Architecture Decision Records (ADRs)
├── scripts/
│   ├── check_no_external_assets.py# Static scanner asserting zero external CDNs/fonts
│   └── verify_audit_chain.py      # Standalone standard-library audit verifier
├── tests/                         # Full test suite (270 unit, integration, and policy tests)
└── src/                           # Django project root
    ├── accounts/                  # Auth, tokens, rate limiting, and actors
    ├── events/                    # Event lifecycle, tracks, prizes, and current event
    ├── teams/                     # Team creation and join codes
    ├── submissions/               # Submissions, links, and duplicate handling
    ├── judging/                   # Rubric configuration, ballots, and scoring views
    ├── voting/                    # Secret voting, budgets, and comment moderation
    ├── audit/                     # Cryptographic append-only hash chain & triggers
    ├── api/                       # JSON & CSV endpoints matching .dogfood.toml
    ├── services/                  # Business logic boundary
    ├── static/                    # Custom CSS & vendored HTMX (no build tools)
    └── templates/                 # Server-rendered HTML templates
```

---

## 14. Running Your Own Event

To run an event using Rubric:

1. **Bootstrap Site Administrator:**
   ```bash
   python src/manage.py create_organizer --email admin@example.com --password "SecurePass123" --name "Lead Organizer"
   ```
2. **Create and Activate Event:**
   - Log in at `/login` and navigate to `/organizer/events`.
   - Create the event with submission and voting windows, tracks, and prizes.
   - Click **Make Current** to route portal traffic to your event.
3. **Invite Judges:**
   - Go to `/organizer/judges`.
   - Add judges by email and track assignments; copy their single-use invitation links (`/invite/judge/<token>`).
4. **Configure Rubric:**
   - Go to `/organizer/rubric`.
   - Define scoring criteria and weights.
5. **Collect Submissions:**
   - Participants register, create teams (`/teams/new`), and submit repository and demo URLs (`/projects/new`).
6. **Assign Judges & Monitor Health:**
   - Navigate to `/organizer/assignments`.
   - Run balanced judge assignment and verify graph connectivity (Fiedler value).
7. **Normalize Scores & Review Calibration:**
   - View live judge progress at `/organizer/progress`.
   - Review empirical-Bayes calibration and constant-judge flags at `/organizer/normalization`.
8. **Open Public Voting (Optional):**
   - Click **Open Voting Now** on `/organizer/events/<id>/dates`.
   - Share `/vote/<event-slug>` with attendees.
9. **Export Data:**
   - Download the final CSV results at `/api/export.csv`.
   - Export and verify the immutable audit trail at `/organizer/audit-log`.

---

## 15. Honest Limitations

- **T4 is Incomplete:** Webhooks, certificates, and OpenAPI schemas are not implemented.
- **Single Active Event:** The portal serves one "current" event at a time. Concurrent multi-tenancy is not supported.
- **Voting Modes:** Supports `OPEN` (IP-based) and `AUTH` (account-based). Email-gated magic links are omitted to maintain offline isolation.
- **Audit Trust Boundary:** Immutability is enforced against application users and PostgreSQL write queries via triggers. A database superuser can modify underlying storage.
- **Production Demo Flag:** Development builds print demo tokens. Production deployments must set `RUBRIC_SEED_DEMO_LOGINS=false`.
- **Database Concurrency:** SQLite in-memory locks do not provide cross-process serialization. PostgreSQL is mandatory for production deployments.

---

## 16. Documentation Map

| Document | Purpose |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Technical stack, layer boundaries, and request lifecycle. |
| [`DATA-MODEL.md`](DATA-MODEL.md) | Schema design, foreign key relationships, and integrity constraints. |
| [`JUDGING.md`](JUDGING.md) | Statistical proofs, normalization formulas, and threat models. |
| [`DECISIONS.md`](DECISIONS.md) | 25 historical Architecture Decision Records (ADRs). |
| [`scripts/verify_audit_chain.py`](scripts/verify_audit_chain.py) | Standalone audit chain verifier (standard library only). |

---

## 17. Demo

- **Video Demonstration:** [▶ Demo Video (Placeholder)](https://example.com/replace-with-demo-video)
- **Slide Deck:** [📊 Slide Deck (Placeholder)](https://example.com/replace-with-slide-deck)

---

## 18. Team & License

- **Team:** Team AM
- **Event:** DogFood 2026
- **License:** [Apache-2.0](LICENSE)
- **Source Code:** [https://github.com/Dev-Am12/Rubric](https://github.com/Dev-Am12/Rubric)