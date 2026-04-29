from __future__ import annotations

import argparse
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


def evaluate_policy(*, base_branch: str, changed_files: Iterable[str]) -> list[str]:
    base = str(base_branch or "").strip()
    files = _normalize_changed_files(changed_files)
    file_set = set(files)
    violations: list[str] = []

    changed_source_skill = any(path.startswith(SOURCE_SKILL_PREFIX) for path in files)
    changed_source_version = any(path in file_set for path in SOURCE_VERSION_FILES)
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check Abel-skills pull request branching and release policy."
    )
    parser.add_argument("--base-branch", required=True, help="Pull request base branch.")
    parser.add_argument(
        "--changed-file",
        action="append",
        default=[],
        help="Changed file path. Repeat for multiple files.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    violations = evaluate_policy(
        base_branch=args.base_branch,
        changed_files=args.changed_file,
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
