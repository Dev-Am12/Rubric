# DogFood 2026 — T3: Voting, Abuse Model, Threat Model (backlog item 5)

**Rev 2 · 2026-09-25 · Status: design only, no code yet — incorporates fixes from STRESS-TEST.md (F10, F11)**
Depends on SCHEMA.md (§1.3) and RESEARCH §7.4. **Governing constraint for this whole file (RESEARCH A14): `run.py` never checks T3 at all.** Every mechanism here has to be demonstrable by a human in under a minute — that's policy V-06 below, and it's the design principle that shapes this backlog item more than any other, because it's the only credit channel T3 has.

---

## 1. Voting policies (stated before implementation)

**V-01 — Vote uniqueness is enforced per access mode, with one uniform mechanism.** `Vote` carries `(event_id, project_id, mode, voter_fingerprint)` as a single compound unique constraint — no partial indexes needed, because `mode` is already part of the key and `voter_fingerprint` simply *means* something different per mode: open-link → salted hash of `(per-event rotating salt, ip, user_agent)`; email-gated → hash of the HMAC-verified email; authenticated → the user's id as a string. (Simpler than the partial-index approach in RESEARCH §7.4's first draft — same guarantee, one index instead of three.)

**V-02 — Results are gated at the query layer, on every request, not by an unlinked page.** No cached or pre-rendered public tally exists anywhere that could leak before the window closes; the same `services.voting.get_results(actor)` function is the only path to a tally, and it checks `actor.is_organizer or event.voting_closed` before returning anything. **Once closed, results are public to everyone — no separate toggle** (fixed by the stress test, F10: an earlier draft implied a configurable option here that was never actually specified anywhere).

**V-03 — Ballot order is per-voter deterministic, not globally random.** `ORDER BY hmac(project_id, event.voting_seed || voter_fingerprint)` — refreshing never re-rolls a favorable position for one voter, and different voters see genuinely different orders.

**V-04 — Rate limiting is server-side, mode-aware, and its own audit trail.** A sliding-window cap per fingerprint (default: 5 attempts/minute) defends the open-link mode specifically, since email-gated/authenticated modes are already capped by the one-vote-per-identity constraint itself. Every attempt — accepted or rejected, and why — is logged (§2.2), not just the successful ones.

**V-05 — Comments are flag-and-hide, never flag-and-delete.** Same principle as D-02: a flagged comment disappears from the public view but stays in the database and the organizer's view, permanently, for the same reason we never silently delete a duplicate submission.

**V-06 — Every anti-abuse mechanism must be demonstrable by a human in under a minute.** Because T3 has no automated credit path (A14), each mechanism gets both a visible organizer-facing indicator (a live "N blocked attempts" counter, not a log file someone has to go find) and a named beat in the demo-video storyboard (backlog item 9) — "watch me try to vote twice and get refused" rather than an assertion in a doc that a judge has to take on faith.

**V-07 — A flagged-duplicate project (D-02) is never votable.** `prj_07`, once superseded by `prj_41` on import, never appears as a ballot option — this ties T3 directly back to the normalization/import policy rather than treating it as a separate concern.

---

## 2. Schema refinement (updates SCHEMA.md §1.3)

A cleaner mechanism than the original sketch: instead of a separate `Vote` + `VoteRateLimit`, one append-only log (`VoteAttempt`) is the source of truth for *every* attempt, successful or not — it serves the rate-limit check, the audit trail, and the V-06 dashboard indicator all at once, and `Vote` becomes a small derived table written only on success (kept separate from the log for fast tallying, rather than filtering a growing log table on every result computation).

**VoteAttempt** (append-only)
| field | type | notes |
|---|---|---|
| id, event_id, project_id | | |
| mode | enum: OPEN / EMAIL / AUTH | |
| voter_fingerprint | text | see V-01 |
| outcome | enum: ACCEPTED / REJECTED_DUPLICATE / REJECTED_RATE_LIMIT / REJECTED_CLOSED | |
| created_at | timestamp | indexed with `(fingerprint, created_at)` for the sliding-window query |

