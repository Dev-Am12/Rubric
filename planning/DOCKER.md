# DogFood 2026 — Docker & CI (backlog item 8)

**Rev 2 · 2026-09-25 · Status: design only, no code yet — §6 fully rewritten (F4): no local machine can run Docker at all**
This is the single highest-stakes piece of the whole submission: spec.md's own words, "if it does not come up on a laptop with the network off, we cannot adopt it, and adoption is the entire point." Everything here exists to make that literally true on a judge's unknown machine, not just on ours.

---

## 1. Repo placement
`run.py` and `fixtures.json` live at the **repo root**, alongside `.dogfood.toml` — this matches `run.py`'s own default search order exactly (RESEARCH §2.3: explicit path → `./fixtures.json` → next to `run.py` → next to the toml → `<toml-dir>/data/fixtures.json`), so a judge who just clones and runs `python3 run.py .dogfood.toml` from the repo root needs zero flags.

```
your-repo/
├── .dogfood.toml
├── run.py                  ← copied verbatim from the released spec, never modified
├── fixtures.json           ← copied verbatim from the released spec, never modified
├── acceptance-report.txt
├── docker-compose.yml
├── Dockerfile
├── entrypoint.sh
├── .dockerignore
├── .gitattributes          ← forces LF (RESEARCH playbook: Windows CRLF broke a shell entrypoint once)
├── README.md / ARCHITECTURE.md / DATA-MODEL.md / JUDGING.md / LICENSE
├── src/
└── tests/
```

## 2. `docker-compose.yml` (draft)
```yaml
services:
  db:
    image: postgres:16-alpine       # multi-arch: amd64 + arm64, judge's machine unknown
    environment:
      POSTGRES_DB: dogfood
      POSTGRES_USER: dogfood
      POSTGRES_PASSWORD: dogfood_dev_only   # explained loudly in README (playbook: alarming-looking secrets get explained, not hidden)
    volumes:
      - dbdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U dogfood"]
      interval: 2s
      timeout: 3s
      retries: 20

  web:
    build: .
    depends_on:
      db:
        condition: service_healthy   # never race Postgres's own startup
    ports:
      - "8080:8080"
    environment:
      DATABASE_URL: postgres://dogfood:dogfood_dev_only@db:5432/dogfood
      DJANGO_SECRET_KEY: dev-only-not-for-production   # explained loudly, not hidden
      DJANGO_DEBUG: "false"
      DJANGO_ALLOWED_HOSTS: "*"

volumes:
  dbdata:
```
No `nginx`, `redis`, or `celery` service (P-06) — fewer moving parts, fewer places for a judge's laptop to disagree with ours.

## 3. `Dockerfile` (draft — multi-stage, hermetic per RESEARCH §7.6)
```dockerfile
# ---- builder: network allowed here (A4 — build-time, not runtime) ----
FROM python:3.12-slim-bookworm AS builder
WORKDIR /wheels
COPY requirements.txt .
RUN pip wheel --wheel-dir=/wheels -r requirements.txt

# ---- runtime: no network needed from here on ----
FROM python:3.12-slim-bookworm
RUN useradd -m appuser
WORKDIR /app
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels
COPY src/ /app/src/
COPY run.py fixtures.json /app/          # so the container itself can also run the checker if needed
COPY entrypoint.sh /app/
RUN chmod +x /app/entrypoint.sh && chown -R appuser /app
USER appuser
EXPOSE 8080
ENTRYPOINT ["/app/entrypoint.sh"]
```
`requirements.txt` is pinned with hashes (`pip-compile --generate-hashes`) — `Django>=5.2.13` (DL-013, the CVE pin) among them.

## 4. `entrypoint.sh` (draft)
```sh
#!/bin/sh
set -eu
python manage.py migrate --noinput
python manage.py seed_fixtures --idempotent   # SCHEMA.md §2 — safe to re-run, upserts by external_id
python manage.py print_seed_credentials       # the "seeded. test logins: ..." convention, spec.md's own worked example
exec gunicorn dogfood.wsgi:application --bind 0.0.0.0:8080 --workers 3
```
Invoked via `sh`, not relying on the executable bit surviving a Windows checkout (playbook: this exact class of bug cost the most in a prior event).

