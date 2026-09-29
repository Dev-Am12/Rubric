"""
Tests asserting zero dangling references to planning documents or policy codes.

planning/ is deleted at submission time. No code comments, templates, tests,
YAML, scripts, CI, root files, or DECISIONS.md may reference planning docs
(e.g., UX.md, NORMALIZATION.md, AUTHZ.md, SCHEMA.md, VOTING.md, API.md,
DOCKER.md, PLAN.md, LOGS.md, RESEARCH.md, STRESS-TEST.md, DL-0xx, or planning/).

Policy codes (D-01..D-05, A-01..A-07, V-01..V-07) stay ONLY where JUDGING.md
defines them.

JUDGING.md is on a documented PENDING_REWRITE allow-list as it is being
rewritten separately.
"""

import os
import re
from pathlib import Path
from django.test import SimpleTestCase


# Documented allow-list for files undergoing independent rewrite
PENDING_REWRITE = {
    'JUDGING.md',
}

# Directories to ignore during scanning
IGNORE_DIRS = {
    '.git',
    '.venv',
    '__pycache__',
    'planning',  # deleted at submission
    '.system_generated',
    'scratch',
    'brain',
}

# Build regex patterns dynamically to prevent self-matching in this test file
_PLANNING_DOC_NAMES = [
    'UX' + '.md',
    'NORMALIZATION' + '.md',
    'AUTHZ' + '.md',
    'SCHEMA' + '.md',
    'VOTING' + '.md',
    'API' + '.md',
    'DOCKER' + '.md',
    'PLAN' + '.md',
    'LOGS' + '.md',
    'RESEARCH' + '.md',
    'STRESS-TEST' + '.md',
    'STRESS_TEST' + '.md',
]

DANGLING_PATTERNS = [
    re.compile(r'\b' + re.escape(doc) + r'\b', re.IGNORECASE)
    for doc in _PLANNING_DOC_NAMES
]
DANGLING_PATTERNS.append(re.compile(r'\bDL-0\d\d?\b', re.IGNORECASE))
DANGLING_PATTERNS.append(re.compile(r'planning/', re.IGNORECASE))

POLICY_CODE_PATTERNS = [
    re.compile(r'\b(D-0[1-5])\b'),
    re.compile(r'\b(A-0[1-7])\b'),
    re.compile(r'\b(V-0[1-7])\b'),
]


class NoDanglingReferencesTest(SimpleTestCase):
    """Scan all project files to guarantee zero dangling planning references or leaked policy codes."""

    def setUp(self):
        self.repo_root = Path(__file__).resolve().parent.parent

    def _collect_files_to_scan(self):
        """Collect all files across src, tests, scripts, .github, and root files."""
        files_to_scan = []

        # Root files
        for item in self.repo_root.iterdir():
            if item.is_file():
                if item.name not in PENDING_REWRITE and item.name != Path(__file__).name:
                    files_to_scan.append(item)

        # Directories to scan
        subdirs_to_scan = ['src', 'tests', 'scripts', '.github']
        for subdir_name in subdirs_to_scan:
            target_dir = self.repo_root / subdir_name
            if not target_dir.exists():
                continue
            for root, dirs, files in os.walk(target_dir):
                dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith('.')]
                for file_name in files:
                    file_path = Path(root) / file_name
                    if file_path.resolve() == Path(__file__).resolve():
                        continue
                    if file_name in PENDING_REWRITE:
                        continue
                    files_to_scan.append(file_path)

        return files_to_scan

    def test_no_dangling_planning_references(self):
        """Verify no references to planning documents exist in shipping code, tests, or config."""
        files = self._collect_files_to_scan()
        violations = []

        for file_path in files:
            rel_path = file_path.relative_to(self.repo_root).as_posix()
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
            except Exception as exc:
                self.fail(f"Could not read {rel_path}: {exc}")

            for line_no, line in enumerate(content.splitlines(), start=1):
                for pattern in DANGLING_PATTERNS:
                    match = pattern.search(line)
                    if match:
                        violations.append(
                            f"{rel_path}:{line_no}: [{match.group(0)}] {line.strip()}"
                        )
                        break

        self.assertEqual(
            violations,
            [],
            f"Found {len(violations)} dangling planning doc reference(s):\n"
            + "\n".join(violations),
        )

    def test_no_policy_codes_outside_judging_md(self):
        """Policy codes (D-01..D-05, A-01..A-07, V-01..V-07) stay ONLY where JUDGING.md defines them."""
        files = self._collect_files_to_scan()
        violations = []

        for file_path in files:
            rel_path = file_path.relative_to(self.repo_root).as_posix()
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
            except Exception as exc:
                self.fail(f"Could not read {rel_path}: {exc}")

            for line_no, line in enumerate(content.splitlines(), start=1):
                for pattern in POLICY_CODE_PATTERNS:
                    match = pattern.search(line)
                    if match:
                        violations.append(
                            f"{rel_path}:{line_no}: [{match.group(1)}] {line.strip()}"
                        )
                        break

        self.assertEqual(
            violations,
            [],
            f"Found {len(violations)} policy code occurrence(s) outside JUDGING.md:\n"
            + "\n".join(violations),
        )
