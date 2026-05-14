from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

import strategy_discovery_api as strategy_api
from abel_invest.narrative_core.command_handlers import workspace as workspace_handlers
from abel_invest.narrative_core.session_lifecycle import resolve_workspace_arg_path
from abel_invest.workspace_core.env import resolve_alpha_source
from abel_invest.workspace_core.workspace import (
    build_default_manifest,
    render_workspace_status,
    scaffold_workspace,
)


def test_scaffold_workspace_writes_alpha_owned_boundary_guidance(tmp_path: Path) -> None:
    root = scaffold_workspace("trial-lab", target_root=tmp_path / "trial-lab")

    readme = (root / "README.md").read_text(encoding="utf-8")
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")

    assert "This workspace is for alpha-managed branch research." in readme
    assert "Do not run `abel-edge init` inside this workspace." in readme
    assert "Do not bootstrap `./abel-invest-workspace` inside it." in readme
    assert "evidence_ledger.json" in readme
    assert "frontier.md" in readme
    assert "exploration_path.md" in readme
    assert "research_journal.md" in readme
    assert "visualize-session" in readme
    assert "creates an online session view" in readme
    assert "abel-auth" in readme
    assert "standalone `abel-edge init` project inside it" in agents
    assert "Do not create `./abel-invest-workspace` inside it." in agents
    assert "visualize-session" in agents
    assert "online session view" in agents
    assert "exploration_path.md" in agents
    assert "research_journal.md" in agents
    assert "abel-auth" in agents
    assert "edit research/" not in _bash_blocks(readme)
    assert "read research/" not in _bash_blocks(readme)
    assert "edit research/" not in _bash_blocks(agents)
    assert "read research/" not in _bash_blocks(agents)
    assert "Report to the user" in agents


def _bash_blocks(text: str) -> str:
    blocks: list[str] = []
    inside = False
    current: list[str] = []
    for line in text.splitlines():
        if line.strip() == "```bash":
            inside = True
            current = []
            continue
        if inside and line.strip() == "```":
            inside = False
            blocks.append("\n".join(current))
            continue
        if inside:
            current.append(line)
    return "\n".join(blocks)


def test_scaffold_workspace_rejects_nested_workspace_under_existing_root(tmp_path: Path) -> None:
    root = scaffold_workspace("trial-lab", target_root=tmp_path / "trial-lab")

    with pytest.raises(RuntimeError, match="Refusing to create a nested Abel strategy discovery workspace"):
        scaffold_workspace("nested", target_root=root / "abel-invest-workspace")


def test_workspace_bootstrap_rejects_nested_target_with_reentry_hint(
    tmp_path: Path,
    capsys,
) -> None:
    root = scaffold_workspace("trial-lab", target_root=tmp_path / "trial-lab")
    nested_target = root / "abel-invest-workspace"

    args = argparse.Namespace(
        workspace_command="bootstrap",
        path=str(nested_target),
        name="abel-invest-workspace",
        base_python=None,
        alpha_source=None,
        runtime_python=None,
        no_editable=False,
    )

    rc = strategy_api.handle_workspace_command(args)
    out = capsys.readouterr().out

    assert rc == 1
    assert "Refusing to bootstrap a nested Abel strategy discovery workspace" in out
    assert f"Existing workspace root for this area: {root}" in out
    assert f"abel-invest workspace status --path {root}" in out
    assert f"abel-invest doctor --path {root}" in out


def test_render_workspace_status_reports_alpha_managed_mode(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()

    status = render_workspace_status(root, build_default_manifest("workspace"))

    assert "Workspace mode: alpha-managed branch research" in status
    assert f"Research root: {root / 'research'}" in status


def test_resolve_alpha_source_defaults_to_skill_root() -> None:
    resolved = resolve_alpha_source()
    expected = Path(__file__).resolve().parents[1] / "skills" / "abel-invest"

    assert resolved == expected.resolve()
    assert (resolved / "pyproject.toml").exists()


def test_workspace_context_json_reports_resolved_research_root(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    root = scaffold_workspace("trial-lab", target_root=tmp_path / "trial-lab")
    monkeypatch.setattr(
        workspace_handlers,
        "run_doctor",
        lambda _root: {
            "status": "ready",
            "workspace_mode": "alpha-managed branch research",
            "next_step": "abel-invest init-session --ticker <TICKER> --exp-id <session-id>",
        },
    )
    args = argparse.Namespace(
        workspace_command="context",
        path=str(root),
        json_output=True,
    )

    assert strategy_api.handle_workspace_command(args) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["workspace_root"] == str(root)
    assert payload["workspace_resolution"] == "current_workspace_root"
    assert payload["research_root"] == str(root / "research")
    assert payload["doctor_status"] == "ready"
    assert payload["session_command_prefix"] == "abel-invest init-session"


def test_workspace_context_json_reports_default_child_reuse(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    root = scaffold_workspace(
        "abel-invest-workspace",
        target_root=tmp_path / "abel-invest-workspace",
    )
    monkeypatch.setattr(
        workspace_handlers,
        "run_doctor",
        lambda _root: {"status": "auth_missing", "next_step": "Use abel-auth"},
    )
    args = argparse.Namespace(
        workspace_command="context",
        path=str(tmp_path),
        json_output=True,
    )

    assert strategy_api.handle_workspace_command(args) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["workspace_root"] == str(root)
    assert payload["workspace_resolution"] == "launch_root_child"
    assert payload["research_root"] == str(root / "research")
    assert payload["doctor_status"] == "auth_missing"


def test_workspace_context_missing_returns_bootstrap_next_step(
    tmp_path: Path,
    capsys,
) -> None:
    args = argparse.Namespace(
        workspace_command="context",
        path=str(tmp_path),
        json_output=True,
    )

    assert strategy_api.handle_workspace_command(args) == 1
    payload = json.loads(capsys.readouterr().out)

    assert payload["workspace_root"] is None
    assert payload["doctor_status"] == "workspace_missing"
    assert payload["default_workspace_path"] == str(tmp_path / "abel-invest-workspace")
    assert "workspace bootstrap" in payload["next_step"]


def test_workspace_arg_path_accepts_existing_launch_root_relative_session(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = scaffold_workspace(
        "abel-invest-workspace",
        target_root=tmp_path / "abel-invest-workspace",
    )
    session = workspace / "research" / "spy" / "resume-probe"
    session.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    resolved = resolve_workspace_arg_path(
        "abel-invest-workspace/research/spy/resume-probe"
    )

    assert resolved == session


def test_workspace_arg_path_keeps_workspace_relative_session_from_launch_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = scaffold_workspace(
        "abel-invest-workspace",
        target_root=tmp_path / "abel-invest-workspace",
    )
    monkeypatch.chdir(tmp_path)

    resolved = resolve_workspace_arg_path("research/spy/resume-probe")

    assert resolved == workspace / "research" / "spy" / "resume-probe"
