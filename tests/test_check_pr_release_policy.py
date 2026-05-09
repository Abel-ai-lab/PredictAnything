from __future__ import annotations

import importlib.util
import pathlib
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_pr_release_policy.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_pr_release_policy", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module from {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CheckPrReleasePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = _load_module()

    def test_develop_pr_rejects_version_bump(self) -> None:
        violations = self.module.evaluate_policy(
            base_branch="develop",
            changed_files=["skills/abel/SKILL.md"],
            changed_source_version_files=["skills/abel/SKILL.md"],
        )
        self.assertTrue(any("version" in violation.lower() for violation in violations))

    def test_develop_pr_allows_source_skill_content_change_without_version_bump(self) -> None:
        violations = self.module.evaluate_policy(
            base_branch="develop",
            changed_files=["skills/abel/SKILL.md"],
            changed_source_version_files=[],
        )
        self.assertEqual([], violations)

    def test_develop_pr_rejects_release_changelog(self) -> None:
        violations = self.module.evaluate_policy(
            base_branch="develop",
            changed_files=["CHANGELOG.md"],
        )
        self.assertTrue(any("changelog" in violation.lower() for violation in violations))

    def test_develop_pr_rejects_committed_clawhub_artifact(self) -> None:
        violations = self.module.evaluate_policy(
            base_branch="develop",
            changed_files=["clawhub/causal-abel/SKILL.md"],
        )
        self.assertEqual([], violations)

    def test_develop_pr_allows_docs_only_change(self) -> None:
        violations = self.module.evaluate_policy(
            base_branch="develop",
            changed_files=["docs/branching-and-releases.md"],
        )
        self.assertEqual([], violations)

    def test_main_pr_requires_version_and_changelog_for_skill_release(self) -> None:
        violations = self.module.evaluate_policy(
            base_branch="main",
            changed_files=["skills/abel-ask/references/probe-usage.md"],
        )
        self.assertTrue(any("version" in violation.lower() for violation in violations))
        self.assertTrue(any("changelog" in violation.lower() for violation in violations))

    def test_main_pr_no_longer_requires_checked_in_clawhub_artifact(self) -> None:
        violations = self.module.evaluate_policy(
            base_branch="main",
            changed_files=[
                "skills/abel/SKILL.md",
                "skills/abel/references/routing.md",
                "CHANGELOG.md",
            ],
            changed_source_version_files=["skills/abel/SKILL.md"],
        )
        self.assertEqual([], violations)

    def test_main_pr_requires_actual_version_bump_not_just_skill_file_change(self) -> None:
        violations = self.module.evaluate_policy(
            base_branch="main",
            changed_files=[
                "skills/abel/SKILL.md",
                "skills/abel/references/routing.md",
                "CHANGELOG.md",
            ],
            changed_source_version_files=[],
        )
        self.assertTrue(any("version" in violation.lower() for violation in violations))

    def test_main_pr_allows_release_bundle(self) -> None:
        violations = self.module.evaluate_policy(
            base_branch="main",
            changed_files=[
                "skills/abel-ask/references/probe-usage.md",
                "skills/abel/SKILL.md",
                "CHANGELOG.md",
            ],
            changed_source_version_files=["skills/abel/SKILL.md"],
        )
        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