## 5. CI (`.github/workflows/ci.yml`, draft) — the clean-room + egress-blocked verification (V1, V10)
```yaml
on: [push]
jobs:
  clean-room:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker compose up -d --build
      - run: |
          timeout 60 sh -c 'until docker compose exec -T web curl -sf http://localhost:8080/projects; do sleep 2; done'
      - run: python3 run.py .dogfood.toml > acceptance-report.txt
      - run: cat acceptance-report.txt
      - name: fail the build on any T1 FAIL          # V10 — the tier-gating rule, no exceptions
        run: '! grep -q "^T1.*FAIL" acceptance-report.txt'
      - uses: actions/upload-artifact@v4
        with: { name: acceptance-report, path: acceptance-report.txt }

  offline-check:
    runs-on: ubuntu-latest
    needs: clean-room
    steps:
      - uses: actions/checkout@v4
      - run: docker compose build          # network allowed here (A4)
      - run: |
          docker network create --internal offline-net
          docker compose up -d
          docker network disconnect bridge dogfood-web-1 || true
          docker network connect offline-net dogfood-web-1
      - run: python3 run.py .dogfood.toml > offline-report.txt
      - run: diff acceptance-report.txt offline-report.txt   # must be identical — proves runtime truly needs no network

  static-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: no external URLs in templates/static
        run: |
          ! grep -rE '(https?://|//cdn\.|unpkg\.com|cdnjs\.cloudflare\.com|fonts\.googleapis\.com)' src/templates/ src/static/ 2>/dev/null
```
The `offline-check` job is the actual, executable proof behind the "network off" requirement — not an assertion in README, a CI job that fails if it's untrue.

## 6. Environment strategy, revised 2026-09-25: no local machine can run Docker at all
This changes how we *develop and verify* everything above — not the compose file, Dockerfile, or CI workflow themselves, which were never designed assuming local Docker, only previously *verified* that way against a Windows machine that's no longer available.

**1. Native PostgreSQL for local dev, not Docker — confirmed done (Windows, pgAdmin 4).** This gives a fast local dev loop (`python manage.py runserver` against a real local Postgres) with full parity to what actually ships — same engine, same `pgcrypto` availability for the audit-log hash chain — and removes almost all "works locally, fails in the container" risk that developing against SQLite or nothing at all would otherwise create.

**2. The repo goes public from kickoff (T-0), not just at submission.** Spec.md only requires public "at submission," but a public repo gets **unlimited GitHub Actions minutes** versus a capped free allowance on a private one — and Actions is about to carry far more weight than originally planned.

**3. GitHub Actions becomes the primary, frequent Docker-verification loop**, not an occasional check. The clean-room and offline-check jobs in §5 are unchanged; what changes is cadence — push at the end of every meaningful step, not just at gate boundaries, since a green Actions run is now the *only* proof the containerized app actually works.

**4. A free, on-demand interactive fallback**, for when Actions logs alone don't explain a failure: a manually-triggered job step using an SSH-into-the-runner action (e.g. `mxschmitt/action-tmate`) opens a real interactive shell on a genuine Docker-capable Linux host, at zero cost beyond Actions minutes already free on a public repo. This substitutes for "poke around inside the container" without touching Codespaces at all.
```yaml
  debug-shell:                      # manual trigger only, never runs automatically
    if: github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker compose up -d --build
      - uses: mxschmitt/action-tmate@v3    # opens an SSH session into this runner
```

**5. GitHub Codespaces, budgeted deliberately** (120 free core-hours/month): reserved for two sessions, not continuous use — (a) one early session right after the skeleton exists, specifically to prove compose/entrypoint/healthchecks boot on a real Docker host *before* building the rest of the app on top of an unverified skeleton, and (b) the final pre-freeze end-to-end dry run. Estimated total need: 5–7 hours of actual session time, well inside the free allowance, provided sessions are stopped when not in active use (Codespaces only counts hours while running).

**6. V9 (second-environment check) is redefined, not dropped.** A literal Windows-Docker-Desktop test is no longer possible — a real, honest gap, not fully replaceable. Two partial mitigations: every Actions run is already a fresh, ephemeral Linux VM (catches "only worked because of local leftover state," though not Windows-specific issues), and §2's compose file never bind-mounts source into the container — everything is `COPY`'d in at build time — which sidesteps the single most common Windows-Docker-Desktop friction point (bind-mount permission/performance bugs), even though it can't rule out something Windows-specific we haven't thought of. **README's honest-limitations section should say this plainly**: not tested on Windows directly; the design avoids the most common friction points, but that isn't a substitute for testing. This is exactly the kind of disclosure spec.md rewards, not just risk management.

---

## 7. Open items for G0
- Whether Postgres data needs to survive a `docker compose down` between judge runs — leaning yes (named volume, as drafted), since a judge re-running the checker without re-seeding should see the same state, not an empty DB.
- Exact gunicorn worker count (3 drafted) — revisit only if the judge console's polling (UX.md §3) turns out to need more concurrency; unlikely at this scale.
- ~~Open question for the owner: can PostgreSQL actually be installed natively (no Docker), and on what OS?~~ **Resolved 2026-09-26**: yes — Windows, with pgAdmin 4 already installed. The plan in §6 stands as designed: native local Postgres for fast dev iteration and full DB parity (including `pgcrypto` for the audit-log hash chain), Docker used purely for packaging and tested exclusively via cloud environments (Actions/Codespaces), never locally — exactly the split the owner independently confirmed understanding correctly.
