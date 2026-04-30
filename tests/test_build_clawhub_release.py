from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_clawhub_release.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_clawhub_release", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_rewrites_openclaw_auth_path(tmp_path: Path) -> None:
    build_clawhub_release = _load_module()

    artifact_dir = build_clawhub_release.build_artifact(
        build_clawhub_release.SOURCE_ROOT,
        tmp_path / "clawhub",
    )

    skill_md = (artifact_dir / "skills" / "abel" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "skills.entries.abel.apiKey" in skill_md
    assert "primaryEnv: ABEL_API_KEY" in skill_md
    assert "Use `.env.skill` only" in skill_md
    assert not (artifact_dir / "skills" / "abel" / ".env.skill").exists()


def test_build_outputs_openclaw_bundle_with_all_abel_skills(tmp_path: Path) -> None:
    build_clawhub_release = _load_module()

    artifact_dir = build_clawhub_release.build_artifact(
        build_clawhub_release.SOURCE_ROOT,
        tmp_path / "clawhub",
    )

    assert artifact_dir.name == "abel"
    assert (artifact_dir / "openclaw.plugin.json").exists()
    assert (artifact_dir / "package.json").exists()
    assert (artifact_dir / "index.js").exists()
    assert not (artifact_dir / ".codex-plugin" / "plugin.json").exists()
    assert not (artifact_dir / "SKILL.md").exists()
    for name in ("abel", "abel-auth", "abel-ask", "abel-invest"):
        assert (artifact_dir / "skills" / name / "SKILL.md").exists()
    assert (artifact_dir / "skills" / "abel-common" / "python").is_dir()

    manifest = json.loads(
        (artifact_dir / "openclaw.plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["id"] == "abel"
    assert manifest["name"] == "Abel"
    assert manifest["skills"] == [
        "./skills/abel",
        "./skills/abel-auth",
        "./skills/abel-ask",
        "./skills/abel-invest",
    ]
    assert manifest["configSchema"] == {
        "type": "object",
        "additionalProperties": False,
        "properties": {},
    }

    package = json.loads((artifact_dir / "package.json").read_text(encoding="utf-8"))
    assert package["name"] == "abel"
    assert package["version"] == manifest["version"]
    assert package["type"] == "module"
    assert package["openclaw"]["extensions"] == ["./index.js"]
    assert package["openclaw"]["compat"]["pluginApi"] == ">=2026.3.24-beta.2"
    assert package["openclaw"]["build"]["openclawVersion"] == "2026.4.2"


def test_build_removes_auth_files_from_bundle_skills(tmp_path: Path) -> None:
    build_clawhub_release = _load_module()

    artifact_dir = build_clawhub_release.build_artifact(
        build_clawhub_release.SOURCE_ROOT,
        tmp_path / "clawhub",
    )

    assert not list(artifact_dir.glob("skills/**/.env.skill"))
    assert not list(artifact_dir.glob("skills/**/.env.skills"))


def test_build_excludes_python_build_artifacts(tmp_path: Path) -> None:
    build_clawhub_release = _load_module()

    source_root = tmp_path / "source" / "skills"
    for skill_name in build_clawhub_release.RELEASE_SKILL_NAMES:
        source_skill = source_root / skill_name
        source_skill.mkdir(parents=True)
        original = build_clawhub_release.SKILLS_ROOT / skill_name
        for child in original.iterdir():
            if child.is_dir():
                import shutil

                shutil.copytree(child, source_skill / child.name)
            else:
                (source_skill / child.name).write_bytes(child.read_bytes())

    egg_info = source_root / "abel-invest" / "generated_artifact.egg-info"
    egg_info.mkdir()
    (egg_info / "PKG-INFO").write_text("generated", encoding="utf-8")
    build_dir = source_root / "abel-invest" / "build"
    build_dir.mkdir()
    (build_dir / "artifact.txt").write_text("generated", encoding="utf-8")

    artifact_dir = build_clawhub_release.build_artifact(
        source_root / build_clawhub_release.SKILL_NAME,
        tmp_path / "clawhub",
    )

    assert not list(artifact_dir.glob("skills/**/*.egg-info"))
    assert not list(artifact_dir.glob("skills/**/build"))


def test_build_marks_python_backed_skills_as_requiring_python3(tmp_path: Path) -> None:
    build_clawhub_release = _load_module()

    artifact_dir = build_clawhub_release.build_artifact(
        build_clawhub_release.SOURCE_ROOT,
        tmp_path / "clawhub",
    )

    for name in ("abel-auth", "abel-ask", "abel-invest"):
        skill_md = (artifact_dir / "skills" / name / "SKILL.md").read_text(
            encoding="utf-8"
        )
        assert "metadata:" in skill_md
        assert "openclaw:" in skill_md
        assert "requires:" in skill_md
        assert "bins:" in skill_md
        assert "python3" in skill_md


def test_validate_auth_story_rejects_env_skill_as_primary() -> None:
    build_clawhub_release = _load_module()

    try:
        build_clawhub_release.validate_auth_story(
            {
                "SKILL.md": (
                    "Persist the key to `<skill-root>/.env.skill` when local storage "
                    "is available.\n"
                )
            }
        )
    except ValueError as exc:
        assert "primary auth path" in str(exc)
    else:
        raise AssertionError("validate_auth_story accepted `.env.skill` as primary")
