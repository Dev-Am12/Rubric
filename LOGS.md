# LOGS.md — Mechanical implementation record

## 2026-09-28 — G4 Step 3: Organizer dashboard and real CSV export

- Built organizer dashboard screen (`/organizer`) per UX.md §3 displaying live progress (33/41 projects meeting target reviews), under-coverage breakdown across tracks, graph health status (1 connected component spanning 30/30 judges with Fiedler λ₂ ≈ 0.0875), and integrity flags (constant-score judge `jdg_07`, thin review count projects with `prj_19` compound flag, and duplicate submission `prj_07` superseded by `prj_41` with one-click restore).
- Implemented `/organizer/assignments`: supports triggering additive runs via `services.assignment.run()`, displays latest connectivity report, and lists historical `AssignmentRun` records.
- Implemented `/organizer/normalization`: supports triggering normalization runs via `services.normalization.run()`, renders the Normalization Proof table with rank changes (Δ Rank), and supports downloading proof CSV.
- Closed G1/G3 placeholder gap on `/api/export.csv`: guarded endpoint to organizer-only access (anonymous returns 401, participant/judge return 403) and exports real per-project CSV rows containing `project_id,raw_mean,normalized_mean,rank,review_count,flags` with proper duplicate exclusion and flag tokens.
- Declared all three new organizer routes in `tests/authz_expectations.yaml`.
- Added 9 new tests in `tests/test_g4_step3.py` covering route access control, fixture fact parity, duplicate restoration, assignment/normalization triggers, and CSV export denial and data validation. Full test suite passing (139 tests).

## 2026-09-28 — G4 normalization audit and completion

- Added the normalization models, migration, deterministic shrinkage service, organizer read, normalized-score payload, and offline proof-artifact export.
- Added fixture and synthetic tests for T1–T9, including the corrected T2 equal-offset and leave-one-out score checks; all 119 tests passed in the final full-suite run.
- The expanded T6 check found that active duplicate `prj_07` still appeared in the public gallery. Filtered projects with `is_duplicate_of` set and added coverage that keeps `prj_41` visible while excluding `prj_07`.
- A fresh local SQLite-backed server passed every live `run.py` T1/T2 check. Temporary database and server log files were removed afterward.
- T6's automatic audit-log record and organizer reversal remain unimplemented: the repository has no `AuditLogEntry` model or duplicate-restoration action; SCHEMA.md assigns the audit log to G5.

## 2026-09-28 — G4 live assignment and graph health

- Added NumPy, `AssignmentRun`, its migration, and the additive per-track assignment service with seeded tie-breaking, eligibility and conflict checks, under-coverage reporting, graph-health reports, and genuine multi-track anchor injection.
- Added synthetic tests A1–A7 plus the explicit singleton-Fiedler F9 check, and fixture test A8. The fixture safety check snapshots all 126 completed assignments before and after a `k=2` live assignment run; it adds no rows and preserves the snapshot exactly.
