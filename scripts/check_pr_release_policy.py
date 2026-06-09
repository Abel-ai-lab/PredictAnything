from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Iterable


SOURCE_SKILL_PREFIX = "skills/"
SOURCE_VERSION_FILES = {
    "skills/abel/SKILL.md",
    "skills/abel-ask/SKILL.md",
    "skills/abel-auth/SKILL.md",
    "skills/abel-invest/SKILL.md",
}
CHANGELOG_FILE = "CHANGELOG.md"


def _normalize_changed_files(changed_files: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in changed_files:
        value = str(raw or "").strip().strip("/")
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def evaluate_policy(
    *,
    base_branch: str,
    changed_files: Iterable[str],
    changed_source_version_files: Iterable[str] | None = None,
) -> list[str]:
    base = str(base_branch or "").strip()
    files = _normalize_changed_files(changed_files)
    file_set = set(files)
    version_files = set(_normalize_changed_files(changed_source_version_files or []))
    violations: list[str] = []

    changed_source_skill = any(path.startswith(SOURCE_SKILL_PREFIX) for path in files)
    changed_source_version = bool(version_files)
    changed_changelog = CHANGELOG_FILE in file_set

    if base == "develop":
        if changed_source_version:
            violations.append(
                "Feature PRs to develop must not bump the source skill version."
            )
        if changed_changelog:
            violations.append(
                "Feature PRs to develop must not add release changelog bookkeeping."
            )
        return violations

    if base == "main" and changed_source_skill:
        if not changed_source_version:
            violations.append(
                "Release PRs to main that change collection skills must include a source version bump."
            )
        if not changed_changelog:
            violations.append(
                "Release PRs to main that change collection skills must include a matching CHANGELOG.md update."
            )

    return violations


def detect_changed_source_version_files(
    *,
    base_ref: str | None,
    changed_files: Iterable[str],
) -> list[str]:
    base = str(base_ref or "").strip()
    if not base:
        return [path for path in _normalize_changed_files(changed_files) if path in SOURCE_VERSION_FILES]
    changed = []
    for path in _normalize_changed_files(changed_files):
        if path not in SOURCE_VERSION_FILES:
            continue
        diff = subprocess.run(
            ["git", "diff", "--unified=0", f"{base}...HEAD", "--", path],
            check=False,
            capture_output=True,
            text=True,
        )
        if diff.returncode not in {0, 1}:
            continue
        for line in diff.stdout.splitlines():
            if line.startswith(("+version:", "-version:")):
                changed.append(path)
                break
    return changed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check Predict Anything pull request branching and release policy."
    )
    parser.add_argument("--base-branch", required=True, help="Pull request base branch.")
    parser.add_argument(
        "--changed-file",
        action="append",
        default=[],
        help="Changed file path. Repeat for multiple files.",
    )
    parser.add_argument(
        "--base-ref",
        default="",
        help="Optional git base ref used to detect actual source skill version changes.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    violations = evaluate_policy(
        base_branch=args.base_branch,
        changed_files=args.changed_file,
        changed_source_version_files=detect_changed_source_version_files(
            base_ref=args.base_ref,
            changed_files=args.changed_file,
        ),
    )
    if not violations:
        print("PASS: pull request release policy satisfied.")
        return 0

    print("FAIL: pull request release policy violated.", file=sys.stderr)
    for violation in violations:
        print(f"- {violation}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
