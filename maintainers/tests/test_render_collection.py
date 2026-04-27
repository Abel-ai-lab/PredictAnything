from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_render_collection_renders_all_skills(tmp_path) -> None:
    output_dir = tmp_path / "rendered-skills"
    command = [
        "python3",
        "maintainers/render_collection.py",
        "--profile",
        "prod",
        "--output-dir",
        str(output_dir),
    ]

    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (output_dir / "abel" / "SKILL.md").exists()
    assert (output_dir / "abel-ask" / "SKILL.md").exists()
    assert (output_dir / "abel-auth" / "SKILL.md").exists()
    assert (output_dir / "abel-strategy-discovery" / "SKILL.md").exists()

    rendered_probe_usage = (
        output_dir / "abel-ask" / "references" / "probe-usage.md"
    ).read_text(encoding="utf-8")
    rendered_auth_skill = (
        output_dir / "abel-auth" / "SKILL.md"
    ).read_text(encoding="utf-8")
    source_auth_skill = (
        REPO_ROOT / "skills" / "abel-auth" / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert 'BASE_URL="https://cap.abel.ai/api"' in rendered_probe_usage
    assert rendered_auth_skill == source_auth_skill


def test_render_collection_uses_legacy_causal_abel_local_profile(tmp_path) -> None:
    output_dir = tmp_path / "rendered-skills-sit"
    command = [
        "python3",
        "maintainers/render_collection.py",
        "--include-local",
        "--profile",
        "sit",
        "--output-dir",
        str(output_dir),
    ]

    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr

    rendered_probe_usage = (
        output_dir / "abel-ask" / "references" / "probe-usage.md"
    ).read_text(encoding="utf-8")
    rendered_narrative_probe = (
        output_dir / "abel-ask" / "scripts" / "narrative_cap_probe.py"
    ).read_text(encoding="utf-8")
    rendered_auth_setup = (
        output_dir / "abel-auth" / "references" / "setup-guide.md"
    ).read_text(encoding="utf-8")
    rendered_common_graph_probe = (
        output_dir
        / "abel-common"
        / "python"
        / "abel_common"
        / "cap"
        / "graph_probe.py"
    ).read_text(encoding="utf-8")
    rendered_common_narrative_probe = (
        output_dir
        / "abel-common"
        / "python"
        / "abel_common"
        / "cap"
        / "narrative_probe.py"
    ).read_text(encoding="utf-8")

    assert 'BASE_URL="https://cap-sit.abel.ai/api"' in rendered_probe_usage
    assert (
        'DEFAULT_BASE_URL = "https://cap-sit.abel.ai/narrative"'
        in rendered_narrative_probe
    )
    assert "Base URL: `https://api-sit.abel.ai/router/`" in rendered_auth_setup
    assert (
        'DEFAULT_BASE_URL = "https://cap-sit.abel.ai/api"'
        in rendered_common_graph_probe
    )
    assert (
        'DEFAULT_BASE_URL = "https://cap-sit.abel.ai/narrative"'
        in rendered_common_narrative_probe
    )


def test_render_collection_preserves_existing_auth_files(tmp_path) -> None:
    output_dir = tmp_path / "rendered-skills"
    ask_auth = output_dir / "abel-ask" / ".env.skill"
    auth_auth = output_dir / "abel-auth" / ".env.skill"
    ask_auth.parent.mkdir(parents=True, exist_ok=True)
    auth_auth.parent.mkdir(parents=True, exist_ok=True)
    ask_auth.write_text("ASK_TOKEN=keep-me\n", encoding="utf-8")
    auth_auth.write_text("AUTH_TOKEN=keep-me\n", encoding="utf-8")

    command = [
        "python3",
        "maintainers/render_collection.py",
        "--profile",
        "prod",
        "--output-dir",
        str(output_dir),
    ]

    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert ask_auth.read_text(encoding="utf-8") == "ASK_TOKEN=keep-me\n"
    assert auth_auth.read_text(encoding="utf-8") == "AUTH_TOKEN=keep-me\n"
