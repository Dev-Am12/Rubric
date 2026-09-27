# DogFood 2026 — Normalization: Policies, Method, Tests (backlog item 3)

**Rev 2 · 2026-09-25 · Status: design only, no code yet — incorporates fixes from STRESS-TEST.md (F6, F13, F14)**
Playbook discipline followed here deliberately: **policies are written before we look at what they do to the real fixture's ranking.** Each policy below states a commitment; the method section implements it; the test section proves it holds — in that order, not the reverse.

---

## 1. Policies (D-01…D-05, stated as commitments — this is JUDGING.md's first draft)

**D-01 — Method choice.** We normalize raw scores using empirical-Bayes shrinkage of each judge's mean and spread toward the event-wide pooled mean and spread (RESEARCH §7.1's formulas), with shrinkage strength κ₀ = ν₀ = 4. This value is a deliberate choice, not a default left untouched: at 4, a judge with only 1–3 ratings (most of the panel, per the real load distribution in RESEARCH §2B) gets meaningfully pulled toward the pool, while a judge with 5+ ratings keeps most of their own signal. **The raw mean is always displayed alongside the normalized mean and rank — normalization never replaces the record, it annotates it.**

**D-02 — Duplicate submissions.** A project that appears to duplicate another from the same team (same team, same or near-identical title, submitted close in time — the real case: team `tm_07`'s `prj_07` at 04:29 and `prj_41` at 17:57, both "Dry Harbour," same track/summary/repo, 3 minutes before the deadline) is flagged by the importer. **The later submission becomes the team's active/canonical entry by default** — ordinary intent reads a near-deadline resubmission as a fix or finalization, not a second competing entry, and this prevents one team's content being double-counted in judging or the public gallery. The earlier entry is retained in full, visibly flagged, linked via `is_duplicate_of`, never deleted, and the flagging action is itself audit-logged (attributed to "duplicate-detection policy v1," not a silent system action) so an organizer can reverse it with one click if the match was wrong.

**D-03 — The constant-score judge.** A judge whose ratings show zero variance (the real case: `jdg_07`, who scored all 3 of their assignments — `prj_09`, `prj_17`, `prj_19` — as `functionality=4, quality=4, innovation=4`, no exception) still tells us their *level* but nothing about *relative* quality. Under the specified shrinkage formula, their normalized z-score is a fixed, non-differentiating offset across every project they touched; it need not be absolutely zero. Their raw scores remain fully on record, and the organizer dashboard flags this judge explicitly (`⚠ scored N/N assignments identically`); the system never silently drops or excludes a judge — that stays a human, audit-logged decision.

**D-04 — Thin review batches.** A project reviewed by fewer judges than the assignment target (the real case: 8 of 41 projects, including `prj_19`, got only 2 reviews instead of the modal 3 — full list: `prj_10, prj_15, prj_18, prj_19, prj_24, prj_29, prj_39, prj_40`) carries visibly less evidence than a fully-reviewed one, and its review count is shown everywhere it's ranked (gallery, dashboard, CSV export) — never silently presented as equally trustworthy as a 5-review project's score. **`prj_19` is the compounding case**: it is simultaneously thin-batch *and* one of `jdg_07`'s constantly-scored projects, meaning its only genuine relative signal comes from a single judge (`jdg_29`). Both flags surface together on the dashboard rather than canceling out into one innocuous-looking number — this is deliberately named here, before we've run anything, so its later appearance in JUDGING.md and the write-up is a predicted finding, not a discovered surprise.

**D-05 — Disconnected judge–project graphs.** Cross-judge calibration is only meaningful within a connected component of the judge–project graph (comparing a judge who only reviewed Track A against one who only reviewed Track B, with no shared project, has no basis). Every normalization run computes and reports component count and the Fiedler value; if more than one component exists, we normalize within each component separately and refuse a single cross-component ranking without an explicit organizer acknowledgment. **On the real fixture this is moot** — verified in RESEARCH §2B as one connected component spanning all 30 judges — but the code path is exercised by a synthetic disconnected test regardless, because an assignment *we* generate live (T3/a future event) is not guaranteed to be as well-connected as the given data.

---

## 2. Method

### 2.1 The formula (from RESEARCH §7.1, restated with the chosen parameters)
This is a pragmatic shrinkage estimator **inspired by** empirical-Bayes methods, not a full hierarchical Bayesian model with a derived posterior — worth stating plainly in JUDGING.md rather than implying more statistical rigor than is actually being claimed (fixed by the stress test, F13).

**Step 0, missing from the original draft (fixed by the stress test, F6): collapse each ballot to one number before any cross-judge normalization.** A `Ballot` has one `BallotScore` per `RubricCriterion`, and T2 explicitly requires "a weighted scoring rubric the organizer can configure" — that configuration has to enter the math somewhere, and it enters here, first:
```
y_ij = Σ(BallotScore.value × RubricCriterion.weight) / Σ(RubricCriterion.weight)
```
for judge *j*'s ballot on project *i*. Everything below operates on this already-criterion-weighted `y_ij`, never on a raw per-criterion value directly.

For judge *j* with n_j ratings, raw mean ȳ_j, raw variance s_j² (both computed over `y_ij`, not raw `BallotScore` values), and event-wide pooled mean μ₀ and variance σ₀²:

```
μ̃_j = (n_j·ȳ_j + 4·μ₀) / (n_j + 4)
s̃_j² = (n_j·s_j² + 4·σ₀²) / (n_j + 4)
z̃_ij = (y_ij − μ̃_j) / √s̃_j²
```
Project *i*'s normalized score is the plain equal-weighted mean of `z̃_ij` across its judges (not weighted by inverse variance), mapped back onto the original 1–5 scale for display (`normalized = μ₀ + z̃ · σ₀`, clipped to [1,5]) so organizers read a familiar number, not a raw z-score. **Each judge contributes equally to this project mean; contributions are not weighted by `1/s̃_j²`.**

**Rank sensitivity limitation.** Rank is an ordinal display statistic, so a small normalized-score change can move a project across several neighbors when the surrounding scores are tightly packed. This depends on the local score gaps in the field, not on which judge's ballots changed. In the fixture, `prj_09`'s nearest baseline neighbor was only 0.00194 points away and `prj_17`'s nearest was 0.01721 away, while the control `prj_13`/`prj_26` neighbors were about 0.04–0.05 points away. Rank movement therefore should be read alongside normalized-score changes and review counts; it is not by itself evidence of a normalization defect.

### 2.2 Pipeline (one `NormalizationRun` per computation, per SCHEMA.md §1.2)
0. Compute `y_ij` per ballot per §2.1's step 0 (the organizer's weighted rubric collapsed to one number).
1. Pull all `y_ij` values for the event, joined to `JudgeAssignment` for judge/project identity.
2. Exclude `Project` rows where `is_duplicate_of` is set and not organizer-restored (D-02).
3. Compute μ₀, σ₀² pooled across every included score.
4. Compute the judge co-review graph; find connected components; compute the Fiedler value per component (RESEARCH §7.3).
5. Per component: compute μ̃_j, s̃_j² per judge, then `z̃_ij` per score, then per-project normalized mean and rank.
6. Write one `NormalizedScore` row per project (raw_mean, normalized_mean, rank, judge_graph_component_id, judge_graph_fiedler_value); write the `NormalizationRun` metadata row (method_name="empirical_bayes_shrinkage_v1", parameters={"kappa0": 4, "nu0": 4}).
7. Flag: any judge with s_j² = 0 and n_j ≥ 2 → D-03 flag on that judge; any project with review count below the event's target → D-04 flag; any project with `is_duplicate_of` set → D-02 flag, excluded from ranking but visible. Persist project warnings in `NormalizationRun.parameters.project_flags`; `normalized_score_payload` exposes those flags and the review count with each `NormalizedScore` row.

