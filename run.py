#!/usr/bin/env python3
"""DOGFOOD 2026 acceptance checker.

Usage:  python3 run.py .dogfood.toml > acceptance-report.txt

Any Python 3. Standard library only, nothing to install.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

try:
    import tomllib  # Python 3.11 and newer
except ModuleNotFoundError:
    tomllib = None


def parse_toml(text):
    """Enough TOML for .dogfood.toml, so older Pythons work too.

    Handles [section] headers, key = "string", and key = ["a", "b"].
    """
    data, section = {}, None
    for raw in text.splitlines():
        line = raw.split("#")[0].strip()
        if not line:
            continue
        head = re.fullmatch(r"\[([A-Za-z0-9_.]+)\]", line)
        if head:
            section = data.setdefault(head.group(1), {})
            continue
        key, sep, value = line.partition("=")
        if not sep or section is None:
            continue
        key, value = key.strip(), value.strip()
        if value.startswith("["):
            items = re.findall(r'"([^"]*)"', value)
            section[key] = items
        else:
            section[key] = value.strip().strip('"').strip("'")
    return data


def load_config(path):
    if tomllib:
        with open(path, "rb") as f:
            return tomllib.load(f)
    with open(path, encoding="utf-8") as f:
        return parse_toml(f.read())

TIERS = ["T1", "T2", "T3", "T4"]
TIMEOUT = 10


def request(url, header=None, method="GET", body=None):
    """Return (status, text). Never raises on an HTTP error status."""
    req = urllib.request.Request(url, method=method)
    if header:
        name, _, value = header.partition(":")
        req.add_header(name.strip(), value.strip())
    if body is not None:
        req.data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


class Check:
    """One assertion. Collects its own failure detail as it runs."""

    def __init__(self, tier, label):
        self.tier = tier
        self.label = label
        self.ok = False
        self.detail = []

    def note(self, line):
        self.detail.append(line)


def build_checks(cfg, fixture):
    base = cfg["portal"]["base_url"].rstrip("/")
    auth = cfg.get("auth", {})
    routes = cfg.get("routes", {})

    def url(key, suffix=""):
        return base + routes.get(key, "") + suffix

    checks = []

    # --- T1 -------------------------------------------------------------
    c = Check("T1", "gallery is public")
    status, body = request(url("gallery"))
    c.ok = status == 200
    if not c.ok:
        c.note(f"GET {url('gallery')}")
        c.note("no auth header")
        c.note(f"got {status or 'no response'}, wanted 200")
    gallery_body = body
    checks.append(c)

    c = Check("T1", "project from fixtures shown")
    titles = fixture_titles(fixture)
    haystack = gallery_body.lower()
    c.ok = any(t.lower() in haystack for t in titles)
    if not c.ok:
        c.note(f"GET {url('gallery')}")
        if titles:
            c.note("looked for any of these fixture project titles: "
                   + ", ".join(repr(t) for t in titles))
            c.note("none of them appeared in the response body")
            c.note("if your gallery paginates, make sure page one is what "
                   "this route returns")
        else:
            c.note("no fixture file was loaded, so there was nothing to look for")
    checks.append(c)

    c = Check("T1", "closed event refuses submissions")
    status, _ = request(
        url("submit"),
        header=auth.get("participant"),
        method="POST",
        body={"title": "dogfood-late-submission-probe", "summary": "probe"},
    )
    c.ok = 400 <= status < 500
    if not c.ok:
        c.note(f"POST {url('submit')}")
        c.note("sent as participant; the fixture event closed "
               f"{(fixture or {}).get('event', {}).get('submissions_close', 'in the past')}")
        c.note(f"got {status or 'no response'}, wanted 4xx")
    checks.append(c)

    # --- T2 -------------------------------------------------------------
    c = Check("T2", "judge sees own scores")
    status, _ = request(url("judge_scores"), header=auth.get("judge_a"))
    c.ok = status == 200
    if not c.ok:
        c.note(f"GET {url('judge_scores')}")
        c.note("sent as judge_a")
        c.note(f"got {status or 'no response'}, wanted 200")
    checks.append(c)

    c = Check("T2", "judge cannot see peer scores")
    probe = base + routes.get("peer_scores", routes.get("judge_scores", ""))
    status, _ = request(probe, header=auth.get("judge_b"))
    c.ok = status in (401, 403)
    if not c.ok:
        c.note(f"GET {probe}")
        c.note("sent as judge_b; this is the url that returns judge_a's scores")
        c.note(f"got {status or 'no response'}, wanted 401 or 403")
        if status == 200:
            c.note("the backend returned another judge's scores")
    checks.append(c)

    c = Check("T2", "participant blocked")
    status, _ = request(url("judge_scores"), header=auth.get("participant"))
    c.ok = status in (401, 403)
    if not c.ok:
        c.note(f"GET {url('judge_scores')}")
        c.note("sent as participant")
        c.note(f"got {status or 'no response'}, wanted 401 or 403")
    checks.append(c)

    c = Check("T2", "csv export works")
    status, body = request(url("csv_export"), header=auth.get("organizer"))
    first_line = body.splitlines()[0] if body.splitlines() else ""
    c.ok = status == 200 and "," in first_line
    if not c.ok:
        c.note(f"GET {url('csv_export')}")
        c.note("sent as organizer")
        if status != 200:
            c.note(f"got {status or 'no response'}, wanted 200")
        else:
            c.note("got 200 but the first line has no comma in it")
    checks.append(c)

    return checks


def fixture_titles(fixture, n=3):
    projects = (fixture or {}).get("projects") or []
    return [p.get("title", "") for p in projects[:n] if p.get("title")]


def load_fixture(explicit, config_path):
    """Look where a student would plausibly have put it."""
    here = os.path.dirname(os.path.abspath(__file__))
    beside_config = os.path.dirname(os.path.abspath(config_path))
    candidates = [explicit] if explicit else [
        "fixtures.json",
        os.path.join(here, "fixtures.json"),
        os.path.join(beside_config, "fixtures.json"),
        os.path.join(beside_config, "data", "fixtures.json"),
    ]
    for c in candidates:
        try:
            with open(c, "rb") as f:
                return json.load(f), c
        except (FileNotFoundError, NotADirectoryError):
            continue
    return None, None


def main():
    ap = argparse.ArgumentParser(description="DOGFOOD 2026 acceptance checker")
    ap.add_argument("config", help="path to .dogfood.toml")
    ap.add_argument("--fixtures", default=None,
                    help="path to fixtures.json (searched for if omitted)")
    args = ap.parse_args()

    cfg = load_config(args.config)

    fixture, fixture_path = load_fixture(args.fixtures, args.config)
    claimed = [t for t in cfg.get("tiers", {}).get("claimed", []) if t in TIERS]

    print("DOGFOOD 2026 acceptance report")
    print(f"portal: {cfg['portal']['base_url']}")
    print(f"claimed: {' '.join(claimed) or 'nothing'}")
    if fixture is None:
        print("note: fixtures.json was not found, so the fixture content "
              "check will fail. Put it next to run.py or pass its path.")
    else:
        print(f"fixtures: {fixture_path}")
    print()

    checks = build_checks(cfg, fixture)

    width = max(len(c.label) for c in checks) + 2
    for c in checks:
        dots = "." * (width - len(c.label))
        print(f"{c.tier}  {c.label} {dots} {'PASS' if c.ok else 'FAIL'}")
        for line in c.detail:
            print(f"       {line}")

    verified = [t for t in TIERS
                if any(c.tier == t for c in checks)
                and all(c.ok for c in checks if c.tier == t)]
    # a tier only counts if every tier below it also passed
    solid = []
    for t in TIERS:
        if t in verified:
            solid.append(t)
        else:
            break

    print()
    print(f"claimed {' '.join(claimed) or 'nothing'}, "
          f"verified {' '.join(solid) or 'nothing'}")

    overclaim = [t for t in claimed if t not in solid]
    if overclaim:
        print(f"note: claimed but not verified: {' '.join(overclaim)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
