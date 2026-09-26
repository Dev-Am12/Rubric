# DogFood 2026 — UI/UX (backlog item 7)

**Rev 2 · 2026-09-25 · Status: design only, no code yet — §4 adds the owner's design philosophy (clean/simple/professional, color TBD at frontend-coding time)**
Server-rendered templates + HTMX (P-05) — every screen below is a Django view calling the same `services.*` functions as API.md's routes. Two screens get full wireframe-level detail because they're where Judging Integrity actually becomes visible to a human: the judge ballot (peer-isolation has to *feel* obviously correct) and the organizer dashboard (this is where the priority-#1 signature feature, graph health, lives). Everything else is a route map — real layout gets drawn once building starts.

---

## 1. Screen inventory (route → who sees it → what it shows)

| Route | Who | Purpose |
|---|---|---|
| `/` | public | Event landing: dates, tracks, prizes |
| `/projects` | public | Gallery, search/filter (D-13: submitted only) |
| `/projects/{id}` | public/owner/organizer | Project detail |
| `/accounts/register`, `/accounts/login` | anon | Real-user auth (API.md §3) |
| `/teams/new`, `/teams/{id}` | participant | Create/manage team, invite code |
| `/projects/new`, `/projects/{id}/edit` | participant (owner) | Submit/edit, draft-vs-submitted banner, deadline countdown |
| `/my/submissions` | participant | Own team's projects — this is the screen that demos duplicate-flagging live (D-11: `participant` persona = a `tm_07` member) |
| `/judge/queue` | judge | Assignment list: pending/completed, per-project link |
| `/judge/ballots/{assignment_id}` | judge (own assignment) | **The ballot screen — §2 below** |
| `/organizer` | organizer | **Dashboard home — §3 below** |
| `/organizer/assignments` | organizer | Trigger a run, view `AssignmentRun` history + connectivity report |
| `/organizer/normalization` | organizer | Trigger a run, the raw/normalized/rank-change proof table |
| `/organizer/duplicates` | organizer | Flagged duplicates, one-click restore (D-02) |
| `/organizer/audit-log` | organizer | Hash-chain viewer + "verify" button/download |
| `/organizer/exports` | organizer | CSV export links per stage |
| `/vote/{event}` | mode-dependent | T3 ballot, per-voter-stable order (V-03) |
| `/results/{event}` | gated per V-02 | Tally, hidden until window closes for non-organizers |

---

## 2. The judge ballot screen (highest-stakes screen in the product)

Two-pane layout, per RESEARCH §7.9's ergonomics research, made concrete:

```
┌─────────────────────────────┬──────────────────────────────┐
│  LEFT: submission material   │  RIGHT: rubric                │
│  (fixed, doesn't scroll away)│  (scrolls independently)      │
│                               │                                │
│  Title, summary, description │  Functionality  [1 2 3 4 5]   │
│  repo/demo/live links         │  Quality        [1 2 3 4 5]   │
│  tech tags, track              │  Innovation     [1 2 3 4 5]   │
│                               │  (each anchor has a 1-line    │
│  [progress: 3 of 5 assigned] │   behavioral description,     │
│                               │   NORMALIZATION.md's method)  │
│                               │                                │
│                               │  Comment: [_____________]     │
│                               │  (blank is fine — ~40% of the │
│                               │   real fixture's are empty)   │
│                               │                                │
│                               │  [Submit & next →]            │
└─────────────────────────────┴──────────────────────────────┘
```
- Keyboard: `j`/`k` moves between assigned projects in the queue; `1`–`5` scores the currently-focused criterion; `Cmd/Ctrl+Enter` submits and advances.
- Autosave: `hx-trigger="change, keyup delay:1s"` on each score input, posting a partial save so a closed tab never loses in-progress work — a ballot is only "complete" (and counted) once explicitly submitted, but a draft persists.
- **There is deliberately no UI element anywhere on this screen, or reachable from it, that can show another judge's scores.** Not hidden with CSS — the underlying `GET /api/judge/scores` call this page's own "my other assignments" widget uses is the *same* `services.judging.get_scores(actor)` call the checker's `peer_scores` probe hits (API.md), so there is structurally nothing extra to leak even if a future page redesign added a careless link.

---

## 3. The organizer dashboard (where the differentiator lives)

```
┌───────────────────────────────────────────────────────────┐
│  Progress: ████████░░  32/41 projects have ≥2 reviews       │
│  Under-coverage: 2 projects short (Track: Health) ⚠         │
├───────────────────────────────────────────────────────────┤
│  Graph health (priority #1 signature feature)                │
│  ● 1 connected component · 30/30 judges · Fiedler λ₂ = 0.41  │
│  [view connectivity graph →]                                 │
├───────────────────────────────────────────────────────────┤
│  Flags                                                        │
│  ⚠ jdg_07 scored 3/3 assignments identically                 │
│  ⚠ 8 projects have fewer than 3 reviews (incl. prj_19,       │
│    which is also affected by jdg_07 above)                   │
│  ⚠ 1 duplicate submission flagged (tm_07 — prj_07 superseded │
│    by prj_41) [restore]                                       │
├───────────────────────────────────────────────────────────┤
│  [Run assignment]  [Run normalization]  [Export CSV ▾]        │
└───────────────────────────────────────────────────────────┘
```
This single screen is deliberately where every real, named edge case (RESEARCH §2B) surfaces in one place — an organizer (or a judge evaluating the submission) sees, without digging, exactly the things JUDGING.md and the write-up talk about. Live data refresh via simple polling (`hx-trigger="every 10s"`) — no WebSocket/SSE, keeps the "no extra services" Adoptability stance (RESEARCH §7.6) intact.

---

## 4. Design philosophy (owner's direction, 2026-09-25)
Not the main focus of the 72 hours, but a real one — with a specific shape: **clean, simple, professional, quietly sophisticated. Not flashy, not heavy.** The uniqueness here is *usability*, not visual flourish — every screen optimizes for easy reading, easy finding, and zero friction, and gets its "polish" from clarity and restraint rather than decoration. Concretely:
- Generous whitespace, a clear type hierarchy (one heading scale, one body size, used consistently), no more than one accent color doing any work at a time.
- No animation beyond what a state change genuinely needs to communicate (an autosave confirming, a row appearing) — nothing decorative, nothing that exists to look impressive.
- Every screen answers "what is this, what can I do here, what just happened" at a glance — this is the same standard AUTHZ.md and NORMALIZATION.md are held to for correctness, applied to layout.
- This is itself a real differentiator (RESEARCH §7.0's point about convergence): a rushed 72-hour hackathon UI is usually visually noisy or inconsistent; a calm, well-organized one is memorable specifically because it's rare in this context, and it serves Adoptability and Code Quality directly ("a stranger can follow it," "a design decision worth stealing") rather than existing for its own sake.
- **Color scheme is deliberately not decided here** — the owner wants live options once frontend coding actually starts, not a pre-baked palette. §4a below stays structural (tokens as a *mechanism*, not specific colors) until then.

## 4a. Design tokens (mechanism only — colors chosen when frontend coding starts, per above)
CSS custom properties for color/spacing/type scale, hand-written, vendored locally (P-05, no CDN). A light/dark pair from the start (cheap, and the publishing/authoring rules elsewhere in this workspace already require it for artifacts — worth the same discipline here even though this isn't a published artifact, since "adoptable" software should be usable at 3am). The *palette itself* is an open choice — Claude presents a short set of concrete options at that point, not before, per the owner's explicit preference.

## 5. Open items for G6/G7
- Whether the connectivity graph (`[view connectivity graph →]`) is an actual force-directed visual or a text/table summary — text/table is the safe default (cheap, always correct); a real force-directed SVG is the natural next step if G4/G5 leave slack, consistent with the priority order in DL-019.
- Comment UI placement (inline on project detail vs. a separate thread view) — inline, simplest, revisit only if it crowds the page once real content is in it.
