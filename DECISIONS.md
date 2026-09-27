# DECISIONS.md — Rubric (hackathon submission/judging portal, DogFood 2026)

Every non-trivial design or engineering judgment call that shapes how Rubric
behaves, or how it should be read — the "why," not routine implementation
mechanics (those live in LOGS.md). Entries are never edited or renumbered
once written; a decision that changes later gets a new, later-numbered entry
that says so explicitly, so the history stays honest.

## Table of Contents

- [1. Authentication: a standalone token model, not Django sessions](#1-authentication-a-standalone-token-model-not-django-sessions)
- [2. One function decides who sees judging scores — for both required routes](#2-one-function-decides-who-sees-judging-scores--for-both-required-routes)
- [3. A deliberately broken route, kept on purpose, to prove our own enforcement works](#3-a-deliberately-broken-route-kept-on-purpose-to-prove-our-own-enforcement-works)
- [4. Duplicate submissions: the later entry is canonical, the earlier one is flagged, never deleted](#4-duplicate-submissions-the-later-entry-is-canonical-the-earlier-one-is-flagged-never-deleted)
- [5. Judges aren't excluded for suspicious scoring patterns — they're neutralized statistically and flagged](#5-judges-arent-excluded-for-suspicious-scoring-patterns--theyre-neutralized-statistically-and-flagged)
- [6. The one part of the checklist we can't do locally, said plainly rather than hidden](#6-the-one-part-of-the-checklist-we-cant-do-locally-said-plainly-rather-than-hidden)
- [7. The public-voting layer is built to be checked by a person, on purpose](#7-the-public-voting-layer-is-built-to-be-checked-by-a-person-on-purpose)
- [8. User accounts don't carry Django's admin baggage](#8-user-accounts-dont-carry-djangos-admin-baggage)
- [9. CSRF enforcement depends on how you authenticated, not a global toggle](#9-csrf-enforcement-depends-on-how-you-authenticated-not-a-global-toggle)
- [10. Judge score isolation uses the authenticated user identity](#10-judge-score-isolation-uses-the-authenticated-user-identity)

---

## 1. Authentication: a standalone token model, not Django sessions

**Decision:** Every identity in Rubric — the four required test accounts and every real signed-up user alike — authenticates via a single hashed bearer token, not Django's built-in cookie-session framework.

**Rationale:** The organizers' own acceptance checker attaches a raw header on every request and never "logs in" in the conventional sense. A session-cookie system would mean simulating a browser session just for four fixed identities — more moving parts than the problem needs, and a second code path alongside real users' actual logins. One token mechanism serves both, with no special-casing between "the checker's account" and "a real judge's account." The raw token is generated once, shown at boot, and hashed before storage — nobody with database access alone can recover it.

**In plain terms:** Everyone gets a plain access token instead of a login-and-cookie flow, checked the same way every time — including the automated checker's own test accounts. The token itself is never sitting in the database in a form someone could steal and reuse.

---

## 2. One function decides who sees judging scores — for both required routes

**Decision:** The two separately-named routes for reading judge scores resolve to the exact same URL, backed by exactly one service-layer function that checks the caller's identity before returning anything.

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

**Decision:** A judge whose scores show an unusual pattern (for example, scoring every project identically) is never removed from the dataset. Their raw scores stay fully visible; a statistical adjustment limits how much they can skew a project's *relative* ranking, and the pattern itself is shown as a visible flag, not fixed quietly. The same honesty applies to any project reviewed fewer times than planned, and to any pair of judges with no shared project to compare against — both are shown, not smoothed into one falsely clean number.

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
