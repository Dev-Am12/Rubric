#!/usr/bin/env python3
"""Reject external network resources referenced by project templates or CSS."""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


CSS_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE | re.DOTALL)
CSS_IMPORT = re.compile(
    r"@import\s+(?:url\(\s*)?(['\"]?)(.*?)\1\s*\)?",
    re.IGNORECASE | re.DOTALL,
)


def is_external(value: str) -> bool:
    value = value.strip().strip("\"'")
    if not value or value.startswith(("#", "{{", "{%", "data:")):
        return False
    parsed = urlsplit(value)
    return parsed.scheme.lower() in {"http", "https"} or value.startswith("//")


class TemplateScanner(HTMLParser):
    def __init__(self, path: Path, text: str):
        super().__init__(convert_charrefs=True)
        self.path = path
        self.text = text
        self.findings: list[str] = []

    def handle_starttag(self, tag, attrs):
        line, _ = self.getpos()
        for name, value in attrs:
            if name and name.lower() in {"src", "href"} and value and is_external(value):
                self.findings.append(f"{self.path}:{line}: external {name}={value!r}")
            if name and name.lower() == "style" and value:
                self.scan_css(value, line)

    def handle_data(self, data):
        # Inline style blocks are CSS resource declarations too.
        if self.get_starttag_text() and self.get_starttag_text().lower().startswith("<style"):
            self.scan_css(data, self.getpos()[0])

    def scan_css(self, css: str, line: int):
        for pattern, kind in ((CSS_URL, "url()"), (CSS_IMPORT, "@import")):
            for match in pattern.finditer(css):
                resource = match.group(2).strip()
                if is_external(resource):
                    offset_line = line + css.count("\n", 0, match.start())
                    self.findings.append(
                        f"{self.path}:{offset_line}: external CSS {kind} {resource!r}"
                    )


def check_template(path: Path) -> list[str]:
    scanner = TemplateScanner(path, path.read_text(encoding="utf-8"))
    scanner.feed(scanner.text)
    return scanner.findings


def check_css(path: Path) -> list[str]:
    css = path.read_text(encoding="utf-8")
    findings = []
    for pattern, kind in ((CSS_URL, "url()"), (CSS_IMPORT, "@import")):
        for match in pattern.finditer(css):
            resource = match.group(2).strip()
            if is_external(resource):
                line = css.count("\n", 0, match.start()) + 1
                findings.append(f"{path}:{line}: external CSS {kind} {resource!r}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--templates", type=Path, default=Path("src/templates"))
    parser.add_argument("--static", type=Path, default=Path("src/static"))
    args = parser.parse_args()

    files = sorted(args.templates.rglob("*.html")) + sorted(args.static.rglob("*.css"))
    findings = []
    for path in files:
        findings.extend(check_template(path) if path.suffix == ".html" else check_css(path))
    if findings:
        print("External resource references found:", file=sys.stderr)
        print("\n".join(findings), file=sys.stderr)
        return 1
    print(f"Scanned {len(files)} template/CSS files; no external resources found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
