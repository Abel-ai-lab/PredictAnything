import ast
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from abel_invest.narrative_core.cli_parser import build_parser


def test_strategy_discovery_bootstrap_script_exists() -> None:
    script = Path(__file__).resolve().parents[1] / "skills" / "abel-invest" / "scripts" / "bootstrap_workspace.py"
    assert script.exists(), "bootstrap script is missing"


def test_strategy_discovery_bootstrap_script_is_preinstall_entrypoint() -> None:
    script = Path(__file__).resolve().parents[1] / "skills" / "abel-invest" / "scripts" / "bootstrap_workspace.py"
    source = script.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imported_modules.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )

    assert not any(module.startswith("abel_invest") for module in imported_modules)
    assert not any(module == "yaml" or module.startswith("yaml.") for module in imported_modules)
    assert '"abel_invest.cli"' not in source
    assert '"abel_invest"' in source

    result = subprocess.run(
        [sys.executable, "-S", str(script), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Bootstrap an Abel strategy discovery workspace" in result.stdout
    assert "--edge-source" not in result.stdout
    assert "--edge-spec" not in result.stdout


def test_strategy_discovery_dependencies_constrain_edge_major_version() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "skills" / "abel-invest" / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    assert "abel-edge>=0.8.4,<0.9.0" in data["project"]["dependencies"]


def test_strategy_discovery_bootstrap_lets_pyproject_install_dependencies() -> None:
    script = Path(__file__).resolve().parents[1] / "skills" / "abel-invest" / "scripts" / "bootstrap_workspace.py"
    source = script.read_text(encoding="utf-8")

    assert "git+https://github.com/Abel-ai-causality/Abel-edge.git@main" not in source
    assert "pip\", \"install\", \"PyYAML" not in source
    assert "--no-deps" not in source


def test_strategy_discovery_cli_hides_edge_install_overrides() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "workspace",
                "bootstrap",
                "--path",
                "abel-invest-workspace",
                "--edge-source",
                "../Abel-edge",
            ]
        )
    with pytest.raises(SystemExit):
        parser.parse_args(["env", "init", "--edge-spec", "abel-edge==0.8.0"])


def test_strategy_discovery_cli_rejects_non_positive_public_limits() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "init-session",
                "--ticker",
                "TSLA",
                "--exp-id",
                "limits",
                "--discover-limit",
                "0",
            ]
        )
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "frontier",
                "expand",
                "--session",
                "research/tsla/limits",
                "--anchor",
                "TSLA.price",
                "--limit",
                "0",
            ]
        )
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "prepare-branch",
                "--branch",
                "research/tsla/limits/branches/a",
                "--cache-limit",
                "0",
            ]
        )
