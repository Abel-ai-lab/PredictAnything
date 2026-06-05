from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "publish_clawhub_release.py"


def _load_module():
    sys.path.insert(0, str(SCRIPT_PATH.parent))
    try:
        spec = importlib.util.spec_from_file_location("publish_clawhub_release", SCRIPT_PATH)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(SCRIPT_PATH.parent))


def test_dry_run_uses_clawhub_package_publish_for_bundle(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    publish = _load_module()

    def fake_build_artifact(source_dir: Path, output_root: Path) -> Path:
        artifact_dir = output_root / "abel"
        skill_dir = artifact_dir / "skills" / "abel"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            (source_dir / "SKILL.md").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (artifact_dir / "openclaw.plugin.json").write_text(
            '{"id":"abel","name":"Abel","skills":["./skills"],"configSchema":{"type":"object","properties":{}}}\n',
            encoding="utf-8",
        )
        return artifact_dir

    monkeypatch.setattr(publish, "build_artifact", fake_build_artifact)
    monkeypatch.setattr(
        publish,
        "detect_git_source_metadata",
        lambda _source_dir: {
            "source_repo": "Abel-ai-lab/abel-strategy-research-skills",
            "source_commit": "abc123",
            "source_ref": "develop",
            "source_path": "",
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "publish_clawhub_release.py",
            "--output-root",
            str(tmp_path),
            "--dry-run",
        ],
    )

    assert publish.main() == 0

    out = capsys.readouterr().out
    expected_version = publish.load_skill_metadata(REPO_ROOT / "skills" / "abel")["version"]
    assert "clawhub package publish" in out
    assert "--name abel" in out
    assert "--display-name \"Abel Strategy Research Skills\"" in out
    assert f"--version {expected_version}" in out
    assert "--source-repo Abel-ai-lab/abel-strategy-research-skills" in out
    assert "--source-commit abc123" in out
    assert "--source-ref develop" in out
    assert "--tags latest" in out
    assert "--slug" not in out


def test_dry_run_allows_source_metadata_overrides(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    publish = _load_module()

    def fake_build_artifact(source_dir: Path, output_root: Path) -> Path:
        artifact_dir = output_root / "abel"
        skill_dir = artifact_dir / "skills" / "abel"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            (source_dir / "SKILL.md").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        return artifact_dir

    monkeypatch.setattr(publish, "build_artifact", fake_build_artifact)
    monkeypatch.setattr(
        publish,
        "detect_git_source_metadata",
        lambda _source_dir: {
            "source_repo": "wrong/repo",
            "source_commit": "wrong",
            "source_ref": "wrong",
            "source_path": "",
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "publish_clawhub_release.py",
            "--output-root",
            str(tmp_path),
            "--source-repo",
            "example/abel",
            "--source-commit",
            "deadbeef",
            "--source-ref",
            "release/native",
            "--source-path",
            "plugins/abel",
            "--dry-run",
        ],
    )

    assert publish.main() == 0

    out = capsys.readouterr().out
    assert "--source-repo example/abel" in out
    assert "--source-commit deadbeef" in out
    assert "--source-ref release/native" in out
    assert "--source-path plugins/abel" in out