### 2.3 Determinism
Step 3–6 must produce byte-identical output across repeated runs on the same input (playbook lesson, confirmed independently by three prior top-ranked projects we studied — RESEARCH's earlier playbook notes): iterate judges/projects in a stable sort order (by `external_id` or PK, never by dict/set iteration order), and avoid any floating-point operation whose result depends on summation order across an unordered collection.

---

## 3. Planted-truth test specs (to build once code exists — this is the spec, not the code)

| # | Test | Setup | Assertion |
|---|---|---|---|
| T1 | `test_shrinkage_beats_raw_on_synthetic_ground_truth` | Synthetic: 10 judges with known offsets (−1.5 to +1.5), 20 synthetic projects with known true quality, judges rate with offset + noise, **fixed random seed** (fixed by the stress test, F14 — otherwise flaky, undermining our own determinism principle) | Spearman correlation of *normalized* ranking vs. true quality ranking is higher than raw-mean ranking vs. true quality ranking |
| T2 | `test_jdg07_constant_offset_and_leave_one_out_effect` | Load the real `fixtures.json` | `jdg_07`'s z-score contribution is identical across `prj_09`/`prj_17`/`prj_19` (measured as 0.5115488667 in the fixture, not necessarily zero). For the non-thin `prj_09` and `prj_17`, leave-one-judge-out absolute normalized-mean changes stay within twice the largest absolute change for the comparable non-constant three-assignment control `jdg_06`; the factor-of-two bound is a conservative same-order-of-magnitude envelope for comparing different projects. `prj_19` is checked separately: removing `jdg_07` leaves one reviewer, an independent low-review-count factor that makes its larger score change non-comparable to a three-review control. Rank movement is deliberately not asserted because local score crowding makes rank sensitive to small score changes. |
| T3 | `test_constant_judge_no_div_by_zero` | Direct unit test: a judge with s_j² = 0, n_j = 3 | `s̃_j²` output is finite and strictly positive; no NaN/Inf anywhere downstream |
| T4 | `test_thin_batches_flagged_real_fixture` | Load real fixtures | All 8 known thin-batch project `external_id`s (`prj_10, 15, 18, 19, 24, 29, 39, 40`) carry `review_count=2` and a thin-batch flag in the API/dashboard payload and the CSV export |
| T5 | `test_prj19_compounding_flag` | Load real fixtures | `prj_19`'s payload carries **both** the thin-batch flag and a reference to the constant-judge flag on `jdg_07` — not silently merged into one generic warning |
| T6 | `test_duplicate_never_lost_default_canonical` | Load real fixtures | Both `prj_07` and `prj_41` exist as DB rows after import; `prj_41.is_duplicate_of` is null (it's the canonical one, being later) and `prj_07.is_duplicate_of == prj_41.id`; `prj_07` is excluded from ranking/gallery by default; an audit log entry exists recording the auto-flag; reversing it via the organizer action un-excludes `prj_07` and is itself logged |
| T7 | `test_disconnected_graph_synthetic` | Synthetic: two judge groups reviewing entirely disjoint project sets | Two components detected; each normalized independently; no single combined ranking is produced without an explicit override flag passed in |
| T8 | `test_deterministic_output` | Real fixtures, run twice | Byte-identical `NormalizedScore` output both times |
| T9 | `test_normalization_proof_artifact` | Real fixtures | The raw-vs-normalized-vs-rank-change table (the "Normalization Proof" deliverable, RESEARCH §7.0) can be generated as a static artifact from a `NormalizationRun` row with no server running — supports the "judges can reproduce this without a live server" standard from the playbook |

---

## 4. Open items for G4

- Exact display mapping from z-score back to the 1–5 scale for organizer-facing UI — current default `μ₀ + z̃·σ₀`, clipped; revisit once the judge console (backlog item 7) is drawn, since the visual context might suggest a cleaner presentation (e.g., percentile instead of a rescaled score).
- Whether `κ₀`/`ν₀` become organizer-configurable in the UI or stay a documented constant — leaning constant-with-documented-value for the submission (simpler, one less place to misconfigure), configurable is a T4-adjacent nice-to-have if time permits.