**Vote** (written only alongside an ACCEPTED `VoteAttempt`, same transaction)
| field | type | notes |
|---|---|---|
| id, event_id, project_id, mode, voter_fingerprint | | |
| weight | numeric, default 1 | reserved for a future QV mode, off by default (RESEARCH §7.4's Sybil math is why QV stays restricted to AUTH mode if ever enabled) |
| attempt_id | FK → VoteAttempt | |
| created_at | timestamp | |
| **unique(event_id, project_id, mode, voter_fingerprint)** | | V-01, replaces the earlier partial-index sketch |

**Comment**
| field | type | notes |
|---|---|---|
| id, project_id, author_id (nullable), body, created_at | | |
| is_flagged | bool, default false | V-05 |

---

## 3. Threat model outline (the bonus category, built as core T3 work per §7.0 — "an answer to people trying to cheat it" is a literal T1/T3 line item, not extra credit)

Following the playbook's strongest write-up pattern: name what we stopped **and** what we did not, in the same document, with the same confidence.

### 3.1 Stopped
| Threat | Mechanism |
|---|---|
| Sybil voting via rapid repeat on one identity | V-01 uniqueness + V-04 rate limit |
| Duplicate voting per identity (any mode) | V-01's compound unique constraint |
| Ballot-order gaming via refresh | V-03's per-voter-deterministic order |
| Result peeking before the window closes | V-02's query-layer gate |
| Silent tampering with vote or score history | The hash-chained `AuditLogEntry` (RESEARCH §7.5) applies here identically |
| Unmoderated comment spam with no recourse | V-05 flag-and-hide |
| A superseded duplicate submission collecting votes | V-07 |

### 3.2 Explicitly NOT stopped (the honest gap — spec.md rewards this directly, and it's real differentiation per RESEARCH §7.0/PLAN §1.2)
- **Fingerprint rotation defeats open-link dedup.** An attacker using a VPN or rotating browser fingerprints can vote more than once in open-link mode — this is inherent to any identity-free voting mode on any platform, not a bug specific to us. The honest mitigation is *offering* email-gated or authenticated modes as the stronger options and saying so plainly, not claiming open-link is Sybil-proof.
- **Email-gated mode trusts that the organizer's participant/judge list wasn't itself compromised**, and verifies only "received and clicked a link at that address," not deeper identity proof — standard and proportionate for a hackathon vote, explicitly not claimed to be more than that.
- **Judge collusion is not technically preventable by any platform.** Our answer is *detectability*, not prevention: an anomalously tight, high-agreement pattern between two specific judges would be visible to an organizer via the disagreement-heatmap/rank-uncertainty features (priority #2/#3 signature features, DL-019) once built — we name this as a limitation with a partial, honest mitigation, not a solved problem.
- **Submission scraping of the public gallery is not defended against** beyond ordinary reasonable rate limits — the gallery is deliberately public per T1's own requirement, so we don't add anti-scraping measures that would work against that goal.

---

## 4. Planted-truth test specs

| # | Test | Assertion |
|---|---|---|
| V-T1 | `test_open_mode_duplicate_rejected` | Same fingerprint votes twice on the same project → second `VoteAttempt` is `REJECTED_DUPLICATE`; exactly one `Vote` row exists |
| V-T2 | `test_rate_limit_blocks_rapid_attempts` | The (default 6th) attempt within the window from one fingerprint is `REJECTED_RATE_LIMIT` |
| V-T3 | `test_results_hidden_during_window` | Tally request as participant/anon during an open window → 403; as organizer → 200; after close → 200 for everyone, no separate toggle |
| V-T4 | `test_ballot_order_stable_per_voter_varies_across_voters` | Same fingerprint requests the ballot twice → identical order; two different fingerprints → different order |
| V-T5 | `test_comment_flag_hides_not_deletes` | A flagged comment is absent from the public list endpoint but present in the DB and the organizer view |
| V-T6 | `test_superseded_duplicate_not_votable` | `prj_07` (flagged duplicate of `prj_41`, D-02) never appears in the T3 ballot for team `tm_07`'s track |
| V-T7 | `test_blocked_attempts_feed_dashboard_indicator` | A `REJECTED_*` attempt increments the organizer-visible counter for that project within the same request cycle (V-06) |

---

## 5. Open items for G6

- Default rate-limit threshold (5/minute proposed) — revisit once the judge/organizer UI is drawn, since the right number depends on how voting is actually presented (one ballot page vs. per-project buttons).
- Whether comment authorship is ever anonymous in open-link voting mode, or comments require at least email-gated identity — leaning: comments follow whatever mode the vote itself used, no separate policy, simplest to defend in JUDGING.md §6 (fixed by the stress test, F11 — there is no separate THREAT-MODEL.md file; DOCS-PLAN.md folded this into JUDGING.md specifically to avoid two files claiming the same things).
