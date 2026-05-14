from __future__ import annotations

from argparse import Namespace

from abel_invest.narrative_core.commands import resolve_command_workspace_root
from abel_invest.workspace_core.edge_runtime import (
    apply_workspace_env,
    build_workspace_runtime_env,
)


def _write_workspace(root):
    root.mkdir(parents=True)
    (root / "alpha.workspace.yaml").write_text(
        """
version: 1
workspace:
  name: test-workspace
  kind: abel-invest
paths:
  research_root: research
  docs_root: docs
  cache_root: cache/market_data
  logs_root: logs
  venv: .venv
runtime:
  python: .venv/bin/python
""".lstrip(),
        encoding="utf-8",
    )
    (root / ".env").write_text(
        """
ABEL_CAP_BASE_URL=https://cap-sit.abel.ai/api
ABEL_AUTH_BASE_URL=https://api-sit.abel.ai/router/
ABEL_API_KEY=sit-token
IGNORED_NON_ABEL_KEY=ignore-me
""".lstrip(),
        encoding="utf-8",
    )


def test_apply_workspace_env_loads_abel_runtime_values(tmp_path):
    workspace = tmp_path / "abel-invest-workspace"
    _write_workspace(workspace)
    env = {}

    applied = apply_workspace_env(workspace, environ=env)

    assert applied["ABEL_CAP_BASE_URL"] == "https://cap-sit.abel.ai/api"
    assert env["ABEL_AUTH_BASE_URL"] == "https://api-sit.abel.ai/router/"
    assert env["ABEL_API_KEY"] == "sit-token"
    assert "IGNORED_NON_ABEL_KEY" not in env


def test_apply_workspace_env_preserves_explicit_environment_by_default(tmp_path):
    workspace = tmp_path / "abel-invest-workspace"
    _write_workspace(workspace)
    env = {"ABEL_CAP_BASE_URL": "https://cap-explicit.example/api"}

    apply_workspace_env(workspace, environ=env)

    assert env["ABEL_CAP_BASE_URL"] == "https://cap-explicit.example/api"
    assert env["ABEL_AUTH_BASE_URL"] == "https://api-sit.abel.ai/router/"


def test_build_workspace_runtime_env_includes_workspace_env_and_cache_root(tmp_path):
    workspace = tmp_path / "abel-invest-workspace"
    _write_workspace(workspace)

    env = build_workspace_runtime_env(workspace, base={})

    assert env["ABEL_CAP_BASE_URL"] == "https://cap-sit.abel.ai/api"
    assert env["ABEL_API_KEY"] == "sit-token"
    assert env["ABEL_AUTH_ENV_FILE"] == str((workspace / ".env").resolve())
    assert env["ABEL_EDGE_CACHE_ROOT"] == str((workspace / "cache/market_data").resolve())


def test_resolve_command_workspace_root_uses_launch_root_child_workspace(tmp_path, monkeypatch):
    launch_root = tmp_path / "empty_workspace"
    workspace = launch_root / "abel-invest-workspace"
    _write_workspace(workspace)
    monkeypatch.chdir(launch_root)

    root = resolve_command_workspace_root(
        Namespace(command="init-session", ticker="META", exp_id="meta-v1", root=None)
    )

    assert root == workspace


def test_resolve_command_workspace_root_does_not_fallback_for_external_absolute_path(
    tmp_path, monkeypatch
):
    workspace = tmp_path / "abel-invest-workspace"
    _write_workspace(workspace)
    external = tmp_path / "outside" / "research"
    monkeypatch.chdir(workspace)

    root = resolve_command_workspace_root(Namespace(command="doctor", path=str(external)))

    assert root is None
