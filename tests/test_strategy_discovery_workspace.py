from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from abel_invest import narrative_impl
from abel_invest.env import resolve_alpha_source
from abel_invest.workspace import (
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
    assert "research_journal.md" in readme
    assert "upload-dashboard-bundle" not in readme
    assert "abel-auth" in readme
    assert "standalone `abel-edge init` project inside it" in agents
    assert "Do not create `./abel-invest-workspace` inside it." in agents
    assert "upload-dashboard-bundle" not in agents
    assert "research_journal.md" in agents
    assert "abel-auth" in agents


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
        edge_spec=None,
        edge_source=None,
        runtime_python=None,
        no_editable=False,
    )

    rc = narrative_impl.handle_workspace_command(args)
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
