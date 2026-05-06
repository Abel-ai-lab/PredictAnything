import ast
import subprocess
import sys
from pathlib import Path


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
